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
from registries import TOKENS, DEXES
from abis import UNISWAP_V2_PAIR_ABI, UNISWAP_V3_POOL_ABI, UNISWAP_V2_ROUTER_ABI, QUOTER_V2_ABI

init(autoreset=True)


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
        # NEW TOKENS
        "GRT": "the-graph",
        "BAL": "balancer",
        "GHST": "aavegotchi",
        "SAND": "the-sandbox",
        "MANA": "decentraland",
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
    - token prices: 5 minutes (CoinGecko) + on-chain derivation
    """

    def __init__(
        self,
        rpc_manager: RPCManager,
        cache: Cache,
        pool_registry_path: str = "./pool_registry.json",
        min_tvl_usd: float = 3000
    ):
        self.rpc_manager = rpc_manager
        self.cache = cache
        self.min_tvl_usd = min_tvl_usd

        # Load pool registry
        with open(pool_registry_path, 'r') as f:
            self.registry = json.load(f)

        # Initialize price fetcher
        self.price_fetcher = CoinGeckoPriceFetcher(cache_duration=300)

        # On-chain derived prices (bootstrap from USDC anchor)
        self.derived_prices = {
            "USDC": 1.0,   # Anchor: stablecoin
            "USDT": 1.0,   # Anchor: stablecoin
            "DAI": 1.0,    # Anchor: stablecoin
        }

        print(f"{Fore.GREEN}✅ Price Data Fetcher initialized{Style.RESET_ALL}")
        print(f"   Min TVL: ${min_tvl_usd:,}")
        print(f"   Cache: Pair prices (1hr), TVL (3hr), Token prices (5min)")
        print(f"   Price anchors: USDC/USDT/DAI = $1.00 (on-chain derivation enabled)")

    def _get_token_info(self, address: str) -> Optional[Dict]:
        """Get token info from registry"""
        address = address.lower()
        for symbol, info in TOKENS.items():
            if info["address"].lower() == address:
                return {**info, "symbol": symbol}
        return None

    def derive_price_from_quote(self, token_symbol: str, quote_value: int, quote_token_symbol: str,
                                quote_token_decimals: int, token_decimals: int) -> Optional[float]:
        """
        Derive a token price from an on-chain quote against a known token

        Args:
            token_symbol: Symbol of token to price (e.g., "WETH")
            quote_value: Raw quote value in wei (e.g., 2000000000 for 2000 USDC)
            quote_token_symbol: Symbol of the quote token (e.g., "USDC")
            quote_token_decimals: Decimals of quote token
            token_decimals: Decimals of token being priced

        Returns:
            USD price of token, or None if quote token has no price
        """
        # Get quote token price (try derived first, then CoinGecko)
        quote_price = self.derived_prices.get(quote_token_symbol)
        if not quote_price:
            quote_price = self.price_fetcher.get_price(quote_token_symbol)

        if not quote_price:
            return None

        # Calculate: 1 token = (quote_value / 10**quote_decimals) quote_tokens
        # Price in USD = exchange_rate * quote_price
        exchange_rate = quote_value / (10 ** quote_token_decimals)
        token_price = exchange_rate * quote_price

        return token_price

    def get_token_price(self, token_symbol: str) -> Optional[float]:
        """
        Get token price with fallback chain:
        1. Check derived prices (on-chain)
        2. Check CoinGecko
        3. Return None
        """
        # First check derived prices
        if token_symbol in self.derived_prices:
            return self.derived_prices[token_symbol]

        # Then check CoinGecko
        cg_price = self.price_fetcher.get_price(token_symbol)
        if cg_price:
            return cg_price

        return None

    def fetch_v2_pool(self, w3: Web3, pool_address: str, dex: str) -> Optional[Dict]:
        """Fetch V2 pool data - QUOTES FIRST, then TVL"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=UNISWAP_V2_PAIR_ABI
            )

            # STEP 1: Get basic pool info (fast)
            reserves = pool.functions.getReserves().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()
            reserve0, reserve1 = reserves[0], reserves[1]

            # STEP 2: Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]

            # STEP 3: GET QUOTES FIRST (before wasting time on TVL)
            dex_info = DEXES.get(dex, {})
            router_addr = dex_info.get("router")

            if not router_addr:
                return None

            router = w3.eth.contract(
                address=Web3.to_checksum_address(router_addr),
                abi=UNISWAP_V2_ROUTER_ABI
            )

            # Quote both directions with 1 token amount
            test_amount0 = 10 ** decimals0  # 1 token0
            test_amount1 = 10 ** decimals1  # 1 token1

            # Get quote for token0 -> token1
            quote_0to1 = 0
            try:
                path0to1 = [Web3.to_checksum_address(token0_addr), Web3.to_checksum_address(token1_addr)]
                amounts_out_0to1 = router.functions.getAmountsOut(test_amount0, path0to1).call()
                quote_0to1 = amounts_out_0to1[1]  # Output amount
                normalized_quote = quote_0to1 / (10**decimals1)
                print(f"  ✅ {token0_info['symbol']}/{token1_info['symbol']} on {dex}")
                print(f"     Quote: 1 {token0_info['symbol']} = {normalized_quote:.8f} {token1_info['symbol']}")
                print(f"     Raw: {quote_0to1} (decimals: {decimals0}/{decimals1})")
            except Exception as e:
                # Skip pool if quote fails
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} - quote failed: {str(e)[:80]}")
                return None

            # Get quote for token1 -> token0
            quote_1to0 = 0
            try:
                path1to0 = [Web3.to_checksum_address(token1_addr), Web3.to_checksum_address(token0_addr)]
                amounts_out_1to0 = router.functions.getAmountsOut(test_amount1, path1to0).call()
                quote_1to0 = amounts_out_1to0[1]  # Output amount
            except Exception as e:
                # Skip pool if reverse quote fails
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} - reverse quote failed")
                return None

            # STEP 4: NOW get TVL data (only if quotes succeeded)
            price0 = self.get_token_price(token0_info["symbol"])
            price1 = self.get_token_price(token1_info["symbol"])

            print(f"     Prices: {token0_info['symbol']}=${price0 if price0 else 'NONE'}, {token1_info['symbol']}=${price1 if price1 else 'NONE'}")

            # Try to derive missing prices from on-chain quotes
            if not price0 and price1:
                # Derive price0 from quote: 1 token0 = (quote_0to1 / 10**decimals1) token1
                price0 = self.derive_price_from_quote(
                    token0_info["symbol"], quote_0to1, token1_info["symbol"],
                    decimals1, decimals0
                )
                if price0 and price0 > 0:
                    self.derived_prices[token0_info["symbol"]] = price0
                    print(f"  💡 Derived {token0_info['symbol']} = ${price0:.6f} from {token1_info['symbol']} quote")

            if not price1 and price0:
                # Derive price1 from quote: 1 token1 = (quote_1to0 / 10**decimals0) token0
                price1 = self.derive_price_from_quote(
                    token1_info["symbol"], quote_1to0, token0_info["symbol"],
                    decimals0, decimals1
                )
                if price1 and price1 > 0:
                    self.derived_prices[token1_info["symbol"]] = price1
                    print(f"  💡 Derived {token1_info['symbol']} = ${price1:.6f} from {token0_info['symbol']} quote")

            # Calculate TVL if we have prices
            if price0 and price1:
                amount0 = reserve0 / (10 ** decimals0)
                amount1 = reserve1 / (10 ** decimals1)
                tvl_usd = (amount0 * price0) + (amount1 * price1)
                print(f"     Reserves: {amount0:.2f} {token0_info['symbol']} (${amount0 * price0:,.0f}) + {amount1:.2f} {token1_info['symbol']} (${amount1 * price1:,.0f}) = ${tvl_usd:,.0f}")
            else:
                # No way to calculate TVL without prices
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} - no USD price available for both tokens")
                return None

            # Check TVL threshold (ALWAYS CHECK, even if derived prices)
            if tvl_usd < self.min_tvl_usd:
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} - TVL ${tvl_usd:,.0f} < ${self.min_tvl_usd:,.0f}")
                return None

            return {
                'pair_prices': {
                    'quote_0to1': quote_0to1,  # ACTUAL quote: 1 token0 → ? token1
                    'quote_1to0': quote_1to0,  # ACTUAL quote: 1 token1 → ? token0
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'token0_address': token0_addr,
                    'token1_address': token1_addr,
                    'decimals0': decimals0,
                    'decimals1': decimals1,
                    'type': 'v2',
                    'dex': dex
                },
                'tvl_data': {
                    'tvl_usd': tvl_usd,
                    'reserve0': reserve0,
                    'reserve1': reserve1,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'price0_usd': price0 if price0 else 0,
                    'price1_usd': price1 if price1 else 0
                }
            }

        except Exception as e:
            return None

    def fetch_v3_pool(self, w3: Web3, pool_address: str, dex: str) -> Optional[Dict]:
        """Fetch V3 pool data - QUOTES FIRST, then TVL"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=UNISWAP_V3_POOL_ABI
            )

            # STEP 1: Get basic pool info (fast)
            slot0 = pool.functions.slot0().call()
            liquidity = pool.functions.liquidity().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()
            fee = pool.functions.fee().call()
            sqrt_price_x96 = slot0[0]

            # STEP 2: Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]

            # STEP 3: GET QUOTES FIRST (before wasting time on TVL)
            dex_info = DEXES.get(dex, {})
            quoter_addr = dex_info.get("quoter")

            if not quoter_addr:
                return None

            quoter = w3.eth.contract(
                address=Web3.to_checksum_address(quoter_addr),
                abi=QUOTER_V2_ABI
            )

            # Quote both directions with 1 token amount
            test_amount0 = 10 ** decimals0  # 1 token0
            test_amount1 = 10 ** decimals1  # 1 token1

            # Get quote for token0 -> token1
            quote_0to1 = 0
            try:
                params0to1 = {
                    'tokenIn': Web3.to_checksum_address(token0_addr),
                    'tokenOut': Web3.to_checksum_address(token1_addr),
                    'amountIn': test_amount0,
                    'fee': fee,
                    'sqrtPriceLimitX96': 0
                }
                result_0to1 = quoter.functions.quoteExactInputSingle(params0to1).call()
                quote_0to1 = result_0to1[0]  # amountOut
                fee_pct = fee / 10000
                print(f"  ✅ {token0_info['symbol']}/{token1_info['symbol']} on {dex} ({fee_pct:.2f}%) - quote: 1 {token0_info['symbol']} = {quote_0to1 / (10**decimals1):.6f} {token1_info['symbol']}")
            except Exception as e:
                # Skip pool if quoter fails
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} (fee:{fee}) - quoter failed: {str(e)[:80]}")
                return None

            # Get quote for token1 -> token0
            quote_1to0 = 0
            try:
                params1to0 = {
                    'tokenIn': Web3.to_checksum_address(token1_addr),
                    'tokenOut': Web3.to_checksum_address(token0_addr),
                    'amountIn': test_amount1,
                    'fee': fee,
                    'sqrtPriceLimitX96': 0
                }
                result_1to0 = quoter.functions.quoteExactInputSingle(params1to0).call()
                quote_1to0 = result_1to0[0]  # amountOut
            except Exception as e:
                # Skip pool if reverse quoter fails
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} (fee:{fee}) - reverse quoter failed")
                return None

            # STEP 4: NOW get TVL data (only if quotes succeeded)
            price0 = self.get_token_price(token0_info["symbol"])
            price1 = self.get_token_price(token1_info["symbol"])

            print(f"     Prices: {token0_info['symbol']}=${price0 if price0 else 'NONE'}, {token1_info['symbol']}=${price1 if price1 else 'NONE'}")

            # Try to derive missing prices from on-chain quotes
            if not price0 and price1:
                # Derive price0 from quote
                price0 = self.derive_price_from_quote(
                    token0_info["symbol"], quote_0to1, token1_info["symbol"],
                    decimals1, decimals0
                )
                if price0 and price0 > 0:
                    self.derived_prices[token0_info["symbol"]] = price0
                    print(f"  💡 Derived {token0_info['symbol']} = ${price0:.6f} from {token1_info['symbol']} quote")

            if not price1 and price0:
                # Derive price1 from quote
                price1 = self.derive_price_from_quote(
                    token1_info["symbol"], quote_1to0, token0_info["symbol"],
                    decimals0, decimals1
                )
                if price1 and price1 > 0:
                    self.derived_prices[token1_info["symbol"]] = price1
                    print(f"  💡 Derived {token1_info['symbol']} = ${price1:.6f} from {token0_info['symbol']} quote")

            # Calculate TVL if we have prices
            if price0 and price1:
                # Calculate TVL (simplified estimate)
                price_ratio = (sqrt_price_x96 / (2 ** 96)) ** 2
                price_adjusted = price_ratio * (10 ** decimals0) / (10 ** decimals1)

                if liquidity > 0:
                    tvl_token1 = 2 * ((liquidity * price_adjusted) ** 0.5)
                    tvl_usd = (tvl_token1 / (10 ** decimals1)) * price1
                else:
                    tvl_usd = 0
            else:
                # No way to calculate TVL without prices
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} (fee:{fee}) - no USD price available for both tokens")
                return None

            # Check TVL threshold (ALWAYS CHECK)
            if tvl_usd < self.min_tvl_usd:
                print(f"  ⚠️  Skipping {token0_info['symbol']}/{token1_info['symbol']} on {dex} (fee:{fee}) - TVL ${tvl_usd:,.0f} < ${self.min_tvl_usd:,.0f}")
                return None

            return {
                'pair_prices': {
                    'quote_0to1': quote_0to1,  # ACTUAL quote: 1 token0 → ? token1
                    'quote_1to0': quote_1to0,  # ACTUAL quote: 1 token1 → ? token0
                    'liquidity': liquidity,
                    'fee': fee,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'token0_address': token0_addr,
                    'token1_address': token1_addr,
                    'decimals0': decimals0,
                    'decimals1': decimals1,
                    'type': 'v3',
                    'dex': dex
                },
                'tvl_data': {
                    'tvl_usd': tvl_usd,
                    'sqrt_price_x96': sqrt_price_x96,
                    'liquidity': liquidity,
                    'token0': token0_info["symbol"],
                    'token1': token1_info["symbol"],
                    'price0_usd': price0 if price0 else 0,
                    'price1_usd': price1 if price1 else 0
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
                return self.fetch_v3_pool(w3, pool_address, dex)
            else:
                return self.fetch_v2_pool(w3, pool_address, dex)

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
            if "quickswap_v3" in dex_name.lower() or "algebra" in dex_name.lower():
                continue  # Skip Algebra protocol (v3 pools not fully supported)

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

        # Show derived prices
        if self.derived_prices:
            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"💡 ON-CHAIN DERIVED PRICES")
            print(f"{'='*80}{Style.RESET_ALL}")
            for token, price in sorted(self.derived_prices.items()):
                anchor = "🔗 ANCHOR" if token in ["USDC", "USDT", "DAI"] else "✅ DERIVED"
                print(f"   {anchor} {token:10s} = ${price:>12.6f}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Save cache
        self.cache.flush_all()

        return pools


if __name__ == "__main__":
    # Test
    rpc_mgr = RPCManager()
    cache = Cache()
    fetcher = PriceDataFetcher(rpc_mgr, cache, min_tvl_usd=3000)

    pools = fetcher.fetch_all_pools()
    print(f"\nFetched {sum(len(p) for p in pools.values())} pools")
