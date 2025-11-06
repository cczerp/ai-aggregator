# persistent_cache.py
"""
Persistent Cache Manager
- Saves liquidity data to disk
- Survives bot restarts
- Time-based expiration
- Automatic cleanup of stale data
"""
import json
import os
import builtins  # FIX: for open() error
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from colorama import Fore, Style

class PersistentCache:
    """Disk-based cache with timestamp tracking"""
    
    def __init__(self, cache_dir: str = "./cache", cache_duration_hours: int = 24):
        """
        Initialize persistent cache
        
        Args:
            cache_dir: Directory to store cache files
            cache_duration_hours: How long cache entries are valid
        """
        self.cache_dir = Path(cache_dir)
        self.cache_duration = timedelta(hours=cache_duration_hours)
        
        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache file paths
        self.liquidity_cache_file = self.cache_dir / "liquidity_cache.json"
        self.metadata_file = self.cache_dir / "cache_metadata.json"
        
        # Load existing cache
        self.liquidity_cache = self._load_cache()
        self.metadata = self._load_metadata()
        
        print(f"{Fore.GREEN}✅ Persistent cache initialized{Style.RESET_ALL}")
        print(f"   Directory: {self.cache_dir}")
        print(f"   Duration: {cache_duration_hours}h")
        print(f"   Existing entries: {len(self.liquidity_cache)}")
    
    def _load_cache(self) -> Dict:
        """Load cache from disk"""
        if self.liquidity_cache_file.exists():
            try:
                with builtins.open(self.liquidity_cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  Could not load cache: {e}{Style.RESET_ALL}")
                return {}
        return {}
    
    def _load_metadata(self) -> Dict:
        """Load metadata from disk"""
        if self.metadata_file.exists():
            try:
                with builtins.open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"{Fore.YELLOW}⚠️  Could not load metadata: {e}{Style.RESET_ALL}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to disk"""
        try:
            with builtins.open(self.liquidity_cache_file, 'w') as f:
                json.dump(self.liquidity_cache, f, indent=2)
        except Exception as e:
            print(f"{Fore.RED}❌ Could not save cache: {e}{Style.RESET_ALL}")
    
    def _save_metadata(self):
        """Save metadata to disk"""
        try:
            with builtins.open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            print(f"{Fore.RED}❌ Could not save metadata: {e}{Style.RESET_ALL}")
    
    def get_liquidity(self, dex: str, pool_address: str) -> Optional[Dict]:
        """
        Get liquidity data from cache
        
        Returns None if not cached or expired
        """
        cache_key = f"{dex}:{pool_address}"
        
        if cache_key not in self.liquidity_cache:
            return None
        
        entry = self.liquidity_cache[cache_key]
        
        # Check expiration
        cached_time = datetime.fromisoformat(entry["timestamp"])
        if datetime.now() - cached_time > self.cache_duration:
            # Expired
            return None
        
        return entry["data"]
    
    def set_liquidity(self, dex: str, pool_address: str, data: Dict):
        """
        Save liquidity data to cache
        """
        cache_key = f"{dex}:{pool_address}"
        
        self.liquidity_cache[cache_key] = {
            "timestamp": datetime.now().isoformat(),
            "dex": dex,
            "pool": pool_address,
            "data": data
        }
        
        # Save to disk
        self._save_cache()
    
    def is_cached(self, dex: str, pool_address: str) -> bool:
        """Check if pool is cached and valid"""
        return self.get_liquidity(dex, pool_address) is not None
    
    def get_cache_age(self, dex: str, pool_address: str) -> Optional[float]:
        """Get age of cached entry in hours"""
        cache_key = f"{dex}:{pool_address}"
        
        if cache_key not in self.liquidity_cache:
            return None
        
        cached_time = datetime.fromisoformat(self.liquidity_cache[cache_key]["timestamp"])
        age = datetime.now() - cached_time
        return age.total_seconds() / 3600  # hours
    
    def cleanup_expired(self) -> int:
        """Remove expired entries from cache"""
        expired_keys = []
        
        for key, entry in self.liquidity_cache.items():
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if datetime.now() - cached_time > self.cache_duration:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.liquidity_cache[key]
        
        if expired_keys:
            self._save_cache()
            print(f"{Fore.YELLOW}🧹 Cleaned up {len(expired_keys)} expired cache entries{Style.RESET_ALL}")
        
        return len(expired_keys)
    
    def clear_all(self):
        """Clear all cache data"""
        self.liquidity_cache = {}
        self._save_cache()
        print(f"{Fore.YELLOW}🧹 Cache cleared{Style.RESET_ALL}")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total = len(self.liquidity_cache)
        expired = 0
        valid = 0
        
        for entry in self.liquidity_cache.values():
            cached_time = datetime.fromisoformat(entry["timestamp"])
            if datetime.now() - cached_time > self.cache_duration:
                expired += 1
            else:
                valid += 1
        
        return {
            "total_entries": total,
            "valid": valid,
            "expired": expired,
            "cache_dir": str(self.cache_dir),
            "cache_duration_hours": self.cache_duration.total_seconds() / 3600
        }
    
    def print_stats(self):
        """Print cache statistics"""
        stats = self.get_stats()
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💾 CACHE STATISTICS")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        print(f"   Location: {stats['cache_dir']}")
        print(f"   Total Entries: {stats['total_entries']}")
        print(f"   Valid: {stats['valid']}")
        print(f"   Expired: {stats['expired']}")
        print(f"   Cache Duration: {stats['cache_duration_hours']:.0f}h")
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
    
    def save_scan_metadata(self, scan_data: Dict):
        """Save metadata about last scan"""
        self.metadata.update({
            "last_scan": datetime.now().isoformat(),
            "scan_data": scan_data
        })
        self._save_metadata()
    
    def get_last_scan_time(self) -> Optional[datetime]:
        """Get timestamp of last scan"""
        if "last_scan" in self.metadata:
            return datetime.fromisoformat(self.metadata["last_scan"])
        return None
    
    def get_time_since_last_scan(self) -> Optional[float]:
        """Get hours since last scan"""
        last_scan = self.get_last_scan_time()
        if last_scan:
            delta = datetime.now() - last_scan
            return delta.total_seconds() / 3600
        return None