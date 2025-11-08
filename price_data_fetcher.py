"""
Price Data Fetcher
Fetches pool data and token prices:
- Pool pair prices: 1 hour cache
- Pool TVL data: 3 hour cache
- Token prices from CoinGecko: 5 minute cache
"""

import json
import time
import requests
from typing import Dict, Optional
from web3 import Web3
from colorama import Fore, Style, init

from cache import Cache
from rpc_mgr import RPCManager
from registries import TOKENS
from abis import UNISWAP_V2_PAIR_ABI, UNISWAP_V3_POOL_ABI, ALGEBRA_POOL_ABI, MULTICALL3_ABI

init(autoreset=True)

# Multicall3 address (same on all chains)
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"


class CoinGeckoPriceFetcher:
    """Fetch all token prices from CoinGecko in a single call"""

    # Map token symbols to CoinGecko IDs
    COINGECKO_IDS = {
        "WETH": "ethereum",
        "WBTC": "bitcoin",
        "USDC": "usd-coin",
        "USDT": "tether",
        "DAI": "dai",
        "WPOL": "matic-network",
        "WMATIC": "matic-network",
        "LINK": "chainlink",
        "AAVE": "aave",
        "UNI": "uniswap",
        "SUSHI": "sushi",
        "CRV": "curve-dao-token",
        "SNX": "havven",
        "YFI": "yearn-finance",
        "QUICK": "quickswap",
    }

    def __init__(self, cache_duration: int = 300):
        """
        Args:
            cache_duration: Cache duration in seconds (default 5 min)
        """
        self.cache_duration = cache_duration
        self.price_cache = {}
        self.last_fetch_time = 0
        self.api_url = "https://api.coingecko.com/api/v3/simple/price"

        print(f"{Fore.GREEN}✅ CoinGecko Price Fetcher Initialized{Style.RESET_ALL}")
        print(f"   Cache duration: {cache_duration}s")
        print(f"   Tokens tracked: {len(self.COINGECKO_IDS)}")

    def _fetch_all_prices(self) -> Dict[str, float]:
        """Fetch all token prices in ONE API call"""
        try:
            # Get all CoinGecko IDs in a single call
            ids = ",".join(self.COINGECKO_IDS.values())

            params = {
                "ids": ids,
                "vs_currencies": "usd"
            }

            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Map back to token symbols
            prices = {}
            for symbol, gecko_id in self.COINGECKO_IDS.items():
                if gecko_id in data and "usd" in data[gecko_id]:
                    prices[symbol] = data[gecko_id]["usd"]

            print(f"{Fore.GREEN}✅ Fetched {len(prices)} prices from CoinGecko{Style.RESET_ALL}")
            return prices

        except Exception as e:
            print(f"{Fore.RED}❌ CoinGecko API error: {e}{Style.RESET_ALL}")
            return {}

    def get_price(self, token_symbol: str) -> Optional[float]:
        """Get price for a token (cached)"""
        # Check if cache needs refresh
        now = time.time()
        if now - self.last_fetch_time > self.cache_duration:
            self.price_cache = self._fetch_all_prices()
            self.last_fetch_time = now

        return self.price_cache.get(token_symbol)

    def get_all_prices(self) -> Dict[str, float]:
        """Get all prices (cached)"""
        now = time.time()
        if now - self.last_fetch_time > self.cache_duration:
            self.price_cache = self._fetch_all_prices()
            self.last_fetch_time = now

        return self.price_cache.copy()

    def force_refresh(self):
        """Force refresh prices immediately"""
        self.price_cache = self._fetch_all_prices()
        self.last_fetch_time = time.time()


class PriceDataFetcher:
    """
    Fetches pool data and token prices with caching:
    - pair_prices: 1 hour
    - tvl_data: 3 hours
    - token prices: 5 minutes (CoinGecko)
    """

    def __init__(
        self,
        rpc_manager: RPCManager,
        cache: Cache,
        pool_registry_path: str = "./pool_registry.json",
        min_tvl_usd: float = 0  # Default to 0 = fetch all pools
    ):
        self.rpc_manager = rpc_manager
        self.cache = cache
        self.min_tvl_usd = min_tvl_usd

        # Load pool registry
        with open(pool_registry_path, 'r') as f:
            self.registry = json.load(f)

        # Initialize price fetcher
        self.price_fetcher = CoinGeckoPriceFetcher(cache_duration=300)

        print(f"{Fore.GREEN}✅ Price Data Fetcher initialized{Style.RESET_ALL}")
        print(f"   Min TVL: ${min_tvl_usd:,}")
        print(f"   Cache: Pair prices (1hr), TVL (3hr), Token prices (5min)")

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

            # Only filter by TVL if min_tvl_usd > 0
            if self.min_tvl_usd > 0 and tvl_usd < self.min_tvl_usd:
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

            # Only filter by TVL if min_tvl_usd > 0
            if self.min_tvl_usd > 0 and tvl_usd < self.min_tvl_usd:
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

    def fetch_algebra_pool(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Fetch Algebra pool data (QuickSwap V3)"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=ALGEBRA_POOL_ABI
            )

            # Get globalState (Algebra's version of slot0), liquidity, and tokens
            global_state = pool.functions.globalState().call()
            liquidity = pool.functions.liquidity().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()

            # globalState returns: (price, tick, fee, timepointIndex, communityFee0, communityFee1, unlocked)
            sqrt_price_x96 = global_state[0]
            fee = global_state[2]  # fee in hundredths of a bip (1e-6)

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

            # Only filter by TVL if min_tvl_usd > 0
            if self.min_tvl_usd > 0 and tvl_usd < self.min_tvl_usd:
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
                    'type': 'v3_algebra'
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

    def batch_fetch_pools(self, w3: Web3, pool_requests: list) -> Dict[str, Optional[Dict]]:
        """
        Batch fetch multiple pools using Multicall3

        Args:
            w3: Web3 instance
            pool_requests: List of (dex, pool_address, pool_type, pair_name) tuples

        Returns:
            Dict mapping pool_address -> pool_data
        """
        if not pool_requests:
            return {}

        # Initialize multicall contract
        multicall = w3.eth.contract(
            address=Web3.to_checksum_address(MULTICALL3_ADDRESS),
            abi=MULTICALL3_ABI
        )

        # Build calls for each pool
        calls = []
        call_map = []  # Track which calls belong to which pool

        for dex, pool_addr, pool_type, pair_name in pool_requests:
            pool_addr_checksum = Web3.to_checksum_address(pool_addr)

            if pool_type == "v2":
                # V2: getReserves()
                pool_contract = w3.eth.contract(address=pool_addr_checksum, abi=UNISWAP_V2_PAIR_ABI)
                calls.append((pool_addr_checksum, True, pool_contract.encode_abi('getReserves', [])))
                call_map.append((dex, pool_addr, pool_type, pair_name, 'getReserves'))

            elif pool_type == "v3":
                # V3: slot0() and liquidity()
                pool_contract = w3.eth.contract(address=pool_addr_checksum, abi=UNISWAP_V3_POOL_ABI)
                calls.append((pool_addr_checksum, True, pool_contract.encode_abi('slot0', [])))
                call_map.append((dex, pool_addr, pool_type, pair_name, 'slot0'))
                calls.append((pool_addr_checksum, True, pool_contract.encode_abi('liquidity', [])))
                call_map.append((dex, pool_addr, pool_type, pair_name, 'liquidity'))
                calls.append((pool_addr_checksum, True, pool_contract.encode_abi('fee', [])))
                call_map.append((dex, pool_addr, pool_type, pair_name, 'fee'))

            elif pool_type == "v3_algebra":
                # Algebra: globalState() and liquidity()
                pool_contract = w3.eth.contract(address=pool_addr_checksum, abi=ALGEBRA_POOL_ABI)
                calls.append((pool_addr_checksum, True, pool_contract.encode_abi('globalState', [])))
                call_map.append((dex, pool_addr, pool_type, pair_name, 'globalState'))
                calls.append((pool_addr_checksum, True, pool_contract.encode_abi('liquidity', [])))
                call_map.append((dex, pool_addr, pool_type, pair_name, 'liquidity'))

        # Execute multicall in batches of 100
        batch_size = 100
        all_results = []

        for i in range(0, len(calls), batch_size):
            batch_calls = calls[i:i+batch_size]
            try:
                results = multicall.functions.aggregate3(batch_calls).call()
                all_results.extend(results)
            except Exception as e:
                print(f"{Fore.RED}Multicall batch failed: {e}{Style.RESET_ALL}")
                # Return empty for this batch
                all_results.extend([(False, b'')] * len(batch_calls))

        # Decode results and group by pool
        pool_data_map = {}
        result_idx = 0

        for dex, pool_addr, pool_type, pair_name, call_type in call_map:
            success, return_data = all_results[result_idx]
            result_idx += 1

            if not success:
                continue

            # Initialize pool data if not exists
            if pool_addr not in pool_data_map:
                pool_data_map[pool_addr] = {
                    'dex': dex,
                    'type': pool_type,
                    'pair_name': pair_name,
                    'pool_address': pool_addr
                }

            # Decode based on call type
            try:
                if call_type == 'getReserves':
                    decoded = w3.codec.decode(['uint112', 'uint112', 'uint32'], return_data)
                    pool_data_map[pool_addr]['reserve0'] = decoded[0]
                    pool_data_map[pool_addr]['reserve1'] = decoded[1]

                elif call_type == 'slot0':
                    decoded = w3.codec.decode(['uint160', 'int24', 'uint16', 'uint16', 'uint16', 'uint8', 'bool'], return_data)
                    pool_data_map[pool_addr]['sqrt_price_x96'] = decoded[0]

                elif call_type == 'liquidity':
                    decoded = w3.codec.decode(['uint128'], return_data)
                    pool_data_map[pool_addr]['liquidity'] = decoded[0]

                elif call_type == 'fee':
                    decoded = w3.codec.decode(['uint24'], return_data)
                    pool_data_map[pool_addr]['fee'] = decoded[0]

                elif call_type == 'globalState':
                    decoded = w3.codec.decode(['uint160', 'int24', 'uint16', 'uint16', 'uint8', 'uint8', 'bool'], return_data)
                    pool_data_map[pool_addr]['sqrt_price_x96'] = decoded[0]
                    pool_data_map[pool_addr]['fee'] = decoded[2]

            except Exception as e:
                if self.rpc_manager.rpc_manager if hasattr(self, 'rpc_manager') else None:
                    pass  # Silent decode error

        return pool_data_map

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
            elif pool_type == "v3_algebra":
                return self.fetch_algebra_pool(w3, pool_address)
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

    def fetch_all_pools_batched(self) -> Dict[str, Dict]:
        """
        Fetch all pools from registry using Multicall3 batching
        Uses cache when available (1hr for pair prices, 3hr for TVL)
        **Much faster than sequential fetching!**
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔍 FETCHING POOL DATA (BATCHED)")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Check cache status
        warning = self.cache.get_expiration_warning()
        if warning:
            print(f"{Fore.YELLOW}{warning}{Style.RESET_ALL}\n")

        pools = {}
        total_checked = 0
        valid_pools = 0
        cached_count = 0

        # Collect all pools that need fetching (not in cache)
        pools_to_fetch = []

        for dex_name, pairs in self.registry.items():
            for pair_name, pool_data in pairs.items():
                if "pool" in pool_data:
                    total_checked += 1
                    pool_addr = pool_data["pool"]
                    pool_type = pool_data.get("type", "v2")

                    # Check cache first
                    cached_pair_prices = self.cache.get_pair_prices(dex_name, pool_addr)
                    cached_tvl_data = self.cache.get_tvl_data(dex_name, pool_addr)

                    if cached_pair_prices and cached_tvl_data:
                        # Use cached data
                        if dex_name not in pools:
                            pools[dex_name] = {}

                        pools[dex_name][pair_name] = {
                            **pool_data,
                            'pair_prices': cached_pair_prices,
                            'tvl_data': cached_tvl_data
                        }
                        valid_pools += 1
                        cached_count += 1
                    else:
                        # Need to fetch from blockchain
                        pools_to_fetch.append((dex_name, pool_addr, pool_type, pair_name, pool_data))

        # Batch fetch all pools that need fetching
        if pools_to_fetch:
            print(f"{Fore.YELLOW}⚡ Batch fetching {len(pools_to_fetch)} pools...{Style.RESET_ALL}")

            # Prepare requests for batch fetching
            batch_requests = [(dex, addr, ptype, pname) for dex, addr, ptype, pname, _ in pools_to_fetch]

            # Execute batch fetch
            def batch_fetch_func(w3):
                return self.batch_fetch_pools(w3, batch_requests)

            try:
                batch_results = self.rpc_manager.execute_with_failover(batch_fetch_func)

                # Process batch results
                for dex_name, pool_addr, pool_type, pair_name, pool_data in pools_to_fetch:
                    if pool_addr in batch_results:
                        raw_data = batch_results[pool_addr]

                        # Convert to full pool data format
                        full_data = self._process_batch_result(raw_data, pool_data)

                        if full_data:
                            if dex_name not in pools:
                                pools[dex_name] = {}

                            pools[dex_name][pair_name] = {
                                **pool_data,
                                'pair_prices': full_data['pair_prices'],
                                'tvl_data': full_data['tvl_data']
                            }
                            valid_pools += 1

                            # Cache the results
                            self.cache.set_pair_prices(dex_name, pool_addr, full_data['pair_prices'])
                            self.cache.set_tvl_data(dex_name, pool_addr, full_data['tvl_data'])

            except Exception as e:
                print(f"{Fore.RED}❌ Batch fetch failed: {e}{Style.RESET_ALL}")
                # Fallback to sequential fetching for failed pools
                print(f"{Fore.YELLOW}⚠️  Falling back to sequential fetching...{Style.RESET_ALL}")
                return self.fetch_all_pools()  # Use non-batched version as fallback

        # Print summary
        for dex_name in pools:
            print(f"{Fore.BLUE}📊 {dex_name}: {len(pools[dex_name])} pools{Style.RESET_ALL}")

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 FETCH SUMMARY")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Total checked: {total_checked:,}")
        print(f"   Valid pools: {valid_pools:,}")
        print(f"   From cache: {cached_count:,} 💾")
        print(f"   From blockchain (batched): {valid_pools - cached_count:,} ⚡")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Save cache
        self.cache.flush_all()

        return pools

    def _process_batch_result(self, raw_data: Dict, pool_data: Dict) -> Optional[Dict]:
        """Process raw batch result into full pool data format"""
        try:
            # Get token info from pool_data
            token0_addr = pool_data['token0']
            token1_addr = pool_data['token1']

            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            # Get USD prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])

            if not price0 or not price1:
                return None

            pool_type = raw_data.get('type', 'v2')

            if pool_type == 'v2':
                # V2 pool processing
                if 'reserve0' not in raw_data or 'reserve1' not in raw_data:
                    return None

                reserve0 = raw_data['reserve0']
                reserve1 = raw_data['reserve1']
                decimals0 = token0_info["decimals"]
                decimals1 = token1_info["decimals"]

                amount0 = reserve0 / (10 ** decimals0)
                amount1 = reserve1 / (10 ** decimals1)
                tvl_usd = (amount0 * price0) + (amount1 * price1)

                # Only filter by TVL if min_tvl_usd > 0
                if self.min_tvl_usd > 0 and tvl_usd < self.min_tvl_usd:
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

            elif pool_type == 'v3':
                # V3 pool processing
                if 'sqrt_price_x96' not in raw_data or 'liquidity' not in raw_data:
                    return None

                sqrt_price_x96 = raw_data['sqrt_price_x96']
                liquidity = raw_data['liquidity']
                fee = raw_data.get('fee', 3000)

                decimals0 = token0_info["decimals"]
                decimals1 = token1_info["decimals"]
                price_ratio = (sqrt_price_x96 / (2 ** 96)) ** 2
                price_adjusted = price_ratio * (10 ** decimals0) / (10 ** decimals1)

                if liquidity > 0:
                    tvl_token1 = 2 * ((liquidity * price_adjusted) ** 0.5)
                    tvl_usd = (tvl_token1 / (10 ** decimals1)) * price1
                else:
                    tvl_usd = 0

                # Only filter by TVL if min_tvl_usd > 0
                if self.min_tvl_usd > 0 and tvl_usd < self.min_tvl_usd:
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

            elif pool_type == 'v3_algebra':
                # Algebra pool processing
                if 'sqrt_price_x96' not in raw_data or 'liquidity' not in raw_data:
                    return None

                sqrt_price_x96 = raw_data['sqrt_price_x96']
                liquidity = raw_data['liquidity']
                fee = raw_data.get('fee', 0)

                decimals0 = token0_info["decimals"]
                decimals1 = token1_info["decimals"]
                price_ratio = (sqrt_price_x96 / (2 ** 96)) ** 2
                price_adjusted = price_ratio * (10 ** decimals0) / (10 ** decimals1)

                if liquidity > 0:
                    tvl_token1 = 2 * ((liquidity * price_adjusted) ** 0.5)
                    tvl_usd = (tvl_token1 / (10 ** decimals1)) * price1
                else:
                    tvl_usd = 0

                # Only filter by TVL if min_tvl_usd > 0
                if self.min_tvl_usd > 0 and tvl_usd < self.min_tvl_usd:
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
                        'type': 'v3_algebra'
                    },
                    'tvl_data': {
                        'tvl_usd': tvl_usd,
                        'token0': token0_info["symbol"],
                        'token1': token1_info["symbol"],
                        'price0_usd': price0,
                        'price1_usd': price1
                    }
                }

        except Exception as e:
            return None

        return None

    def fetch_all_pools(self) -> Dict[str, Dict]:
        """
        Fetch all pools from registry (non-batched version)
        Uses cache when available (1hr for pair prices, 3hr for TVL)

        NOTE: Use fetch_all_pools_batched() for much better performance!
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔍 FETCHING POOL DATA (SEQUENTIAL)")
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
