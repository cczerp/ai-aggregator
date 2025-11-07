"""
Pool Data Fetcher
Fetches pool data from blockchain and caches it:
- Pair prices: 1 hour cache
- TVL data: 3 hour cache
"""

import json
from typing import Dict, Optional
from web3 import Web3
from colorama import Fore, Style, init

from cache import Cache
from rpc_mgr import RPCManager
from registries import TOKENS
from price_fetcher import CoinGeckoPriceFetcher
from abis import UNISWAP_V2_PAIR_ABI, UNISWAP_V3_POOL_ABI

init(autoreset=True)


class PoolDataFetcher:
    """
    Fetches pool data and caches it with specific durations:
    - pair_prices: 1 hour
    - tvl_data: 3 hours
    """

    def __init__(
        self,
        rpc_manager: RPCManager,
        cache: Cache,
        pool_registry_path: str = "./pool_registry.json",
        min_tvl_usd: float = 10000
    ):
        self.rpc_manager = rpc_manager
        self.cache = cache
        self.min_tvl_usd = min_tvl_usd

        # Load pool registry
        with open(pool_registry_path, 'r') as f:
            self.registry = json.load(f)

        # Initialize price fetcher
        self.price_fetcher = CoinGeckoPriceFetcher(cache_duration=300)

        print(f"{Fore.GREEN}✅ Pool Data Fetcher initialized{Style.RESET_ALL}")
        print(f"   Min TVL: ${min_tvl_usd:,}")
        print(f"   Cache: Pair prices (1hr), TVL (3hr)")

    def _get_token_info(self, address: str) -> Optional[Dict]:
        """Get token info from registry"""
        address = address.lower()
        for symbol, info in TOKENS.items():
            if info["address"].lower() == address:
                return {**info, "symbol": symbol}
        return None

    def fetch_v2_pool(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Fetch V2 pool data"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=UNISWAP_V2_PAIR_ABI
            )

            # Get reserves and tokens
            reserves = pool.functions.getReserves().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()

            reserve0, reserve1 = reserves[0], reserves[1]

            # Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            # Get USD prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])

            if not price0 or not price1:
                return None

            # Calculate TVL
            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]
            amount0 = reserve0 / (10 ** decimals0)
            amount1 = reserve1 / (10 ** decimals1)
            tvl_usd = (amount0 * price0) + (amount1 * price1)

            if tvl_usd < self.min_tvl_usd:
                return None

            return {
                'pair_prices': {
                    'reserve0': reserve0,
                    'reserve1': reserve1,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'token0_address': token0_addr,
                    'token1_address': token1_addr,
                    'decimals0': decimals0,
                    'decimals1': decimals1,
                    'type': 'v2'
                },
                'tvl_data': {
                    'tvl_usd': tvl_usd,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'price0_usd': price0,
                    'price1_usd': price1
                }
            }

        except Exception:
            return None

    def fetch_v3_pool(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Fetch V3 pool data"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=UNISWAP_V3_POOL_ABI
            )

            # Get slot0, liquidity, and tokens
            slot0 = pool.functions.slot0().call()
            liquidity = pool.functions.liquidity().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()
            fee = pool.functions.fee().call()

            sqrt_price_x96 = slot0[0]

            # Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            # Get USD prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])

            if not price0 or not price1:
                return None

            # Calculate TVL (simplified estimate)
            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]
            price_ratio = (sqrt_price_x96 / (2 ** 96)) ** 2
            price_adjusted = price_ratio * (10 ** decimals0) / (10 ** decimals1)

            if liquidity > 0:
                tvl_token1 = 2 * ((liquidity * price_adjusted) ** 0.5)
                tvl_usd = (tvl_token1 / (10 ** decimals1)) * price1
            else:
                tvl_usd = 0

            if tvl_usd < self.min_tvl_usd:
                return None

            return {
                'pair_prices': {
                    'sqrt_price_x96': sqrt_price_x96,
                    'liquidity': liquidity,
                    'fee': fee,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'token0_address': token0_addr,
                    'token1_address': token1_addr,
                    'decimals0': decimals0,
                    'decimals1': decimals1,
                    'type': 'v3'
                },
                'tvl_data': {
                    'tvl_usd': tvl_usd,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'price0_usd': price0,
                    'price1_usd': price1
                }
            }

        except Exception:
            return None

    def fetch_pool(self, dex: str, pool_address: str, pool_type: str = "v2") -> Optional[Dict]:
        """
        Fetch pool data and cache with different durations
        Returns: {'pair_prices': {...}, 'tvl_data': {...}, 'from_cache': bool}
        """
        # Check cache first
        cached_pair_prices = self.cache.get_pair_prices(dex, pool_address)
        cached_tvl_data = self.cache.get_tvl_data(dex, pool_address)

        # If both cached, return immediately
        if cached_pair_prices and cached_tvl_data:
            return {
                'pair_prices': cached_pair_prices,
                'tvl_data': cached_tvl_data,
                'from_cache': True
            }

        # Need to fetch from blockchain
        def fetch_func(w3):
            if pool_type == "v3":
                return self.fetch_v3_pool(w3, pool_address)
            else:
                return self.fetch_v2_pool(w3, pool_address)

        try:
            data = self.rpc_manager.execute_with_failover(fetch_func)

            if not data:
                return None

            # Cache with different durations
            self.cache.set_pair_prices(dex, pool_address, data['pair_prices'])
            self.cache.set_tvl_data(dex, pool_address, data['tvl_data'])

            return {
                'pair_prices': data['pair_prices'],
                'tvl_data': data['tvl_data'],
                'from_cache': False
            }

        except Exception:
            return None

    def fetch_all_pools(self) -> Dict[str, Dict]:
        """
        Fetch all pools from registry
        Uses cache when available (1hr for pair prices, 3hr for TVL)
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔍 FETCHING POOL DATA")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Check cache status
        warning = self.cache.get_expiration_warning()
        if warning:
            print(f"{Fore.YELLOW}{warning}{Style.RESET_ALL}\n")

        pools = {}
        total_checked = 0
        valid_pools = 0
        cached_count = 0

        for dex_name, pairs in self.registry.items():
            if "quickswap_v3" in dex_name.lower():
                continue  # Skip Algebra protocol

            print(f"{Fore.BLUE}📊 {dex_name}{Style.RESET_ALL}")
            pools[dex_name] = {}

            for pair_name, pool_data in pairs.items():
                if "pool" in pool_data:
                    # V2 pool
                    total_checked += 1
                    pool_addr = pool_data["pool"]
                    pool_type = pool_data.get("type", "v2")

                    data = self.fetch_pool(dex_name, pool_addr, pool_type)

                    if data:
                        pools[dex_name][pair_name] = {
                            **pool_data,
                            'pair_prices': data['pair_prices'],
                            'tvl_data': data['tvl_data']
                        }
                        valid_pools += 1

                        if data.get('from_cache'):
                            cached_count += 1
                            indicator = "💾"
                        else:
                            indicator = "🔄"

                        tvl = data['tvl_data']['tvl_usd']
                        print(f"   ✅ {pair_name:20s} TVL: ${tvl:>12,.0f} {indicator}")

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 FETCH SUMMARY")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Total checked: {total_checked:,}")
        print(f"   Valid pools: {valid_pools:,}")
        print(f"   From cache: {cached_count:,} (pair: 1hr, TVL: 3hr)")
        print(f"   From blockchain: {valid_pools - cached_count:,}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Save cache
        self.cache.flush_all()

        return pools


if __name__ == "__main__":
    # Test
    rpc_mgr = RPCManager()
    cache = Cache()
    fetcher = PoolDataFetcher(rpc_mgr, cache, min_tvl_usd=10000)

    pools = fetcher.fetch_all_pools()
    print(f"\nFetched {sum(len(p) for p in pools.values())} pools")
