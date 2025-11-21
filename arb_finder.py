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
            'dystopia': 20,
            # NEW DEXES
            'apeswap': 20,
            'dfyn': 30,
            'polycat': 20,
            'jetswap': 30,
            'waultswap': 20,
            'kyber_dmm': 8,
            'meshswap': 30,
            'polydex': 30,
            'dinoswap': 25,
            'mm_finance': 17,
        }

        print(f"{Fore.GREEN}✅ Arb Finder initialized (min profit: ${min_profit_usd}){Style.RESET_ALL}")

    # Math functions now imported from price_math.py

    def calculate_swap_output_with_slippage(
        self,
        pool_data: Dict,
        token_in_symbol: str,
        token_out_symbol: str,
        amount_in_usd: float
    ) -> Optional[Dict]:
        """
        Calculate swap output accounting for slippage using actual pool reserves.

        Args:
            pool_data: Pool data with pair_prices and tvl_data
            token_in_symbol: Input token symbol
            token_out_symbol: Output token symbol
            amount_in_usd: Trade size in USD

        Returns:
            Dict with amount_out, slippage_pct, effective_price, or None
        """
        pair_prices = pool_data.get('pair_prices')
        tvl_data = pool_data.get('tvl_data')

        if not pair_prices or not tvl_data:
            return None

        pool_type = pair_prices.get('type')
        token0 = pair_prices.get('token0')
        token1 = pair_prices.get('token1')
        decimals0 = pair_prices.get('decimals0', 18)
        decimals1 = pair_prices.get('decimals1', 18)

        # Determine direction
        is_0_to_1 = (token_in_symbol == token0 and token_out_symbol == token1)
        is_1_to_0 = (token_in_symbol == token1 and token_out_symbol == token0)

        if not (is_0_to_1 or is_1_to_0):
            return None

        # Get token prices in USD to convert amount
        price_in_usd = tvl_data.get('price0_usd' if is_0_to_1 else 'price1_usd', 0)
        price_out_usd = tvl_data.get('price1_usd' if is_0_to_1 else 'price0_usd', 0)

        if price_in_usd == 0:
            return None

        # Convert USD to token amount (in wei)
        amount_in_token = amount_in_usd / price_in_usd
        amount_in = int(amount_in_token * (10 ** (decimals0 if is_0_to_1 else decimals1)))

        if amount_in == 0:
            return None

        # Calculate output based on pool type
        if pool_type == 'v2':
            # Get reserves from tvl_data (NOT pair_prices!)
            reserve0 = tvl_data.get('reserve0', 0)
            reserve1 = tvl_data.get('reserve1', 0)

            if reserve0 == 0 or reserve1 == 0:
                return None

            # Determine fee
            dex = pair_prices.get('dex', '')
            fee_bps = self.dex_fees.get(dex, 30)

            # Use constant product formula with slippage
            reserve_in = reserve0 if is_0_to_1 else reserve1
            reserve_out = reserve1 if is_0_to_1 else reserve0

            amount_out = calculate_v2_output_amount(
                amount_in, reserve_in, reserve_out, fee_bps
            )

        elif pool_type == 'v3':
            # For V3, the stored quote is for 1 token
            # We need to scale it, but V3 has concentrated liquidity so linear scaling is approximate
            quote_ref = pair_prices.get('quote_0to1' if is_0_to_1 else 'quote_1to0', 0)

            if quote_ref == 0:
                return None

            # Get fee from pool
            fee = pair_prices.get('fee', 3000)
            fee_bps = fee // 100  # Convert from hundredths of bip to bps

            # Linear approximation (not perfect for V3, but better than nothing)
            # In production, you'd call the quoter contract for the exact amount
            amount_ref = 10 ** (decimals0 if is_0_to_1 else decimals1)
            scale = amount_in / amount_ref
            amount_out = int(quote_ref * scale)

            # Apply fee
            amount_out = amount_out * (10000 - fee_bps) // 10000
        else:
            return None

        if amount_out == 0 or price_out_usd == 0:
            return None

        # Convert output to USD
        decimals_out = decimals1 if is_0_to_1 else decimals0
        amount_out_token = amount_out / (10 ** decimals_out)
        amount_out_usd = amount_out_token * price_out_usd

        # Calculate slippage
        # Expected: amount_in_usd should equal amount_out_usd (before fees)
        # Actual: less due to slippage and fees
        slippage_pct = ((amount_in_usd - amount_out_usd) / amount_in_usd) * 100

        # Effective price
        effective_price = amount_out_token / amount_in_token if amount_in_token > 0 else 0

        return {
            'amount_in': amount_in,
            'amount_out': amount_out,
            'amount_in_usd': amount_in_usd,
            'amount_out_usd': amount_out_usd,
            'slippage_pct': slippage_pct,
            'effective_price': effective_price,
            'token_in': token_in_symbol,
            'token_out': token_out_symbol
        }

    def get_pool_price(self, pool_data: Dict) -> Optional[float]:
        """
        Get effective price from pool data using actual quotes
        Returns: price of token1 in terms of token0
        """
        pair_prices = pool_data.get('pair_prices')
        if not pair_prices:
            return None

        # Use the actual stored quotes (these are REAL quotes from DEX contracts)
        quote_0to1 = pair_prices.get('quote_0to1', 0)
        quote_1to0 = pair_prices.get('quote_1to0', 0)
        decimals0 = pair_prices.get('decimals0', 18)
        decimals1 = pair_prices.get('decimals1', 18)

        if quote_0to1 == 0 or quote_1to0 == 0:
            return None

        # The quotes represent: 1 token0 → ? token1
        # Price = how much token1 you get for 1 token0
        price = (quote_0to1 / (10 ** decimals1)) / (10 ** decimals0 / (10 ** decimals0))

        return price

    def calculate_arbitrage(
        self,
        pair_name: str,
        pools: List[Dict],
        amount_usd: float
    ) -> Optional[Dict]:
        """
        Calculate arbitrage for a specific pair and trade size using ACTUAL swap quotes with slippage

        Args:
            pair_name: Token pair (e.g., "USDC/WETH")
            pools: List of pools trading this pair
            amount_usd: Trade size in USD

        Returns:
            Arbitrage opportunity or None
        """
        if len(pools) < 2:
            return None

        # Parse pair to get tokens
        tokens = pair_name.split('/')
        if len(tokens) != 2:
            return None

        token0, token1 = tokens

        # For each pool, calculate swap outputs in BOTH directions with slippage
        pool_swaps = []

        for pool in pools:
            # Direction 1: token0 -> token1
            swap_0to1 = self.calculate_swap_output_with_slippage(
                pool['pool_data'], token0, token1, amount_usd
            )

            # Direction 2: token1 -> token0
            swap_1to0 = self.calculate_swap_output_with_slippage(
                pool['pool_data'], token1, token0, amount_usd
            )

            if swap_0to1 and swap_1to0:
                pool_swaps.append({
                    'dex': pool['dex'],
                    'pool_data': pool['pool_data'],
                    'swap_0to1': swap_0to1,
                    'swap_1to0': swap_1to0
                })

        if len(pool_swaps) < 2:
            return None

        # Find best arbitrage opportunity
        # Strategy: Buy token1 on one DEX, sell token1 on another
        best_arb = None
        max_profit = 0

        for i, buy_pool in enumerate(pool_swaps):
            for j, sell_pool in enumerate(pool_swaps):
                if i == j:
                    continue

                # Path: Start with amount_usd in token0
                # Buy token1 on buy_pool: token0 -> token1
                buy_swap = buy_pool['swap_0to1']
                amount_token1_usd = buy_swap['amount_out_usd']

                # Sell token1 on sell_pool: token1 -> token0
                # Need to recalculate for the actual amount we have
                sell_swap = self.calculate_swap_output_with_slippage(
                    sell_pool['pool_data'],
                    token1,
                    token0,
                    amount_token1_usd
                )

                if not sell_swap:
                    continue

                # Final amount in token0 (USD)
                final_amount_usd = sell_swap['amount_out_usd']

                # Profit
                profit_usd = final_amount_usd - amount_usd

                if profit_usd > max_profit and profit_usd >= self.min_profit_usd:
                    max_profit = profit_usd
                    roi_percent = (profit_usd / amount_usd) * 100

                    # Get TVL for reference
                    buy_tvl = buy_pool['pool_data'].get('tvl_data', {}).get('tvl_usd', 0)
                    sell_tvl = sell_pool['pool_data'].get('tvl_data', {}).get('tvl_usd', 0)

                    best_arb = {
                        'pair': pair_name,
                        'direction': f'Buy {token1} on {buy_pool["dex"]}, Sell {token1} on {sell_pool["dex"]}',
                        'dex_buy': buy_pool['dex'],
                        'dex_sell': sell_pool['dex'],
                        'buy_price': buy_swap['effective_price'],
                        'sell_price': sell_swap['effective_price'],
                        'profit_usd': profit_usd,
                        'net_profit_usd': profit_usd,  # Will subtract gas later
                        'roi_percent': roi_percent,
                        'roi': roi_percent,
                        'trade_size_usd': amount_usd,
                        'buy_tvl_usd': buy_tvl,
                        'sell_tvl_usd': sell_tvl,
                        'buy_slippage_pct': buy_swap['slippage_pct'],
                        'sell_slippage_pct': sell_swap['slippage_pct'],
                        'total_slippage_pct': buy_swap['slippage_pct'] + sell_swap['slippage_pct']
                    }

        return best_arb

    def build_token_graph(self, pools: Dict[str, Dict]) -> Dict:
        """
        Build a graph of all token pairs with available pools
        Returns: {token_a: {token_b: [pool_data1, pool_data2, ...], ...}, ...}
        """
        graph = {}

        for dex_name, pairs in pools.items():
            for pair_name, pool_data in pairs.items():
                pair_prices = pool_data.get('pair_prices', {})
                token0 = pair_prices.get('token0')
                token1 = pair_prices.get('token1')

                if not token0 or not token1:
                    continue

                # Add bidirectional edges
                if token0 not in graph:
                    graph[token0] = {}
                if token1 not in graph[token0]:
                    graph[token0][token1] = []
                graph[token0][token1].append({
                    'dex': dex_name,
                    'pool_data': pool_data
                })

                if token1 not in graph:
                    graph[token1] = {}
                if token0 not in graph[token1]:
                    graph[token1][token0] = []
                graph[token1][token0].append({
                    'dex': dex_name,
                    'pool_data': pool_data
                })

        return graph

    def find_triangular_paths(self, graph: Dict, max_paths: int = 1000) -> List[List]:
        """
        Find all triangular paths (A→B→C→A)
        Returns: List of paths, where each path is [token_a, token_b, token_c]
        """
        paths = []

        # For each starting token
        for token_a in graph.keys():
            # Find all tokens reachable from token_a
            for token_b in graph.get(token_a, {}).keys():
                # Find all tokens reachable from token_b
                for token_c in graph.get(token_b, {}).keys():
                    # Check if we can return to token_a from token_c
                    if token_a in graph.get(token_c, {}):
                        # Avoid duplicate paths (A→B→C→A is same as B→C→A→B)
                        path = sorted([token_a, token_b, token_c])
                        if path not in paths:
                            paths.append([token_a, token_b, token_c])

                            if len(paths) >= max_paths:
                                return paths

        return paths

    def calculate_triangular_profit(
        self,
        path: List[str],
        graph: Dict,
        amount_usd: float
    ) -> Optional[Dict]:
        """
        Calculate profit for a triangular arbitrage path

        Args:
            path: [token_a, token_b, token_c] representing A→B→C→A
            graph: Token graph from build_token_graph()
            amount_usd: Starting amount in USD

        Returns:
            Opportunity dict or None
        """
        if len(path) != 3:
            return None

        token_a, token_b, token_c = path

        # Get all pool options for each hop
        pools_a_to_b = graph.get(token_a, {}).get(token_b, [])
        pools_b_to_c = graph.get(token_b, {}).get(token_c, [])
        pools_c_to_a = graph.get(token_c, {}).get(token_a, [])

        if not pools_a_to_b or not pools_b_to_c or not pools_c_to_a:
            return None

        # Use best pool for each hop (highest liquidity)
        best_pool_a_to_b = max(pools_a_to_b, key=lambda p: p['pool_data'].get('tvl_data', {}).get('tvl_usd', 0))
        best_pool_b_to_c = max(pools_b_to_c, key=lambda p: p['pool_data'].get('tvl_data', {}).get('tvl_usd', 0))
        best_pool_c_to_a = max(pools_c_to_a, key=lambda p: p['pool_data'].get('tvl_data', {}).get('tvl_usd', 0))

        # Get quotes for each hop (using the new quote_0to1/quote_1to0 fields)
        # This is a simplified calculation - in reality would need to call the actual quote functions
        # For now, use the stored quotes as approximation

        try:
            # Hop 1: A → B
            pair_a_b = best_pool_a_to_b['pool_data'].get('pair_prices', {})
            quote_a_to_b = pair_a_b.get('quote_0to1', 0) if pair_a_b.get('token0') == token_a else pair_a_b.get('quote_1to0', 0)
            decimals_a = pair_a_b.get('decimals0', 18) if pair_a_b.get('token0') == token_a else pair_a_b.get('decimals1', 18)
            decimals_b = pair_a_b.get('decimals1', 18) if pair_a_b.get('token0') == token_a else pair_a_b.get('decimals0', 18)

            # Hop 2: B → C
            pair_b_c = best_pool_b_to_c['pool_data'].get('pair_prices', {})
            quote_b_to_c = pair_b_c.get('quote_0to1', 0) if pair_b_c.get('token0') == token_b else pair_b_c.get('quote_1to0', 0)
            decimals_c = pair_b_c.get('decimals1', 18) if pair_b_c.get('token0') == token_b else pair_b_c.get('decimals0', 18)

            # Hop 3: C → A
            pair_c_a = best_pool_c_to_a['pool_data'].get('pair_prices', {})
            quote_c_to_a = pair_c_a.get('quote_0to1', 0) if pair_c_a.get('token0') == token_c else pair_c_a.get('quote_1to0', 0)

            # Calculate amounts through the path (simplified - assumes 1 token input)
            amount_b = quote_a_to_b / (10 ** decimals_b)
            amount_c = amount_b * (quote_b_to_c / (10 ** decimals_c))
            amount_a_final = amount_c * (quote_c_to_a / (10 ** decimals_a))

            # Calculate profit (simplified - would need actual USD prices)
            profit_ratio = amount_a_final - 1.0  # Assuming started with 1 token_a

            if profit_ratio <= 0:
                return None

            return {
                'type': 'triangular',
                'path': f"{token_a}→{token_b}→{token_c}→{token_a}",
                'dex_path': f"{best_pool_a_to_b['dex']}→{best_pool_b_to_c['dex']}→{best_pool_c_to_a['dex']}",
                'profit_ratio': profit_ratio,
                'profit_usd': amount_usd * profit_ratio,
                'roi_percent': profit_ratio * 100,
                'trade_size_usd': amount_usd
            }

        except:
            return None

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

        # ========== TRIANGULAR ARBITRAGE ==========
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔺 TRIANGULAR ARBITRAGE SCANNING")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Build token graph
        print(f"Building token graph from {len(pools)} DEXes...")
        graph = self.build_token_graph(pools)
        token_count = len(graph)
        print(f"  ✅ Graph built: {token_count} tokens")

        # Find all triangular paths
        print(f"Finding all triangular paths (A→B→C→A)...")
        paths = self.find_triangular_paths(graph, max_paths=5000)
        print(f"  ✅ Found {len(paths)} possible triangular paths")

        if paths:
            print(f"\n{Fore.CYAN}📊 EVALUATING TRIANGULAR ROUTES:{Style.RESET_ALL}")
            print(f"   Strategy: Token_A → Token_B → Token_C → Token_A")
            print(f"   Testing {len(self.test_amounts_usd)} trade sizes per path\n")

            triangle_checked = 0
            for path in paths[:100]:  # Check top 100 paths
                triangle_checked += 1
                if triangle_checked % 10 == 0:
                    print(f"  ...checked {triangle_checked}/{min(100, len(paths))} paths")

                # Try different trade sizes
                for amount_usd in self.test_amounts_usd:
                    opp = self.calculate_triangular_profit(path, graph, amount_usd)

                    if opp:
                        opportunities.append(opp)
                        print(f"  {Fore.GREEN}✓ TRIANGLE PROFIT: {opp['path']} via {opp['dex_path']} = ${opp['profit_usd']:.2f} ({opp['roi_percent']:.2f}% ROI){Style.RESET_ALL}")

        # Sort by profit
        opportunities.sort(key=lambda x: x['profit_usd'], reverse=True)

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"✅ CALCULATION COMPLETE")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"\n{Fore.GREEN}SIMPLE ARBITRAGE (Same Pair, Different DEXes):{Style.RESET_ALL}")
        print(f"   Total pairs: {len(pair_pools)}")
        print(f"   Pairs checked: {checked} (pairs with 2+ DEXes)")
        print(f"   Pairs skipped: {skipped} (only 1 DEX available)")
        print(f"\n{Fore.GREEN}TRIANGULAR ARBITRAGE (A→B→C→A):{Style.RESET_ALL}")
        print(f"   Total paths found: {len(paths) if paths else 0}")
        print(f"   Paths evaluated: {min(100, len(paths)) if paths else 0}")
        print(f"\n{Fore.CYAN}TOTAL OPPORTUNITIES: {len(opportunities)}{Style.RESET_ALL}")
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
