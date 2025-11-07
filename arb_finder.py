"""
Arbitrage Finder
Reads cached pool data and finds arbitrage opportunities.
Uses formulas and rules to iterate through all cached data.
INSTANT - no blockchain calls, pure math.
"""

from typing import Dict, List, Optional
from colorama import Fore, Style, init
from price_math import (
    calculate_v2_output_amount,
    calculate_v3_output_amount,
    get_price_from_v2_reserves,
    get_price_from_v3_sqrt_price
)

init(autoreset=True)


class ArbFinder:
    """
    Finds arbitrage opportunities from cached pool data.
    Instant and repeatable - no blockchain calls.
    """

    def __init__(self, min_profit_usd: float = 1.0):
        self.min_profit_usd = min_profit_usd

        # Test amounts in USD
        self.test_amounts_usd = [1000, 10000, 100000]

        # DEX fees (basis points: 30 = 0.3%)
        self.dex_fees = {
            'quickswap_v2': 30,
            'sushiswap': 30,
            'uniswap_v3': None,  # V3 has per-pool fees
            'retro': 20,
            'dystopia': 20
        }

        print(f"{Fore.GREEN}✅ Arb Finder initialized (min profit: ${min_profit_usd}){Style.RESET_ALL}")

    # Math functions now imported from price_math.py

    def get_pool_price(self, pool_data: Dict) -> Optional[float]:
        """
        Get effective price from pool data
        Returns: price of token1 in terms of token0
        """
        pair_prices = pool_data.get('pair_prices')
        if not pair_prices:
            return None

        pool_type = pair_prices.get('type')

        if pool_type == 'v2':
            reserve0 = pair_prices.get('reserve0', 0)
            reserve1 = pair_prices.get('reserve1', 0)
            decimals0 = pair_prices.get('decimals0', 18)
            decimals1 = pair_prices.get('decimals1', 18)

            # Use price_math function
            return get_price_from_v2_reserves(reserve0, reserve1, decimals0, decimals1)

        elif pool_type == 'v3':
            sqrt_price_x96 = pair_prices.get('sqrt_price_x96', 0)
            decimals0 = pair_prices.get('decimals0', 18)
            decimals1 = pair_prices.get('decimals1', 18)

            # Use price_math function
            return get_price_from_v3_sqrt_price(sqrt_price_x96, decimals0, decimals1)

        return None

    def calculate_arbitrage(
        self,
        pair_name: str,
        pools: List[Dict],
        amount_usd: float
    ) -> Optional[Dict]:
        """
        Calculate arbitrage for a specific pair and trade size

        Args:
            pair_name: Token pair (e.g., "USDC/WETH")
            pools: List of pools trading this pair
            amount_usd: Trade size in USD

        Returns:
            Arbitrage opportunity or None
        """
        if len(pools) < 2:
            return None

        # Get prices from each pool
        pool_prices = []

        for pool in pools:
            price = self.get_pool_price(pool['pool_data'])

            if price and price > 0:
                pool_prices.append({
                    'dex': pool['dex'],
                    'pool_data': pool['pool_data'],
                    'price': price
                })

        if len(pool_prices) < 2:
            return None

        # Find best buy (lowest price) and sell (highest price)
        best_buy = min(pool_prices, key=lambda x: x['price'])
        best_sell = max(pool_prices, key=lambda x: x['price'])

        # Calculate profit
        if best_sell['price'] <= best_buy['price']:
            return None

        # Get DEX fees
        buy_dex = best_buy['dex']
        sell_dex = best_sell['dex']

        buy_fee = self.dex_fees.get(buy_dex, 30)
        sell_fee = self.dex_fees.get(sell_dex, 30)

        # For V3, use pool-specific fee
        if best_buy['pool_data'].get('pair_prices', {}).get('type') == 'v3':
            buy_fee = best_buy['pool_data']['pair_prices'].get('fee', 3000) // 100

        if best_sell['pool_data'].get('pair_prices', {}).get('type') == 'v3':
            sell_fee = best_sell['pool_data']['pair_prices'].get('fee', 3000) // 100

        # Calculate profit after fees
        price_diff = best_sell['price'] - best_buy['price']
        profit_ratio = price_diff / best_buy['price']

        # Subtract fees
        total_fee_ratio = (buy_fee + sell_fee) / 10000
        net_profit_ratio = profit_ratio - total_fee_ratio

        if net_profit_ratio <= 0:
            return None

        profit_usd = net_profit_ratio * amount_usd

        if profit_usd < self.min_profit_usd:
            return None

        # Get TVL for reference
        buy_tvl = best_buy['pool_data'].get('tvl_data', {}).get('tvl_usd', 0)
        sell_tvl = best_sell['pool_data'].get('tvl_data', {}).get('tvl_usd', 0)

        return {
            'pair': pair_name,
            'dex_buy': buy_dex,
            'dex_sell': sell_dex,
            'buy_price': best_buy['price'],
            'sell_price': best_sell['price'],
            'profit_usd': profit_usd,
            'roi_percent': net_profit_ratio * 100,
            'trade_size_usd': amount_usd,
            'buy_tvl_usd': buy_tvl,
            'sell_tvl_usd': sell_tvl
        }

    def find_opportunities(self, pools: Dict[str, Dict]) -> List[Dict]:
        """
        Find all arbitrage opportunities from cached pool data

        Args:
            pools: Dict of {dex_name: {pair_name: pool_data}}

        Returns:
            List of opportunities sorted by profit
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💰 SCANNING FOR ARBITRAGE (instant - using cached data)")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        opportunities = []

        # Group pools by token pair
        pair_pools = {}
        for dex_name, pairs in pools.items():
            for pair_name, pool_data in pairs.items():
                if pair_name not in pair_pools:
                    pair_pools[pair_name] = []

                pair_pools[pair_name].append({
                    'dex': dex_name,
                    'pair': pair_name,
                    'pool_data': pool_data
                })

        print(f"Checking {len(pair_pools)} pairs for simple arbitrage (same pair, different DEXes)...\n")
        print(f"{Fore.CYAN}📊 ROUTE EVALUATION (Simple Arbitrage Only):{Style.RESET_ALL}")
        print(f"   Strategy: Buy Token0/Token1 on DEX_A → Sell Token0/Token1 on DEX_B")
        print(f"   Testing {len(self.test_amounts_usd)} trade sizes: ${', $'.join(str(int(amt)) for amt in self.test_amounts_usd)}\n")

        # Check each pair with 2+ pools
        checked = 0
        skipped = 0
        for pair_name, pools_list in pair_pools.items():
            if len(pools_list) < 2:
                skipped += 1
                continue

            checked += 1
            dex_names = [p['dex'] for p in pools_list]
            print(f"  {Fore.YELLOW}Checking {pair_name}{Style.RESET_ALL} across {len(pools_list)} DEXes: {', '.join(dex_names)}")

            # Try different trade sizes
            for amount_usd in self.test_amounts_usd:
                opp = self.calculate_arbitrage(pair_name, pools_list, amount_usd)

                if opp:
                    opportunities.append(opp)
                    print(f"    {Fore.GREEN}✓ PROFIT FOUND @ ${amount_usd:,.0f}: Buy {opp['dex_buy']} → Sell {opp['dex_sell']} = ${opp['profit_usd']:.2f} ({opp['roi_percent']:.2f}% ROI){Style.RESET_ALL}")

        # Sort by profit
        opportunities.sort(key=lambda x: x['profit_usd'], reverse=True)

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"✅ CALCULATION COMPLETE")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Total pairs: {len(pair_pools)}")
        print(f"   Pairs checked: {checked} (pairs with 2+ DEXes)")
        print(f"   Pairs skipped: {skipped} (only 1 DEX available)")
        print(f"   Opportunities found: {len(opportunities)}")
        print(f"\n{Fore.YELLOW}   Note: Currently only checking simple arbitrage (same pair, different DEXes)")
        print(f"         Triangular arbitrage (A→B→C→A) not yet implemented{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        return opportunities

    def display_opportunities(self, opportunities: List[Dict], limit: int = 10):
        """Display top opportunities"""
        if not opportunities:
            print(f"{Fore.YELLOW}No opportunities found{Style.RESET_ALL}\n")
            return

        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"💰 TOP ARBITRAGE OPPORTUNITIES")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        for i, opp in enumerate(opportunities[:limit], 1):
            print(f"{Fore.GREEN}{i}. {opp['pair']}{Style.RESET_ALL}")
            print(f"   Buy:  {opp['dex_buy']} @ {opp['buy_price']:.8f} (TVL: ${opp['buy_tvl_usd']:,.0f})")
            print(f"   Sell: {opp['dex_sell']} @ {opp['sell_price']:.8f} (TVL: ${opp['sell_tvl_usd']:,.0f})")
            print(f"   Profit: ${opp['profit_usd']:.2f} | ROI: {opp['roi_percent']:.2f}% | Size: ${opp['trade_size_usd']:,.0f}")
            print()

        print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    # Test with mock data
    print("Testing arb finder with mock data...")

    mock_pools = {
        'quickswap_v2': {
            'USDC/WETH': {
                'pool': '0x123...',
                'pair_prices': {
                    'reserve0': 1000000 * 10**6,  # 1M USDC
                    'reserve1': 500 * 10**18,      # 500 WETH
                    'token0': 'USDC',
                    'token1': 'WETH',
                    'decimals0': 6,
                    'decimals1': 18,
                    'type': 'v2'
                },
                'tvl_data': {
                    'tvl_usd': 2000000,
                    'token0': 'USDC',
                    'token1': 'WETH'
                }
            }
        },
        'sushiswap': {
            'USDC/WETH': {
                'pool': '0x456...',
                'pair_prices': {
                    'reserve0': 2000000 * 10**6,  # 2M USDC
                    'reserve1': 990 * 10**18,      # 990 WETH (slightly different price)
                    'token0': 'USDC',
                    'token1': 'WETH',
                    'decimals0': 6,
                    'decimals1': 18,
                    'type': 'v2'
                },
                'tvl_data': {
                    'tvl_usd': 4000000,
                    'token0': 'USDC',
                    'token1': 'WETH'
                }
            }
        }
    }

    finder = ArbFinder(min_profit_usd=1.0)
    opportunities = finder.find_opportunities(mock_pools)
    finder.display_opportunities(opportunities)
