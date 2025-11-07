"""
AI Monitor
Tracks every operation, calculation, and decision.
ArbiGirl can query this to answer any question about what's happening.
"""

import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)


class AIMonitor:
    """
    Tracks ALL operations for ArbiGirl to query.
    Stores: fetches, calculations, opportunities, errors, etc.
    """

    def __init__(self, max_history: int = 10000):
        """
        Initialize AI Monitor

        Args:
            max_history: Maximum number of events to keep in memory
        """
        self.events = []
        self.max_history = max_history

        # Statistics
        self.stats = {
            'total_fetches': 0,
            'total_calculations': 0,
            'total_arb_checks': 0,
            'total_opportunities': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }

        # Current session data
        self.current_pools = {}
        self.current_opportunities = []

        print(f"{Fore.GREEN}✅ AI Monitor initialized (history: {max_history}){Style.RESET_ALL}")

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """
        Log an event with full details

        Args:
            event_type: Type (fetch, calculation, opportunity, cache_hit, etc.)
            details: Full event details
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
            self.stats['total_opportunities'] += 1
        elif event_type == 'cache_hit':
            self.stats['cache_hits'] += 1
        elif event_type == 'cache_miss':
            self.stats['cache_misses'] += 1

    def update_pools(self, pools: Dict):
        """Store current pool data"""
        self.current_pools = pools

    def update_opportunities(self, opportunities: List[Dict]):
        """Store current opportunities"""
        self.current_opportunities = opportunities

    def query(self, question: str) -> str:
        """
        Answer questions about operations

        Args:
            question: Natural language question

        Returns:
            Answer based on logged data
        """
        q_lower = question.lower()

        # Stats query
        if 'stats' in q_lower or 'statistics' in q_lower:
            total_cache = self.stats['cache_hits'] + self.stats['cache_misses']
            hit_rate = (self.stats['cache_hits'] / total_cache * 100) if total_cache > 0 else 0

            return f"""System Statistics:
  • Total fetches: {self.stats['total_fetches']:,}
  • Total calculations: {self.stats['total_calculations']:,}
  • Total arb checks: {self.stats['total_arb_checks']:,}
  • Total opportunities: {self.stats['total_opportunities']:,}
  • Cache hits: {self.stats['cache_hits']:,}
  • Cache misses: {self.stats['cache_misses']:,}
  • Cache hit rate: {hit_rate:.1f}%
  • Events in memory: {len(self.events):,}"""

        # Coins/tokens query
        if 'coins' in q_lower or 'tokens' in q_lower or 'which coins' in q_lower:
            tokens = set()
            for event in self.events:
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

        # DEX query
        if 'dex' in q_lower or 'exchange' in q_lower:
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

        # Latest opportunities
        if 'opportunities' in q_lower or 'arb' in q_lower:
            if self.current_opportunities:
                result = f"Latest opportunities ({len(self.current_opportunities)} found):\n"
                for i, opp in enumerate(self.current_opportunities[:5], 1):
                    result += f"\n{i}. {opp.get('pair')} - ${opp.get('profit_usd', 0):.2f} profit ({opp.get('roi_percent', 0):.2f}% ROI)\n"
                    result += f"   Buy: {opp.get('dex_buy')} @ {opp.get('buy_price', 0):.8f}\n"
                    result += f"   Sell: {opp.get('dex_sell')} @ {opp.get('sell_price', 0):.8f}\n"
                return result
            return "No opportunities found yet"

        # Latest fetch
        if 'last fetch' in q_lower or 'recent fetch' in q_lower:
            fetches = [e for e in self.events if e['type'] == 'fetch']
            if fetches:
                last = fetches[-1]
                return f"Last fetch at {last['datetime']}: {json.dumps(last['details'], indent=2)}"
            return "No fetches recorded yet"

        # How many pools
        if 'how many pools' in q_lower or 'pool count' in q_lower:
            pool_count = sum(len(pairs) for pairs in self.current_pools.values())
            return f"Currently tracking {pool_count} pools across {len(self.current_pools)} DEXes"

        # Calculation details
        if 'calculation' in q_lower or 'math' in q_lower:
            calcs = [e for e in self.events if e['type'] == 'calculation'][-5:]
            if calcs:
                result = "Recent calculations:\n"
                for calc in calcs:
                    details = calc['details']
                    result += f"\n• {calc['datetime']}: {details.get('description', 'N/A')}\n"
                    result += f"  Input: {details.get('amount_in', 0):,}\n"
                    result += f"  Output: {details.get('amount_out', 0):,}\n"
                return result
            return "No calculations recorded yet"

        # Cache info
        if 'cache' in q_lower:
            cache_events = [e for e in self.events if e['type'] in ['cache_hit', 'cache_miss']][-10:]
            if cache_events:
                result = "Recent cache activity:\n"
                for event in cache_events:
                    event_type = "HIT" if event['type'] == 'cache_hit' else "MISS"
                    details = event['details']
                    result += f"\n• {event_type}: {details.get('dex', 'N/A')} / {details.get('pool', 'N/A')}\n"
                return result
            return "No cache activity recorded yet"

        # Default
        return f"""I track all operations! Ask me:
  • "show stats" - System statistics
  • "what coins were checked?" - List of tokens
  • "what dexes were used?" - List of DEXes
  • "show opportunities" - Latest arbitrage opportunities
  • "how many pools?" - Pool count
  • "show calculations" - Recent calculations
  • "show cache activity" - Cache hits/misses
  • "when was the last fetch?" - Latest fetch details"""

    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get recent events, optionally filtered by type"""
        if event_type:
            events = [e for e in self.events if e['type'] == event_type]
        else:
            events = self.events

        return events[-limit:]

    def clear_history(self):
        """Clear event history (keeps stats)"""
        self.events = []
        print(f"{Fore.YELLOW}Event history cleared{Style.RESET_ALL}")


# Global AI monitor instance
_global_monitor = None

def get_monitor() -> AIMonitor:
    """Get or create global AI monitor"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = AIMonitor()
    return _global_monitor
