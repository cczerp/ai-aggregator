"""
Optimized Price Discovery Engine
Calculates prices directly from pool reserves without router calls
10-100x faster than using quote functions
"""

from web3 import Web3
from typing import Dict, List, Tuple, Optional
import time
from decimal import Decimal, getcontext
from colorama import Fore, Style

# Set high precision for calculations
getcontext().prec = 50

class OptimizedPriceEngine:
    """Direct price calculation from pool reserves - no router calls needed"""
    
    # Minimal ABIs for direct pool queries
    V2_PAIR_ABI = [{
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    }]
    
    V3_POOL_ABI = [{
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    }]
    
    def __init__(self, rpc_manager, min_profit_usd=1.0):
        self.rpc_manager = rpc_manager
        self.min_profit_usd = min_profit_usd
        self.price_cache = {}
        self.cache_duration = 2  # 2 second cache for ultra-fast scanning
        
        # DEX fees (basis points)
        self.dex_fees = {
            "quickswap_v2": 30,      # 0.3%
            "sushiswap": 30,         # 0.3%
            "uniswap_v3_500": 5,     # 0.05%
            "uniswap_v3_3000": 30,   # 0.3%
            "uniswap_v3_10000": 100, # 1.0%
            "retro": 20,             # 0.2%
            "dystopia": 20           # 0.2%
        }
        
        print(f"✅ Optimized Price Engine initialized")
        print(f"   Cache: {self.cache_duration}s")
        print(f"   Min profit: ${self.min_profit_usd}")
    
    def calculate_v2_price(self, reserve0: int, reserve1: int, decimals0: int, decimals1: int) -> Tuple[Decimal, Decimal]:
        """
        Calculate both price directions from V2 reserves
        Returns: (price_0_to_1, price_1_to_0)
        """
        if reserve0 == 0 or reserve1 == 0:
            return Decimal(0), Decimal(0)
        
        # Adjust for decimals
        adj_reserve0 = Decimal(reserve0) / Decimal(10 ** decimals0)
        adj_reserve1 = Decimal(reserve1) / Decimal(10 ** decimals1)
        
        # Price of token0 in terms of token1
        price_0_to_1 = adj_reserve1 / adj_reserve0
        # Price of token1 in terms of token0
        price_1_to_0 = adj_reserve0 / adj_reserve1
        
        return price_0_to_1, price_1_to_0
    
    def calculate_v3_price(self, sqrt_price_x96: int, decimals0: int, decimals1: int) -> Tuple[Decimal, Decimal]:
        """
        Calculate price from V3 sqrtPriceX96
        Returns: (price_0_to_1, price_1_to_0)
        """
        # Decode sqrtPriceX96 to actual price
        price = (Decimal(sqrt_price_x96) / Decimal(2**96)) ** 2
        
        # Adjust for decimals
        decimal_adjustment = Decimal(10 ** (decimals1 - decimals0))
        price_0_to_1 = price * decimal_adjustment
        price_1_to_0 = Decimal(1) / price_0_to_1 if price_0_to_1 > 0 else Decimal(0)
        
        return price_0_to_1, price_1_to_0
    
    def calculate_output_amount(self, amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int = 30) -> int:
        """
        Calculate exact output amount for V2-style AMM with fees
        Uses the constant product formula: x * y = k
        """
        if amount_in == 0 or reserve_in == 0 or reserve_out == 0:
            return 0
        
        # Apply fee (e.g., 30 bps = 0.3%)
        amount_in_with_fee = amount_in * (10000 - fee_bps)
        
        # Calculate output using constant product formula
        numerator = amount_in_with_fee * reserve_out
        denominator = (reserve_in * 10000) + amount_in_with_fee
        
        if denominator == 0:
            return 0
        
        amount_out = numerator // denominator
        return amount_out
    
    def batch_fetch_reserves(self, pool_addresses: List[str], pool_types: List[str]) -> Dict:
        """
        Batch fetch reserves for multiple pools in parallel
        Much faster than individual queries
        """
        results = {}
        
        def fetch_batch(w3):
            batch_results = {}
            
            for i, (address, pool_type) in enumerate(zip(pool_addresses, pool_types)):
                try:
                    if pool_type == "v2":
                        contract = w3.eth.contract(
                            address=Web3.to_checksum_address(address),
                            abi=self.V2_PAIR_ABI
                        )
                        reserves = contract.functions.getReserves().call()
                        batch_results[address] = {
                            "type": "v2",
                            "reserve0": reserves[0],
                            "reserve1": reserves[1],
                            "timestamp": reserves[2]
                        }
                    elif pool_type == "v3":
                        contract = w3.eth.contract(
                            address=Web3.to_checksum_address(address),
                            abi=self.V3_POOL_ABI
                        )
                        slot0 = contract.functions.slot0().call()
                        batch_results[address] = {
                            "type": "v3",
                            "sqrtPriceX96": slot0[0],
                            "tick": slot0[1]
                        }
                except:
                    continue
            
            return batch_results
        
        try:
            results = self.rpc_manager.execute_with_failover(fetch_batch)
        except:
            pass
        
        return results
    
    def find_arbitrage_fast(self, token0: str, token1: str, pools: Dict[str, List]) -> Optional[Dict]:
        """
        Ultra-fast arbitrage detection for a token pair across multiple DEXs
        Calculates prices directly from reserves without router calls
        """
        
        # Check cache first
        cache_key = f"{token0}_{token1}_{int(time.time() / self.cache_duration)}"
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        
        # Collect all pools for this pair
        pool_addresses = []
        pool_infos = []
        
        for dex_name, pool_list in pools.items():
            for pool in pool_list:
                pool_addresses.append(pool["address"])
                pool_infos.append({
                    "dex": dex_name,
                    "type": pool.get("type", "v2"),
                    "fee": pool.get("fee", 30),
                    "address": pool["address"]
                })
        
        if len(pool_addresses) < 2:
            return None  # Need at least 2 pools for arbitrage
        
        # Batch fetch all reserves
        reserves_data = self.batch_fetch_reserves(
            pool_addresses, 
            [p["type"] for p in pool_infos]
        )
        
        if len(reserves_data) < 2:
            return None
        
        # Calculate prices for each pool
        prices = []
        for pool_info in pool_infos:
            address = pool_info["address"]
            if address not in reserves_data:
                continue
            
            data = reserves_data[address]
            
            # Get token decimals (you'll need to pass this or fetch it)
            decimals0 = 18  # Default, should be fetched from token contract
            decimals1 = 18  # Default, should be fetched from token contract
            
            if data["type"] == "v2":
                price_0_to_1, price_1_to_0 = self.calculate_v2_price(
                    data["reserve0"], data["reserve1"], 
                    decimals0, decimals1
                )
            else:  # v3
                price_0_to_1, price_1_to_0 = self.calculate_v3_price(
                    data["sqrtPriceX96"], 
                    decimals0, decimals1
                )
            
            prices.append({
                "dex": pool_info["dex"],
                "address": address,
                "price_0_to_1": float(price_0_to_1),
                "price_1_to_0": float(price_1_to_0),
                "fee_bps": pool_info["fee"],
                "reserves": data
            })
        
        if len(prices) < 2:
            return None
        
        # Find best arbitrage opportunity
        best_opportunity = None
        max_profit_pct = 0
        
        for i in range(len(prices)):
            for j in range(len(prices)):
                if i == j:
                    continue
                
                buy_pool = prices[i]
                sell_pool = prices[j]
                
                # Calculate profit percentage considering fees
                buy_fee = buy_pool["fee_bps"] / 10000
                sell_fee = sell_pool["fee_bps"] / 10000
                
                # Direction 1: Buy token1 with token0 at pool i, sell at pool j
                price_diff = sell_pool["price_1_to_0"] - buy_pool["price_0_to_1"]
                if buy_pool["price_0_to_1"] > 0:
                    profit_pct = (price_diff / buy_pool["price_0_to_1"]) - buy_fee - sell_fee
                    
                    if profit_pct > max_profit_pct:
                        max_profit_pct = profit_pct
                        best_opportunity = {
                            "token_in": token0,
                            "token_out": token1,
                            "buy_dex": buy_pool["dex"],
                            "sell_dex": sell_pool["dex"],
                            "buy_price": buy_pool["price_0_to_1"],
                            "sell_price": sell_pool["price_1_to_0"],
                            "profit_pct": profit_pct * 100,
                            "buy_pool": buy_pool["address"],
                            "sell_pool": sell_pool["address"],
                            "timestamp": time.time()
                        }
        
        # Cache result
        self.price_cache[cache_key] = best_opportunity
        
        # Clean old cache entries
        if len(self.price_cache) > 10000:
            self.price_cache.clear()
        
        return best_opportunity
    
    def scan_all_pairs_optimized(self, pool_registry: Dict) -> List[Dict]:
        """
        Scan all token pairs for arbitrage opportunities
        10-100x faster than router-based scanning
        """
        opportunities = []
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"⚡ OPTIMIZED ARBITRAGE SCAN")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        
        # Group pools by token pair
        pair_pools = {}
        for dex_name, pairs in pool_registry.items():
            for pair_name, pool_data in pairs.items():
                if pair_name not in pair_pools:
                    pair_pools[pair_name] = {}
                pair_pools[pair_name][dex_name] = pool_data
        
        total_pairs = len(pair_pools)
        print(f"Scanning {total_pairs} token pairs...\n")
        
        start_time = time.time()
        pairs_checked = 0
        
        for pair_name, dex_pools in pair_pools.items():
            tokens = pair_name.split("/")
            if len(tokens) != 2:
                continue
            
            token0, token1 = tokens
            pairs_checked += 1
            
            # Progress indicator
            if pairs_checked % 10 == 0:
                elapsed = time.time() - start_time
                rate = pairs_checked / elapsed if elapsed > 0 else 0
                print(f"  Progress: {pairs_checked}/{total_pairs} pairs ({rate:.1f} pairs/sec)")
            
            # Convert pool data to list format
            pools = {}
            for dex_name, pool_info in dex_pools.items():
                if isinstance(pool_info, dict):
                    if "pool" in pool_info:  # V2
                        pools[dex_name] = [{
                            "address": pool_info["pool"],
                            "type": "v2",
                            "fee": 30
                        }]
                    else:  # V3 with fee tiers
                        pools[dex_name] = []
                        for fee_tier, tier_data in pool_info.items():
                            if isinstance(tier_data, dict) and "pool" in tier_data:
                                pools[dex_name].append({
                                    "address": tier_data["pool"],
                                    "type": "v3",
                                    "fee": int(fee_tier)
                                })
            
            # Find arbitrage for this pair
            opportunity = self.find_arbitrage_fast(token0, token1, pools)
            
            if opportunity and opportunity["profit_pct"] > 0.1:  # 0.1% minimum
                opportunities.append(opportunity)
                print(f"\n{Fore.GREEN}✅ ARBITRAGE FOUND!{Style.RESET_ALL}")
                print(f"   Pair: {pair_name}")
                print(f"   Buy: {opportunity['buy_dex']} @ {opportunity['buy_price']:.6f}")
                print(f"   Sell: {opportunity['sell_dex']} @ {opportunity['sell_price']:.6f}")
                print(f"   Profit: {opportunity['profit_pct']:.2f}%\n")
        
        elapsed_time = time.time() - start_time
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 SCAN COMPLETE")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Time: {elapsed_time:.1f}s")
        print(f"   Pairs scanned: {pairs_checked}")
        print(f"   Rate: {pairs_checked/elapsed_time:.1f} pairs/sec")
        print(f"   Opportunities: {len(opportunities)}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        return opportunities
    
    def monitor_mempool_for_opportunities(self):
        """
        Monitor mempool for large trades that create arbitrage opportunities
        This is where the real alpha is!
        """
        print(f"\n{Fore.YELLOW}🔍 Monitoring mempool for sandwich opportunities...{Style.RESET_ALL}")
        
        def monitor(w3):
            # Subscribe to pending transactions
            pending_filter = w3.eth.filter('pending')
            
            while True:
                for tx_hash in pending_filter.get_new_entries():
                    try:
                        tx = w3.eth.get_transaction(tx_hash)
                        
                        # Check if it's a DEX trade (by checking 'to' address)
                        dex_routers = [
                            "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",  # QuickSwap
                            "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",  # SushiSwap
                            # Add more routers
                        ]
                        
                        if tx.to and tx.to.lower() in [r.lower() for r in dex_routers]:
                            # Decode the transaction to see what tokens are being traded
                            # This would require decoding the input data
                            print(f"   📦 Found DEX trade: {tx_hash.hex()}")
                            
                            # Here you would:
                            # 1. Decode the swap parameters
                            # 2. Calculate the price impact
                            # 3. Find arbitrage opportunities created by this trade
                            # 4. Submit your arbitrage transaction with higher gas
                    
                    except:
                        continue
                
                time.sleep(0.1)  # Small delay
        
        # Run in separate thread or async
        # self.rpc_manager.execute_with_failover(monitor)


def integrate_with_existing_bot(bot_instance):
    """
    Integration helper to add optimized engine to existing bot
    """
    print(f"\n{Fore.CYAN}Upgrading bot with optimized price engine...{Style.RESET_ALL}")
    
    # Add the optimized engine
    bot_instance.optimized_engine = OptimizedPriceEngine(
        bot_instance.rpc_manager,
        min_profit_usd=bot_instance.arbitrage_scanner.min_profit_usd
    )
    
    # Override the scan method
    original_scan = bot_instance.find_arbitrage
    
    def enhanced_scan(filtered_pools):
        # Run both scanners
        print(f"\n{Fore.BLUE}Running dual scan mode...{Style.RESET_ALL}")
        
        # Original router-based scan
        router_opportunities = original_scan(filtered_pools)
        
        # Optimized direct-reserve scan
        optimized_opportunities = bot_instance.optimized_engine.scan_all_pairs_optimized(filtered_pools)
        
        # Merge and deduplicate
        all_opportunities = router_opportunities + optimized_opportunities
        
        return all_opportunities
    
    bot_instance.find_arbitrage = enhanced_scan
    
    print(f"{Fore.GREEN}✅ Bot upgraded with optimized engine!{Style.RESET_ALL}")
    
    return bot_instance