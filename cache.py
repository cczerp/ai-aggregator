"""
Production Cache System
- Time-based only (no session resets)
- Multiple cache durations per data type
- Persistent across restarts
- Checks cache first always
"""
import json
import os
import time
from typing import Optional, Dict, Any
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)


class Cache:
    """Multi-duration cache system with timestamp-based expiration"""

    # Cache durations (in seconds) - OPTIMIZED FOR REAL-TIME ARBITRAGE ⚡
    DURATIONS = {
        'pair_prices': 10,                    # 10 seconds - pair price data (CRITICAL!)
        'tvl_data': 5 * 60,                   # 5 minutes - TVL/liquidity data
        'pool_registry': 10 * 60,             # 10 minutes - pool registry (TVL)
        'dex_health': 30 * 24 * 3600,         # 30 days - DEX health status
        'oracle': 30,                         # 30 seconds - oracle price feeds
        'router_gas': 2 * 60,                 # 2 minutes - gas estimates
        'arb_opportunity': 5,                 # 5 seconds - opportunities (VERY volatile!)
        'default': 60                         # 60 seconds - fallback
    }
    
    def __init__(self, cache_dir: str = "./cache"):
        """Initialize cache system"""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Separate files for different cache types
        self.cache_files = {
            'pair_prices': self.cache_dir / "pair_prices_cache.json",
            'tvl_data': self.cache_dir / "tvl_data_cache.json",
            'pool_registry': self.cache_dir / "pool_registry_cache.json",
            'dex_health': self.cache_dir / "dex_health_cache.json",
            'oracle': self.cache_dir / "oracle_cache.json",
            'router_gas': self.cache_dir / "router_gas_cache.json",
            'arb_opportunity': self.cache_dir / "arb_cache.json",
            'default': self.cache_dir / "general_cache.json"
        }
        
        # Load all caches
        self.caches = {}
        for cache_type, filepath in self.cache_files.items():
            self.caches[cache_type] = self._load_cache(filepath)
        
        # Statistics per cache type
        self.stats = {cache_type: {'hits': 0, 'misses': 0, 'writes': 0} 
                     for cache_type in self.cache_files.keys()}
        
        print(f"{Fore.GREEN}✅ Cache System Initialized (REAL-TIME MODE){Style.RESET_ALL}")
        print(f"   Location: {self.cache_dir}")
        for cache_type, duration in self.DURATIONS.items():
            count = len(self.caches.get(cache_type, {}))
            # Format duration appropriately
            if duration >= 86400:
                duration_str = f"{duration/86400:.0f}d"
            elif duration >= 3600:
                duration_str = f"{duration/3600:.1f}h"
            elif duration >= 60:
                duration_str = f"{duration/60:.0f}m"
            else:
                duration_str = f"{duration:.0f}s"
            print(f"   • {cache_type}: {count} entries ({duration_str})")
    
    def _load_cache(self, filepath: Path) -> Dict:
        """Load cache from disk"""
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_cache(self, cache_type: str):
        """Save specific cache to disk"""
        filepath = self.cache_files.get(cache_type, self.cache_files['default'])
        try:
            with open(filepath, 'w') as f:
                json.dump(self.caches[cache_type], f, indent=2)
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to save {cache_type} cache: {e}{Style.RESET_ALL}")
    
    def _make_key(self, *args) -> str:
        """Create cache key from arguments"""
        return ':'.join(str(arg).lower() for arg in args)
    
    def get(self, cache_type: str, *key_parts) -> Optional[Any]:
        """
        Get cached data - ALWAYS CHECK CACHE FIRST
        
        Args:
            cache_type: 'pool_registry', 'oracle', 'router_gas', 'arb_opportunity', etc.
            *key_parts: Key components (dex, pool, token, etc.)
        
        Returns:
            Cached data or None if expired/missing
        """
        cache = self.caches.get(cache_type, {})
        key = self._make_key(*key_parts)
        
        if key not in cache:
            self.stats[cache_type]['misses'] += 1
            return None
        
        entry = cache[key]
        timestamp = entry.get('timestamp', 0)
        duration = self.DURATIONS.get(cache_type, self.DURATIONS['default'])
        
        # Check if expired (TIME-BASED ONLY)
        if time.time() - timestamp > duration:
            self.stats[cache_type]['misses'] += 1
            del cache[key]
            self._save_cache(cache_type)
            return None
        
        # Valid cache hit
        self.stats[cache_type]['hits'] += 1
        return entry.get('data')
    
    def set(self, cache_type: str, data: Any, *key_parts):
        """
        Save data to cache with timestamp
        
        Args:
            cache_type: Cache category
            data: Data to cache
            *key_parts: Key components
        """
        if cache_type not in self.caches:
            self.caches[cache_type] = {}
        
        key = self._make_key(*key_parts)
        
        self.caches[cache_type][key] = {
            'timestamp': time.time(),
            'data': data
        }
        
        self.stats[cache_type]['writes'] += 1
        
        # Auto-save every 5 writes
        if self.stats[cache_type]['writes'] % 5 == 0:
            self._save_cache(cache_type)
    
    def is_cached(self, cache_type: str, *key_parts) -> bool:
        """Check if data is cached and valid"""
        return self.get(cache_type, *key_parts) is not None
    
    def get_pair_prices(self, dex: str, pool: str) -> Optional[Dict]:
        """Get pair price data (10-second cache - REAL-TIME!)"""
        return self.get('pair_prices', dex, pool)

    def set_pair_prices(self, dex: str, pool: str, data: Dict):
        """Cache pair price data"""
        self.set('pair_prices', data, dex, pool)

    def get_tvl_data(self, dex: str, pool: str) -> Optional[Dict]:
        """Get pool TVL data (5-minute cache)"""
        return self.get('tvl_data', dex, pool)

    def set_tvl_data(self, dex: str, pool: str, data: Dict):
        """Cache pool TVL data"""
        self.set('tvl_data', data, dex, pool)

    def get_pool_liquidity(self, dex: str, pool: str) -> Optional[Dict]:
        """Get pool liquidity/TVL (5-minute cache) - legacy alias"""
        return self.get('tvl_data', dex, pool)

    def set_pool_liquidity(self, dex: str, pool: str, data: Dict):
        """Cache pool liquidity/TVL - legacy alias"""
        self.set('tvl_data', data, dex, pool)

    def get_oracle_price(self, token: str) -> Optional[float]:
        """Get token price (30-second cache)"""
        return self.get('oracle', token)

    def set_oracle_price(self, token: str, price: float):
        """Cache token price"""
        self.set('oracle', price, token)

    def get_router_gas(self, dex: str) -> Optional[int]:
        """Get router gas estimate (2-minute cache)"""
        return self.get('router_gas', dex)
    
    def set_router_gas(self, dex: str, gas: int):
        """Cache router gas estimate"""
        self.set('router_gas', gas, dex)
    
    def get_dex_health(self, dex: str) -> Optional[Dict]:
        """Get DEX health status (30-day cache)"""
        return self.get('dex_health', dex)
    
    def set_dex_health(self, dex: str, health: Dict):
        """Cache DEX health status"""
        self.set('dex_health', health, dex)
    
    def cleanup_expired(self, cache_type: Optional[str] = None):
        """Remove expired entries from cache(s)"""
        types_to_clean = [cache_type] if cache_type else list(self.caches.keys())
        
        total_removed = 0
        for ctype in types_to_clean:
            cache = self.caches.get(ctype, {})
            duration = self.DURATIONS.get(ctype, self.DURATIONS['default'])
            now = time.time()
            
            expired = [
                key for key, entry in cache.items()
                if now - entry.get('timestamp', 0) > duration
            ]
            
            for key in expired:
                del cache[key]
            
            if expired:
                self._save_cache(ctype)
                total_removed += len(expired)
        
        if total_removed > 0:
            print(f"{Fore.YELLOW}🧹 Cleaned {total_removed} expired entries{Style.RESET_ALL}")
        
        return total_removed
    
    def flush_all(self):
        """Force save all caches to disk immediately"""
        for cache_type in self.caches.keys():
            self._save_cache(cache_type)
        print(f"{Fore.GREEN}💾 All caches flushed to disk{Style.RESET_ALL}")
    
    def clear_cache_type(self, cache_type: str):
        """Clear specific cache type"""
        if cache_type in self.caches:
            self.caches[cache_type] = {}
            self._save_cache(cache_type)
            print(f"{Fore.YELLOW}🧹 Cleared {cache_type} cache{Style.RESET_ALL}")
    
    def print_stats(self):
        """Print cache statistics"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💾 CACHE STATISTICS")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        
        for cache_type in sorted(self.caches.keys()):
            cache = self.caches[cache_type]
            stats = self.stats[cache_type]
            
            total_requests = stats['hits'] + stats['misses']
            hit_rate = (stats['hits'] / max(total_requests, 1)) * 100
            
            duration = self.DURATIONS.get(cache_type, self.DURATIONS['default'])
            if duration >= 86400:
                duration_str = f"{duration/86400:.0f}d"
            else:
                duration_str = f"{duration/3600:.0f}h"
            
            print(f"   {Fore.YELLOW}{cache_type.upper()}{Style.RESET_ALL}")
            print(f"      Entries: {len(cache):,}")
            print(f"      Duration: {duration_str}")
            print(f"      Hits: {stats['hits']:,}")
            print(f"      Misses: {stats['misses']:,}")
            print(f"      Hit Rate: {hit_rate:.1f}%")
            print()
        
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
    
    def check_expiration_status(self) -> Dict[str, Dict]:
        """
        Check expiration status of all cache types
        Returns dict with cache_type -> {expired: bool, time_remaining: seconds, percentage_fresh: float}
        """
        status = {}
        now = time.time()

        for cache_type, cache_data in self.caches.items():
            if not cache_data:
                status[cache_type] = {
                    'expired': True,
                    'time_remaining': 0,
                    'percentage_fresh': 0,
                    'entry_count': 0
                }
                continue

            duration = self.DURATIONS.get(cache_type, self.DURATIONS['default'])

            # Check freshest entry
            freshest_time = max(
                (entry.get('timestamp', 0) for entry in cache_data.values()),
                default=0
            )

            time_since_freshest = now - freshest_time
            time_remaining = max(0, duration - time_since_freshest)
            expired = time_remaining == 0
            percentage_fresh = max(0, (1 - time_since_freshest / duration) * 100) if duration > 0 else 0

            status[cache_type] = {
                'expired': expired,
                'time_remaining': time_remaining,
                'percentage_fresh': percentage_fresh,
                'entry_count': len(cache_data),
                'duration': duration
            }

        return status

    def get_expiration_warning(self) -> Optional[str]:
        """
        Get warning message if any critical caches are expiring soon or expired
        Returns None if all caches are healthy
        """
        status = self.check_expiration_status()
        warnings = []

        critical_caches = ['pair_prices', 'tvl_data', 'pool_registry']

        for cache_type in critical_caches:
            cache_status = status.get(cache_type, {})

            if cache_status.get('expired'):
                duration_str = f"{cache_status.get('duration', 0) / 3600:.0f}h"
                warnings.append(
                    f"❌ {cache_type.upper()}: EXPIRED (duration: {duration_str})"
                )
            elif cache_status.get('time_remaining', 0) < 300:  # < 5 minutes
                time_left = cache_status.get('time_remaining', 0)
                warnings.append(
                    f"⚠️  {cache_type.upper()}: Expiring in {time_left/60:.1f} minutes"
                )

        if warnings:
            return "\n".join(warnings)
        return None

    def __del__(self):
        """Save all caches on exit"""
        self.flush_all()


# Global cache instance - use this everywhere
_global_cache = None

def get_cache(cache_dir: str = "./cache") -> Cache:
    """Get or create global cache instance"""
    global _global_cache
    if _global_cache is None:
        _global_cache = Cache(cache_dir=cache_dir)
    return _global_cache
