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
    
    # Cache durations (in seconds)
    DURATIONS = {
        'pool_registry': 30 * 24 * 3600,    # 30 days - TVL/liquidity data
        'dex_health': 30 * 24 * 3600,        # 30 days - same as pool registry
        'oracle': 1 * 3600,                   # 1 hour - price feeds
        'router_gas': 12 * 3600,              # 12 hours - gas estimates
        'arb_opportunity': 5 * 60,            # 5 minutes - opportunities
        'default': 24 * 3600                  # 24 hours - fallback
    }
    
    def __init__(self, cache_dir: str = "./cache"):
        """Initialize cache system"""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Separate files for different cache types
        self.cache_files = {
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
        
        print(f"{Fore.GREEN}✅ Cache System Initialized{Style.RESET_ALL}")
        print(f"   Location: {self.cache_dir}")
        for cache_type, duration in self.DURATIONS.items():
            count = len(self.caches.get(cache_type, {}))
            hours = duration / 3600
            if hours >= 24:
                duration_str = f"{hours/24:.0f}d"
            else:
                duration_str = f"{hours:.0f}h"
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
    
    def get_pool_liquidity(self, dex: str, pool: str) -> Optional[Dict]:
        """Get pool liquidity/TVL (30-day cache)"""
        return self.get('pool_registry', dex, pool)
    
    def set_pool_liquidity(self, dex: str, pool: str, data: Dict):
        """Cache pool liquidity/TVL"""
        self.set('pool_registry', data, dex, pool)
    
    def get_oracle_price(self, token: str) -> Optional[float]:
        """Get token price (1-hour cache)"""
        return self.get('oracle', token)
    
    def set_oracle_price(self, token: str, price: float):
        """Cache token price"""
        self.set('oracle', price, token)
    
    def get_router_gas(self, dex: str) -> Optional[int]:
        """Get router gas estimate (12-hour cache)"""
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
