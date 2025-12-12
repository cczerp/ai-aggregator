#!/usr/bin/env python3
"""
Cross-DEX Comparator
Compares quotes for the same token pair across different DEXes to find arbitrage
"""

import time
from typing import Dict, List, Tuple
from colorama import Fore, Style, init
from web3 import Web3

from registries import DEXES, TOKENS
from rpc_mgr import RPCManager
from abis import UNISWAP_V2_ROUTER_ABI

init(autoreset=True)


class CrossDEXComparator:
    """Compares prices across DEXes for same token pairs"""

    def __init__(self, rpc_manager: RPCManager, min_profit_bps: int = 60):
        """
        Args:
            rpc_manager: RPC manager instance
            min_profit_bps: Minimum profit in basis points (60 = 0.6%)
        """
        self.rpc_manager = rpc_manager
        endpoint = rpc_manager.get_available_endpoint("primary")
        if not endpoint:
            raise Exception("No RPC endpoint available")
        self.w3 = rpc_manager.get_web3(endpoint)
        self.min_profit_bps = min_profit_bps

        print(f"{Fore.GREEN}✅ Cross-DEX Comparator initialized{Style.RESET_ALL}")
        print(f"   Minimum profit threshold: {min_profit_bps} bps ({min_profit_bps/100}%)")

    def get_quote(self, dex_name: str, token_in: str, token_out: str, amount_in: int) -> Tuple[int, bool]:
        """
        Get quote from a specific DEX

        Returns:
            (amount_out, success)
        """
        dex_info = DEXES.get(dex_name)
        if not dex_info or dex_info.get('type') != 'v2':
            return 0, False

        router_address = dex_info.get('router')
        if not router_address:
            return 0, False

        try:
            router = self.w3.eth.contract(
                address=Web3.to_checksum_address(router_address),
                abi=UNISWAP_V2_ROUTER_ABI
            )

            token_in_addr = TOKENS[token_in]['address']
            token_out_addr = TOKENS[token_out]['address']

            path = [
                Web3.to_checksum_address(token_in_addr),
                Web3.to_checksum_address(token_out_addr)
            ]

            amounts_out = router.functions.getAmountsOut(amount_in, path).call()
            return amounts_out[1], True

        except Exception as e:
            return 0, False

    def compare_pair(
        self,
        token_a: str,
        token_b: str,
        test_amount_usd: float = 1000.0,
        dex_list: List[str] = None
    ) -> List[Dict]:
        """
        Compare a token pair across all DEXes

        Args:
            token_a: First token symbol
            token_b: Second token symbol
            test_amount_usd: Test trade size in USD
            dex_list: List of DEXes to check (None = all V2 DEXes)

        Returns:
            List of arbitrage opportunities
        """
        if token_a not in TOKENS or token_b not in TOKENS:
            print(f"{Fore.RED}❌ Unknown token: {token_a} or {token_b}{Style.RESET_ALL}")
            return []

        if dex_list is None:
            dex_list = [name for name, info in DEXES.items() if info.get('type') == 'v2']

        print(f"\n{Fore.CYAN}🔍 Comparing {token_a}/{token_b} across {len(dex_list)} DEXes{Style.RESET_ALL}")

        # Convert test amount to token_a wei
        decimals_a = TOKENS[token_a]['decimals']
        amount_in = int((test_amount_usd / 1.0) * (10 ** decimals_a))  # Assume $1 per token for now

        # Get quotes from all DEXes
        quotes = {}
        for dex_name in dex_list:
            amount_out, success = self.get_quote(dex_name, token_a, token_b, amount_in)
            if success and amount_out > 0:
                quotes[dex_name] = amount_out
                print(f"  {dex_name:20s}: {amount_out:>20,} ({token_b})")

        if len(quotes) < 2:
            print(f"{Fore.YELLOW}⚠️  Need at least 2 DEXes with liquidity{Style.RESET_ALL}")
            return []

        # Find arbitrage opportunities
        opportunities = []

        # Sort by quote (ascending)
        sorted_dexes = sorted(quotes.items(), key=lambda x: x[1])

        best_buy_dex = sorted_dexes[0][0]   # Lowest quote = best to buy token_b
        best_buy_quote = sorted_dexes[0][1]

        best_sell_dex = sorted_dexes[-1][0]  # Highest quote = best to sell token_b
        best_sell_quote = sorted_dexes[-1][1]

        # Calculate profit in basis points
        profit_bps = ((best_sell_quote - best_buy_quote) / best_buy_quote) * 10000

        # Account for fees (2 swaps × 0.3% = 0.6% = 60 bps minimum)
        fee_buy = DEXES[best_buy_dex].get('fee', 0.003) * 10000
        fee_sell = DEXES[best_sell_dex].get('fee', 0.003) * 10000
        total_fees_bps = fee_buy + fee_sell

        net_profit_bps = profit_bps - total_fees_bps

        print(f"\n{Fore.CYAN}📊 Analysis:{Style.RESET_ALL}")
        print(f"   Buy {token_b} on:  {best_buy_dex} ({best_buy_quote:,})")
        print(f"   Sell {token_b} on: {best_sell_dex} ({best_sell_quote:,})")
        print(f"   Price difference:  {profit_bps:.1f} bps ({profit_bps/100:.2f}%)")
        print(f"   Fees:              {total_fees_bps:.1f} bps ({total_fees_bps/100:.2f}%)")
        print(f"   Net profit:        {net_profit_bps:.1f} bps ({net_profit_bps/100:.2f}%)")

        if net_profit_bps >= self.min_profit_bps:
            print(f"{Fore.GREEN}✅ ARBITRAGE OPPORTUNITY FOUND!{Style.RESET_ALL}")

            opportunity = {
                'pair': f"{token_a}/{token_b}",
                'buy_dex': best_buy_dex,
                'sell_dex': best_sell_dex,
                'buy_quote': best_buy_quote,
                'sell_quote': best_sell_quote,
                'profit_bps': profit_bps,
                'fees_bps': total_fees_bps,
                'net_profit_bps': net_profit_bps,
                'net_profit_pct': net_profit_bps / 100,
                'estimated_profit_usd': (net_profit_bps / 10000) * test_amount_usd
            }

            opportunities.append(opportunity)

        else:
            print(f"{Fore.YELLOW}⚠️  Not profitable (need ≥{self.min_profit_bps} bps){Style.RESET_ALL}")

        return opportunities

    def scan_all_pairs(self, token_list: List[str] = None) -> List[Dict]:
        """
        Scan all token pair combinations

        Args:
            token_list: List of token symbols to check (None = all tokens)

        Returns:
            List of all arbitrage opportunities found
        """
        if token_list is None:
            token_list = [sym for sym in TOKENS.keys() if sym != "WMATIC"]

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🚀 SCANNING ALL TOKEN PAIRS")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Tokens: {len(token_list)}")
        print(f"   Pairs to check: {len(token_list) * (len(token_list) - 1) // 2}")

        all_opportunities = []

        # Check all combinations
        for i, token_a in enumerate(token_list):
            for token_b in token_list[i+1:]:
                opps = self.compare_pair(token_a, token_b)
                all_opportunities.extend(opps)

                time.sleep(0.1)  # Rate limit

        # Print summary
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 SCAN COMPLETE")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Opportunities found: {len(all_opportunities)}")

        if all_opportunities:
            print(f"\n{Fore.GREEN}💰 TOP OPPORTUNITIES:{Style.RESET_ALL}")
            for i, opp in enumerate(sorted(all_opportunities, key=lambda x: x['net_profit_bps'], reverse=True)[:5], 1):
                print(f"   {i}. {opp['pair']:15s} | Buy: {opp['buy_dex']:15s} | Sell: {opp['sell_dex']:15s} | Profit: {opp['net_profit_pct']:.2f}% (${opp['estimated_profit_usd']:.2f})")

        return all_opportunities


if __name__ == "__main__":
    rpc_mgr = RPCManager()
    comparator = CrossDEXComparator(rpc_mgr, min_profit_bps=60)

    # Example: Compare WETH/USDC across all DEXes
    opportunities = comparator.compare_pair('WETH', 'USDC')

    # Or scan all major pairs
    # major_tokens = ['USDC', 'WETH', 'WBTC', 'DAI', 'USDT']
    # all_opps = comparator.scan_all_pairs(major_tokens)
