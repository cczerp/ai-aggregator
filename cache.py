# cache.py
"""
Persistent disk cache for pool liquidity data
Saves to JSON and survives bot restarts
"""
import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict
from colorama import Fore, Style


class Cache:
    """Persistent cache with automatic expiration"""
    
    def __init__(self, cache_dir: str = "./cache", cache_duration_hours: int = 24):
        self.cache_dir = cache_dir
        self.cache_duration = cache_duration_hours * 3600  # Convert to seconds
        self.cache_file = os.path.join(cache_dir, "liquidity_cache.json")
        
        # Stats
        self.hits = 0
        self.misses = 0
        self.writes = 0
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Load existing cache
        self.data = self._load_cache()
        
        print(f"{Fore.GREEN}✅ Cache Initialized{Style.RESET_ALL}")
        print(f"   Location: {self.cache_file}")
        print(f"   Duration: {cache_duration_hours}h")
        print(f"   Existing entries: {len(self.data)}")
    
    def _load_cache(self) -> Dict:
        """Load cache from disk"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  Failed to load cache: {e}{Style.RESET_ALL}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to disk"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to save cache: {e}{Style.RESET_ALL}")
    
    def _make_key(self, dex_name: str, pool_address: str) -> str:
        """Create cache key"""
        return f"{dex_name}:{pool_address.lower()}"
    
    def get(self, dex_name: str, pool_address: str) -> Optional[Dict]:
        """Get cached data if valid"""
        key = self._make_key(dex_name, pool_address)
        
        if key not in self.data:
            self.misses += 1
            return None
        
        entry = self.data[key]
        timestamp = entry.get("timestamp", 0)
        
        # Check if expired
        if time.time() - timestamp > self.cache_duration:
            self.misses += 1
            del self.data[key]
            self._save_cache()
            return None
        
        # Valid cache hit
        self.hits += 1
        return entry.get("data")
    
    def set(self, dex_name: str, pool_address: str, data: Dict):
        """Set cached data"""
        key = self._make_key(dex_name, pool_address)
        
        self.data[key] = {
            "timestamp": time.time(),
            "data": data
        }
        
        self.writes += 1
        
        # Save to disk every 5 writes (more frequent than before)
        if self.writes % 5 == 0:
            self._save_cache()
    
    def flush(self):
        """Force save cache to disk immediately"""
        self._save_cache()
        print(f"{Fore.GREEN}💾 Cache flushed to disk ({len(self.data)} entries){Style.RESET_ALL}")
    
    def is_cached(self, dex_name: str, pool_address: str) -> bool:
        """Check if data is cached and valid"""
        key = self._make_key(dex_name, pool_address)
        
        if key not in self.data:
            return False
        
        timestamp = self.data[key].get("timestamp", 0)
        return time.time() - timestamp <= self.cache_duration
    
    def cleanup_expired(self) -> int:
        """Remove expired entries"""
        now = time.time()
        expired_keys = [
            key for key, entry in self.data.items()
            if now - entry.get("timestamp", 0) > self.cache_duration
        ]
        
        for key in expired_keys:
            del self.data[key]
        
        if expired_keys:
            self._save_cache()
        
        return len(expired_keys)
    
    def clear(self):
        """Clear all cache"""
        self.data = {}
        self._save_cache()
        self.hits = 0
        self.misses = 0
        self.writes = 0
    
    def print_stats(self):
        """Print cache statistics"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💾 CACHE STATISTICS")
        print(f"{'='*80}{Style.RESET_ALL}")
        
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / max(total_requests, 1)) * 100
        
        print(f"   Cache Hits: {self.hits:,}")
        print(f"   Cache Misses: {self.misses:,}")
        print(f"   Cache Writes: {self.writes:,}")
        print(f"   Hit Rate: {hit_rate:.1f}%")
        print(f"   Total Entries: {len(self.data):,}")
        print(f"   Cache Duration: {self.cache_duration / 3600:.0f}h")
        
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
    
    def __del__(self):
        """Save cache on exit"""
        self._save_cache()