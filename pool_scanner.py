# pool_scanner.py
"""
Pool Scanner with:
- $10k minimum TVL filtering
- Persistent cache integration
- Batch RPC calls
- Smart scanning logic
"""
from web3 import Web3
from typing import Dict, List, Optional
import json
import time
from colorama import Fore, Style

from rpc_mgr import RPCManager
from cache import Cache
from registries import TOKENS, get_token_decimals
from price_fetcher import CoinGeckoPriceFetcher

# V2 Pool ABI
V2_POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "reserve0", "type": "uint112"},
            {"name": "reserve1", "type": "uint112"},
            {"name": "blockTimestampLast", "type": "uint32"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# V3 Pool ABI
V3_POOL_ABI = [
    {
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
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class PoolScanner:
    """Scan pools with caching and batch operations"""
    
    def __init__(
        self,
        rpc_manager: RPCManager,
        cache: Cache,
        pool_registry_path: str = "./pool_registry.json",
        min_liquidity_usd: float = 10000
    ):
        self.rpc_manager = rpc_manager
        self.cache = cache
        self.min_liquidity_usd = min_liquidity_usd
        
        # Load pool registry
        with open(pool_registry_path, 'r') as f:
            self.registry = json.load(f)
        
        # Initialize CoinGecko price fetcher (one API call for all prices!)
        self.price_fetcher = CoinGeckoPriceFetcher(cache_duration=300)  # 5 min cache
        
        # Track skipped pools for reporting
        self.skipped_pools = {"no_price_feed": set(), "low_liquidity": 0, "failed_query": 0}
        
        print(f"\n{Fore.GREEN}✅ Pool Scanner Initialized{Style.RESET_ALL}")
        print(f"   Min TVL: ${self.min_liquidity_usd:,}")
        print(f"   Total DEXes: {len(self.registry)}")
    
    def _get_token_info_by_address(self, address: str) -> Optional[Dict]:
        """Get token info by address"""
        address = address.lower()
        for symbol, info in TOKENS.items():
            if info["address"].lower() == address:
                return {**info, "symbol": symbol}
        return None
    
    def _get_token_price_usd(self, token_address: str) -> Optional[float]:
        """Get USD price for a token by its address"""
        token_info = self._get_token_info_by_address(token_address)
        if not token_info:
            return None
        return self.price_fetcher.get_price(token_info["symbol"])
    
    def _query_v2_liquidity(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Query V2 pool liquidity"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=V2_POOL_ABI
            )
            
            # Get reserves
            reserves = pool.functions.getReserves().call()
            reserve0, reserve1 = reserves[0], reserves[1]
            
            # Get token addresses
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()
            
            # Get token info
            token0_info = self._get_token_info_by_address(token0_addr)
            token1_info = self._get_token_info_by_address(token1_addr)
            
            if not token0_info or not token1_info:
                return None
            
            # Get prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])
            
            if not price0 or not price1:
                # Track which tokens are missing price feeds
                if not price0:
                    self.skipped_pools["no_price_feed"].add(token0_info["symbol"])
                if not price1:
                    self.skipped_pools["no_price_feed"].add(token1_info["symbol"])
                return None
            
            # Calculate TVL
            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]
            
            amount0 = reserve0 / (10 ** decimals0)
            amount1 = reserve1 / (10 ** decimals1)
            
            tvl_usd = (amount0 * price0) + (amount1 * price1)
            
            # Sanity check
            if tvl_usd > 100_000_000:  # $100M max per pool
                return None
            
            return {
                "reserve0": reserve0,
                "reserve1": reserve1,
                "token0": token0_info["symbol"],
                "token1": token1_info["symbol"],
                "token0_address": token0_addr,
                "token1_address": token1_addr,
                "decimals0": decimals0,
                "decimals1": decimals1,
                "price0": price0,
                "price1": price1,
                "tvl_usd": tvl_usd,
                "type": "v2"
            }
        
        except Exception as e:
            return None
    
    def _query_v3_liquidity(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Query V3 pool liquidity"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=V3_POOL_ABI
            )
            
            # Get slot0 and liquidity
            slot0 = pool.functions.slot0().call()
            liquidity = pool.functions.liquidity().call()
            sqrt_price_x96 = slot0[0]
            
            # Get token addresses
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()
            
            # Get token info
            token0_info = self._get_token_info_by_address(token0_addr)
            token1_info = self._get_token_info_by_address(token1_addr)
            
            if not token0_info or not token1_info:
                return None
            
            # Get prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])
            
            if not price0 or not price1:
                # Track which tokens are missing price feeds
                if not price0:
                    self.skipped_pools["no_price_feed"].add(token0_info["symbol"])
                if not price1:
                    self.skipped_pools["no_price_feed"].add(token1_info["symbol"])
                return None
            
            # Calculate price from sqrtPriceX96
            price_ratio = (sqrt_price_x96 / (2 ** 96)) ** 2
            
            # Adjust for decimals
            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]
            price_adjusted = price_ratio * (10 ** decimals0) / (10 ** decimals1)
            
            # Estimate TVL (simplified - not exact but good enough for filtering)
            # TVL ≈ 2 * sqrt(liquidity * price_in_token1)
            if liquidity > 0:
                tvl_token1 = 2 * ((liquidity * price_adjusted) ** 0.5)
                tvl_usd = (tvl_token1 / (10 ** decimals1)) * price1
            else:
                tvl_usd = 0
            
            # Sanity check
            if tvl_usd > 100_000_000 or tvl_usd < 0:
                return None
            
            return {
                "liquidity": liquidity,
                "sqrt_price_x96": sqrt_price_x96,
                "token0": token0_info["symbol"],
                "token1": token1_info["symbol"],
                "token0_address": token0_addr,
                "token1_address": token1_addr,
                "decimals0": decimals0,
                "decimals1": decimals1,
                "price0": price0,
                "price1": price1,
                "tvl_usd": tvl_usd,
                "type": "v3"
            }
        
        except Exception as e:
            return None
    
    def query_pool(self, dex_name: str, pool_address: str, pool_type: str) -> Optional[Dict]:
        """Query single pool with caching"""
        
        # Check cache first
        cached_data = self.cache.get(dex_name, pool_address)
        if cached_data:
            return cached_data
        
        # Skip QuickSwap V3 (uses Algebra protocol - different ABI)
        if "quickswap_v3" in dex_name.lower():
            return None
        
        # Query from blockchain
        def query_func(w3):
            if pool_type == "v3":
                return self._query_v3_liquidity(w3, pool_address)
            else:
                return self._query_v2_liquidity(w3, pool_address)
        
        try:
            data = self.rpc_manager.execute_with_failover(query_func)
            
            if data:
                # Save to cache
                self.cache.set(dex_name, pool_address, data)
            
            return data
        
        except Exception as e:
            return None
    
    def scan_all_pools(self) -> Dict:
        """Scan all pools and filter by liquidity"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔍 SCANNING POOLS FOR HIGH LIQUIDITY")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        print(f"   Minimum TVL: ${self.min_liquidity_usd:,}")
        print(f"   Cache Duration: 24h\n")
        
        filtered_pools = {}
        total_pools = 0
        valid_pools = 0
        low_liquidity_pools = 0
        cached_pools = 0
        failed_pools = 0
        
        scan_start = time.time()
        
        for dex_name, pairs in self.registry.items():
            print(f"\n{Fore.BLUE}📊 Scanning {dex_name}{Style.RESET_ALL}")
            filtered_pools[dex_name] = {}
            
            # Skip empty DEXes
            if not pairs:
                print(f"   ⏭️  Skipped (empty)")
                continue
            
            # Skip QuickSwap V3 (Algebra protocol)
            if "quickswap_v3" in dex_name.lower():
                print(f"   ⏭️  Skipped (Algebra protocol not yet supported)")
                continue
            
            for pair_name, pool_data in pairs.items():
                # Handle V2 (single pool)
                if "pool" in pool_data:
                    total_pools += 1
                    pool_addr = pool_data["pool"]
                    
                    # Check if cached
                    is_cached = self.cache.is_cached(dex_name, pool_addr)
                    if is_cached:
                        cached_pools += 1
                    
                    data = self.query_pool(dex_name, pool_addr, pool_data.get("type", "v2"))
                    
                    if data and data.get("tvl_usd"):
                        if data["tvl_usd"] >= self.min_liquidity_usd:
                            filtered_pools[dex_name][pair_name] = {
                                **pool_data,
                                "liquidity_data": data
                            }
                            valid_pools += 1
                            cache_indicator = "💾" if is_cached else "🔄"
                            print(f"   ✅ {pair_name:20s} TVL: ${data['tvl_usd']:>12,.0f} {cache_indicator}")
                        else:
                            self.skipped_pools["low_liquidity"] += 1
                    else:
                        self.skipped_pools["failed_query"] += 1
                
                # Handle V3 (multiple fee tiers)
                else:
                    filtered_pools[dex_name][pair_name] = {}
                    for fee_tier, fee_data in pool_data.items():
                        total_pools += 1
                        pool_addr = fee_data["pool"]
                        
                        is_cached = self.cache.is_cached(dex_name, pool_addr)
                        if is_cached:
                            cached_pools += 1
                        
                        data = self.query_pool(dex_name, pool_addr, "v3")
                        
                        if data and data.get("tvl_usd"):
                            if data["tvl_usd"] >= self.min_liquidity_usd:
                                filtered_pools[dex_name][pair_name][fee_tier] = {
                                    **fee_data,
                                    "liquidity_data": data
                                }
                                valid_pools += 1
                                fee_pct = int(fee_tier) / 10000
                                cache_indicator = "💾" if is_cached else "🔄"
                                print(f"   ✅ {pair_name:20s} ({fee_pct:.2f}%) TVL: ${data['tvl_usd']:>10,.0f} {cache_indicator}")
                            else:
                                self.skipped_pools["low_liquidity"] += 1
                        else:
                            self.skipped_pools["failed_query"] += 1
        
        scan_duration = time.time() - scan_start
        
        # Print summary
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 SCAN SUMMARY")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Total pools scanned:     {total_pools:,}")
        print(f"   ✅ Valid (>${self.min_liquidity_usd:,.0f} TVL): {valid_pools:,}")
        print(f"   💾 Served from cache:     {cached_pools:,}")
        print(f"   ⚠️  Low liquidity:         {self.skipped_pools['low_liquidity']:,}")
        print(f"   ❌ Failed queries:        {self.skipped_pools['failed_query']:,}")
        
        # Show tokens with missing price feeds
        if self.skipped_pools["no_price_feed"]:
            print(f"\n   {Fore.YELLOW}⚠️  Tokens without price feeds (pools skipped):{Style.RESET_ALL}")
            for token in sorted(self.skipped_pools["no_price_feed"]):
                print(f"      • {token}")
        
        print(f"\n   ⏱️  Scan duration:         {scan_duration:.1f}s")
        print(f"   ⏰ Cache valid for:       24 hours")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        # CRITICAL: Force save cache to disk
        self.cache.flush()
        
        return filtered_pools