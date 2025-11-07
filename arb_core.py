"""
Consolidated Arbitrage Core Module
Combines pool scanning, price calculation, and arbitrage detection
with AI monitoring for every operation.

Architecture:
1. DataFetcher → Fetches pool data, caches pair prices (1hr) and TVL (3hrs)
2. ArbEngine → Reads cache, does math, finds arbs (instant, repeatable)
3. AIMonitor → Tracks every call, calculation, and decision
4. Cache expiration warnings with auto-fetch option
"""

import json
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from web3 import Web3
from colorama import Fore, Style, init

from cache import Cache
from rpc_mgr import RPCManager
from price_math import PriceCalculator
from registries import TOKENS
from price_fetcher import CoinGeckoPriceFetcher

init(autoreset=True)


# ============================================================================
# AI MONITOR - Tracks every operation for ArbiGirl queries
# ============================================================================

class AIMonitor:
    """
    Tracks every call, calculation, and decision made by the system.
    ArbiGirl can query this to answer user questions about operations.
    """

    def __init__(self, max_history: int = 10000):
        """
        Initialize AI Monitor

        Args:
            max_history: Maximum number of events to keep in memory
        """
        self.events = []
        self.max_history = max_history
        self.stats = {
            'total_fetches': 0,
            'total_calculations': 0,
            'total_arb_checks': 0,
            'total_opportunities_found': 0
        }
        print(f"{Fore.GREEN}✅ AI Monitor initialized (max history: {max_history}){Style.RESET_ALL}")

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """
        Log an event with full details

        Args:
            event_type: Type of event (fetch, calculation, arb_check, opportunity, etc.)
            details: Full details of the event
        """
        event = {
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat(),
            'type': event_type,
            'details': details
        }

        self.events.append(event)

        # Keep only recent events
        if len(self.events) > self.max_history:
            self.events = self.events[-self.max_history:]

        # Update stats
        if event_type == 'fetch':
            self.stats['total_fetches'] += 1
        elif event_type == 'calculation':
            self.stats['total_calculations'] += 1
        elif event_type == 'arb_check':
            self.stats['total_arb_checks'] += 1
        elif event_type == 'opportunity':
            self.stats['total_opportunities_found'] += 1

    def query(self, question: str) -> str:
        """
        Answer questions about operations

        Args:
            question: Natural language question from user

        Returns:
            Answer based on logged events
        """
        q_lower = question.lower()

        # Query: "what was the last fetch?"
        if 'last fetch' in q_lower or 'recent fetch' in q_lower:
            fetches = [e for e in self.events if e['type'] == 'fetch']
            if fetches:
                last = fetches[-1]
                return f"Last fetch at {last['datetime']}: {json.dumps(last['details'], indent=2)}"
            return "No fetches recorded yet"

        # Query: "how many opportunities found?"
        if 'how many opportunities' in q_lower or 'opportunities found' in q_lower:
            return f"Total opportunities found: {self.stats['total_opportunities_found']}"

        # Query: "what coins/tokens were checked?"
        if 'what coins' in q_lower or 'what tokens' in q_lower or 'which coins' in q_lower:
            tokens = set()
            for event in self.events:
                if event['type'] in ['fetch', 'calculation', 'arb_check']:
                    details = event['details']
                    if 'token0' in details:
                        tokens.add(details['token0'])
                    if 'token1' in details:
                        tokens.add(details['token1'])
                    if 'pair' in details:
                        pair_tokens = details['pair'].split('/')
                        tokens.update(pair_tokens)

            if tokens:
                return f"Tokens checked: {', '.join(sorted(tokens))}"
            return "No token data available yet"

        # Query: "what dexes were used?"
        if 'what dex' in q_lower or 'which dex' in q_lower:
            dexes = set()
            for event in self.events:
                details = event['details']
                if 'dex' in details:
                    dexes.add(details['dex'])
                if 'dex_buy' in details:
                    dexes.add(details['dex_buy'])
                if 'dex_sell' in details:
                    dexes.add(details['dex_sell'])

            if dexes:
                return f"DEXes used: {', '.join(sorted(dexes))}"
            return "No DEX data available yet"

        # Query: "show me the latest opportunities"
        if 'latest opportunities' in q_lower or 'recent opportunities' in q_lower:
            opps = [e for e in self.events if e['type'] == 'opportunity'][-5:]
            if opps:
                result = "Latest opportunities:\n"
                for i, opp in enumerate(opps, 1):
                    details = opp['details']
                    result += f"\n{i}. {details.get('pair')} - ${details.get('profit_usd', 0):.2f} profit\n"
                    result += f"   Buy: {details.get('dex_buy')} | Sell: {details.get('dex_sell')}\n"
                return result
            return "No opportunities found yet"

        # Query: "show stats"
        if 'stats' in q_lower or 'statistics' in q_lower:
            return f"""System Statistics:
  • Total fetches: {self.stats['total_fetches']:,}
  • Total calculations: {self.stats['total_calculations']:,}
  • Total arb checks: {self.stats['total_arb_checks']:,}
  • Total opportunities: {self.stats['total_opportunities_found']:,}
  • Events in memory: {len(self.events):,}"""

        # Default: show available query types
        return """Available queries:
  - "what was the last fetch?"
  - "how many opportunities found?"
  - "what coins/tokens were checked?"
  - "what dexes were used?"
  - "show me the latest opportunities"
  - "show stats"
"""

    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get recent events, optionally filtered by type"""
        if event_type:
            events = [e for e in self.events if e['type'] == event_type]
        else:
            events = self.events

        return events[-limit:]


# ============================================================================
# DATA FETCHER - Fetches and caches pool data
# ============================================================================

class DataFetcher:
    """
    Fetches pool data from blockchain and caches it.
    - Pair prices: 1 hour cache
    - TVL data: 3 hour cache
    """

    def __init__(
        self,
        rpc_manager: RPCManager,
        cache: Cache,
        ai_monitor: AIMonitor,
        pool_registry_path: str = "./pool_registry.json",
        min_tvl_usd: float = 10000
    ):
        self.rpc_manager = rpc_manager
        self.cache = cache
        self.ai_monitor = ai_monitor
        self.min_tvl_usd = min_tvl_usd

        # Load pool registry
        with open(pool_registry_path, 'r') as f:
            self.registry = json.load(f)

        # Initialize price fetcher
        self.price_fetcher = CoinGeckoPriceFetcher(cache_duration=300)

        # V2/V3 ABIs (minimal)
        self.v2_abi = [{
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
        }, {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }, {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }]

        self.v3_abi = [{
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
        }, {
            "inputs": [],
            "name": "liquidity",
            "outputs": [{"name": "", "type": "uint128"}],
            "stateMutability": "view",
            "type": "function"
        }, {
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }, {
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }]

        print(f"{Fore.GREEN}✅ Data Fetcher initialized (min TVL: ${min_tvl_usd:,}){Style.RESET_ALL}")

    def _get_token_info(self, address: str) -> Optional[Dict]:
        """Get token info from registry"""
        address = address.lower()
        for symbol, info in TOKENS.items():
            if info["address"].lower() == address:
                return {**info, "symbol": symbol}
        return None

    def fetch_pool_data(self, dex: str, pool_address: str, pool_type: str = "v2") -> Optional[Dict]:
        """
        Fetch pool data from blockchain and cache it

        Returns:
            Dict with pair_prices (1hr cache) and tvl_data (3hr cache)
        """
        # Check cache first
        pair_prices = self.cache.get_pair_prices(dex, pool_address)
        tvl_data = self.cache.get_tvl_data(dex, pool_address)

        # If both cached, return immediately
        if pair_prices and tvl_data:
            self.ai_monitor.log_event('fetch', {
                'dex': dex,
                'pool': pool_address,
                'source': 'cache',
                'has_pair_prices': True,
                'has_tvl_data': True
            })
            return {
                'pair_prices': pair_prices,
                'tvl_data': tvl_data,
                'from_cache': True
            }

        # Need to fetch from blockchain
        def fetch_func(w3):
            if pool_type == "v3":
                return self._fetch_v3_pool(w3, pool_address)
            else:
                return self._fetch_v2_pool(w3, pool_address)

        try:
            data = self.rpc_manager.execute_with_failover(fetch_func)

            if not data:
                return None

            # Separate into pair_prices and tvl_data
            pair_prices_new = {
                'reserve0': data.get('reserve0'),
                'reserve1': data.get('reserve1'),
                'sqrt_price_x96': data.get('sqrt_price_x96'),
                'liquidity': data.get('liquidity'),
                'token0': data['token0'],
                'token1': data['token1'],
                'type': pool_type
            }

            tvl_data_new = {
                'tvl_usd': data['tvl_usd'],
                'token0': data['token0'],
                'token1': data['token1'],
                'token0_address': data['token0_address'],
                'token1_address': data['token1_address']
            }

            # Cache with different durations
            self.cache.set_pair_prices(dex, pool_address, pair_prices_new)
            self.cache.set_tvl_data(dex, pool_address, tvl_data_new)

            # Log to AI monitor
            self.ai_monitor.log_event('fetch', {
                'dex': dex,
                'pool': pool_address,
                'source': 'blockchain',
                'token0': data['token0'],
                'token1': data['token1'],
                'tvl_usd': data['tvl_usd']
            })

            return {
                'pair_prices': pair_prices_new,
                'tvl_data': tvl_data_new,
                'from_cache': False
            }

        except Exception as e:
            self.ai_monitor.log_event('fetch_error', {
                'dex': dex,
                'pool': pool_address,
                'error': str(e)
            })
            return None

    def _fetch_v2_pool(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Fetch V2 pool data"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self.v2_abi
            )

            # Get reserves and tokens
            reserves = pool.functions.getReserves().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()

            # Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            # Get prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])

            if not price0 or not price1:
                return None

            # Calculate TVL
            reserve0, reserve1 = reserves[0], reserves[1]
            amount0 = reserve0 / (10 ** token0_info["decimals"])
            amount1 = reserve1 / (10 ** token1_info["decimals"])
            tvl_usd = (amount0 * price0) + (amount1 * price1)

            # Filter by min TVL
            if tvl_usd < self.min_tvl_usd:
                return None

            return {
                'reserve0': reserve0,
                'reserve1': reserve1,
                'token0': token0_info["symbol"],
                'token1': token1_info["symbol"],
                'token0_address': token0_addr,
                'token1_address': token1_addr,
                'decimals0': token0_info["decimals"],
                'decimals1': token1_info["decimals"],
                'price0': price0,
                'price1': price1,
                'tvl_usd': tvl_usd,
                'type': 'v2'
            }

        except Exception as e:
            return None

    def _fetch_v3_pool(self, w3: Web3, pool_address: str) -> Optional[Dict]:
        """Fetch V3 pool data"""
        try:
            pool = w3.eth.contract(
                address=Web3.to_checksum_address(pool_address),
                abi=self.v3_abi
            )

            # Get slot0, liquidity, and tokens
            slot0 = pool.functions.slot0().call()
            liquidity = pool.functions.liquidity().call()
            token0_addr = pool.functions.token0().call()
            token1_addr = pool.functions.token1().call()

            # Get token info
            token0_info = self._get_token_info(token0_addr)
            token1_info = self._get_token_info(token1_addr)

            if not token0_info or not token1_info:
                return None

            # Get prices
            price0 = self.price_fetcher.get_price(token0_info["symbol"])
            price1 = self.price_fetcher.get_price(token1_info["symbol"])

            if not price0 or not price1:
                return None

            # Calculate TVL (simplified estimate)
            sqrt_price_x96 = slot0[0]
            price_ratio = (sqrt_price_x96 / (2 ** 96)) ** 2
            decimals0 = token0_info["decimals"]
            decimals1 = token1_info["decimals"]
            price_adjusted = price_ratio * (10 ** decimals0) / (10 ** decimals1)

            if liquidity > 0:
                tvl_token1 = 2 * ((liquidity * price_adjusted) ** 0.5)
                tvl_usd = (tvl_token1 / (10 ** decimals1)) * price1
            else:
                tvl_usd = 0

            # Filter by min TVL
            if tvl_usd < self.min_tvl_usd:
                return None

            return {
                'sqrt_price_x96': sqrt_price_x96,
                'liquidity': liquidity,
                'token0': token0_info["symbol"],
                'token1': token1_info["symbol"],
                'token0_address': token0_addr,
                'token1_address': token1_addr,
                'decimals0': decimals0,
                'decimals1': decimals1,
                'price0': price0,
                'price1': price1,
                'tvl_usd': tvl_usd,
                'type': 'v3'
            }

        except Exception as e:
            return None

    def fetch_all_pools(self) -> Dict[str, Dict]:
        """
        Fetch all pools from registry
        Uses cache when available (1hr for prices, 3hr for TVL)
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔍 FETCHING POOL DATA")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        filtered_pools = {}
        total_checked = 0
        valid_pools = 0
        cached_count = 0

        for dex_name, pairs in self.registry.items():
            if "quickswap_v3" in dex_name.lower():
                continue  # Skip Algebra protocol

            print(f"\n{Fore.BLUE}📊 {dex_name}{Style.RESET_ALL}")
            filtered_pools[dex_name] = {}

            for pair_name, pool_data in pairs.items():
                if "pool" in pool_data:
                    # V2 pool
                    total_checked += 1
                    pool_addr = pool_data["pool"]

                    data = self.fetch_pool_data(dex_name, pool_addr, pool_data.get("type", "v2"))

                    if data:
                        filtered_pools[dex_name][pair_name] = {
                            **pool_data,
                            'data': data
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
        print(f"   From cache: {cached_count:,}")
        print(f"   From blockchain: {valid_pools - cached_count:,}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        return filtered_pools


# ============================================================================
# ARB ENGINE - Finds arbitrage opportunities from cached data
# ============================================================================

class ArbEngine:
    """
    Finds arbitrage opportunities using cached pool data.
    Instant and repeatable since it only reads from cache.
    """

    def __init__(self, ai_monitor: AIMonitor, min_profit_usd: float = 1.0):
        self.ai_monitor = ai_monitor
        self.min_profit_usd = min_profit_usd

        # Test amounts
        self.test_amounts_usd = [1000, 10000, 100000]

        print(f"{Fore.GREEN}✅ Arb Engine initialized (min profit: ${min_profit_usd}){Style.RESET_ALL}")

    def calculate_v2_output(self, amount_in: int, reserve_in: int, reserve_out: int, fee_bps: int = 30) -> int:
        """Calculate V2 output using constant product formula"""
        if amount_in == 0 or reserve_in == 0 or reserve_out == 0:
            return 0

        amount_in_with_fee = amount_in * (10000 - fee_bps)
        numerator = amount_in_with_fee * reserve_out
        denominator = (reserve_in * 10000) + amount_in_with_fee

        if denominator == 0:
            return 0

        return numerator // denominator

    def find_opportunities(self, pools: Dict[str, Dict]) -> List[Dict]:
        """
        Find arbitrage opportunities from pool data

        Args:
            pools: Dict of {dex_name: {pair_name: pool_data}}

        Returns:
            List of arbitrage opportunities
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💰 SCANNING FOR ARBITRAGE")
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

        # Check each pair with 2+ pools
        for pair_name, pair_pools_list in pair_pools.items():
            if len(pair_pools_list) < 2:
                continue

            self.ai_monitor.log_event('arb_check', {
                'pair': pair_name,
                'pool_count': len(pair_pools_list)
            })

            # Try different trade sizes
            for amount_usd in self.test_amounts_usd:
                opp = self._check_pair_arbitrage(pair_name, pair_pools_list, amount_usd)

                if opp and opp['profit_usd'] >= self.min_profit_usd:
                    opportunities.append(opp)

                    # Log opportunity to AI monitor
                    self.ai_monitor.log_event('opportunity', {
                        'pair': opp['pair'],
                        'dex_buy': opp['dex_buy'],
                        'dex_sell': opp['dex_sell'],
                        'profit_usd': opp['profit_usd'],
                        'roi_percent': opp['roi_percent'],
                        'trade_size_usd': amount_usd
                    })

        # Sort by profit
        opportunities.sort(key=lambda x: x['profit_usd'], reverse=True)

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"✅ Found {len(opportunities)} opportunities")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        return opportunities

    def _check_pair_arbitrage(self, pair_name: str, pools: List[Dict], amount_usd: float) -> Optional[Dict]:
        """Check arbitrage for a specific pair and amount"""
        # Get quotes from each pool
        quotes = []

        for pool in pools:
            pool_data = pool['pool_data']

            # Get pair prices from cached data
            if 'data' not in pool_data or 'pair_prices' not in pool_data['data']:
                continue

            pair_prices = pool_data['data']['pair_prices']

            # Simple price check (you can extend this with actual AMM calculations)
            # For V2: use reserves
            if pair_prices.get('type') == 'v2':
                reserve0 = pair_prices.get('reserve0')
                reserve1 = pair_prices.get('reserve1')

                if reserve0 and reserve1:
                    # Price: token1 per token0
                    price = reserve1 / reserve0 if reserve0 > 0 else 0

                    quotes.append({
                        'dex': pool['dex'],
                        'price': price,
                        'reserves': (reserve0, reserve1)
                    })

        if len(quotes) < 2:
            return None

        # Find best buy (lowest price) and sell (highest price)
        best_buy = min(quotes, key=lambda x: x['price'])
        best_sell = max(quotes, key=lambda x: x['price'])

        # Calculate profit
        if best_sell['price'] <= best_buy['price']:
            return None

        profit_ratio = (best_sell['price'] - best_buy['price']) / best_buy['price']
        profit_usd = profit_ratio * amount_usd

        if profit_usd < self.min_profit_usd:
            return None

        return {
            'pair': pair_name,
            'dex_buy': best_buy['dex'],
            'dex_sell': best_sell['dex'],
            'buy_price': best_buy['price'],
            'sell_price': best_sell['price'],
            'profit_usd': profit_usd,
            'roi_percent': profit_ratio * 100,
            'trade_size_usd': amount_usd
        }


# ============================================================================
# CONSOLIDATED ARB SYSTEM - Main interface
# ============================================================================

class ConsolidatedArbSystem:
    """
    Main interface for the consolidated arbitrage system.
    ArbiGirl uses this to run components independently or together.
    """

    def __init__(
        self,
        rpc_manager: Optional[RPCManager] = None,
        cache: Optional[Cache] = None,
        min_tvl_usd: float = 10000,
        min_profit_usd: float = 1.0
    ):
        # Initialize dependencies
        self.rpc_manager = rpc_manager or RPCManager()
        self.cache = cache or Cache(cache_dir="./cache")

        # Initialize AI Monitor
        self.ai_monitor = AIMonitor(max_history=10000)

        # Initialize components
        self.data_fetcher = DataFetcher(
            self.rpc_manager,
            self.cache,
            self.ai_monitor,
            min_tvl_usd=min_tvl_usd
        )

        self.arb_engine = ArbEngine(
            self.ai_monitor,
            min_profit_usd=min_profit_usd
        )

        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"✅ CONSOLIDATED ARB SYSTEM INITIALIZED")
        print(f"{'='*80}{Style.RESET_ALL}\n")

    def fetch_pools(self) -> Dict:
        """Step 1: Fetch pool data (uses cache when available)"""
        return self.data_fetcher.fetch_all_pools()

    def find_arbitrage(self, pools: Dict) -> List[Dict]:
        """Step 2: Find arbitrage from cached pool data (instant)"""
        return self.arb_engine.find_opportunities(pools)

    def run_full_scan(self) -> List[Dict]:
        """Run complete scan: fetch pools + find arbitrage"""
        # Check cache status
        warning = self.cache.get_expiration_warning()
        if warning:
            print(f"\n{Fore.YELLOW}{'='*80}")
            print(f"⚠️  CACHE EXPIRATION WARNING")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(warning)
            print(f"\n{Fore.YELLOW}Data may be stale. Consider fetching fresh data.{Style.RESET_ALL}\n")

        # Step 1: Fetch pools
        pools = self.fetch_pools()

        # Step 2: Find arbitrage
        opportunities = self.find_arbitrage(pools)

        return opportunities

    def ask_arbigirl(self, question: str) -> str:
        """Ask ArbiGirl a question about operations"""
        return self.ai_monitor.query(question)

    def check_cache_status(self) -> Dict:
        """Check cache expiration status"""
        return self.cache.check_expiration_status()

    def get_ai_stats(self) -> Dict:
        """Get AI monitor statistics"""
        return self.ai_monitor.stats


if __name__ == "__main__":
    # Example usage
    system = ConsolidatedArbSystem(
        min_tvl_usd=10000,
        min_profit_usd=1.0
    )

    # Run a scan
    opportunities = system.run_full_scan()

    # Ask ArbiGirl questions
    print(f"\n{Fore.MAGENTA}ArbiGirl: {system.ask_arbigirl('show stats')}{Style.RESET_ALL}")
