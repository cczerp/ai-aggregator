from web3 import Web3
from typing import List, Dict, Any, Callable, Optional
import time, os, random, json, requests
from datetime import datetime, timedelta
from colorama import Fore, Style

# Constants
RPC_HEALTH_LOG = "rpc_health.log"

class RPCEndpoint:
    """Single RPC endpoint with tracking and cooldown"""
    
    def __init__(self, name: str, url: str, rate_limit: int = 30, tier: str = "secondary"):
        self.name = name
        self.url = url
        self.rate_limit = rate_limit  # calls per minute
        self.tier = tier  # primary or secondary
        self.calls = 0
        self.failures = 0
        self.last_call = 0
        self.cooldown_until = 0
        self.last_failure_time = 0
        self.consecutive_failures = 0
        self.last_error = None
        self.is_alive = True
        
    def can_call(self) -> bool:
        now = time.time()

        # Check cooldown
        if now < self.cooldown_until:
            return False

        # Check rate limit (calls per minute) with 50% tolerance for concurrency
        # This allows endpoints to be reused more quickly when multiple endpoints are available
        min_delay = (60 / self.rate_limit) * 0.5
        if now - self.last_call < min_delay:
            return False

        return self.is_alive
    
    def record_call(self):
        """Record successful call"""
        self.calls += 1
        self.last_call = time.time()
        self.consecutive_failures = 0
    
    def record_failure(self, error_msg: str):
        self.failures += 1
        self.consecutive_failures += 1
        self.last_error = error_msg

        # Exponential backoff for transient errors
        backoff_time = min(600, 10 * (2 ** (self.consecutive_failures - 1)))
        self.cooldown_until = time.time() + backoff_time

        # Strict disable after 2 consecutive failures
        if self.consecutive_failures >= 2:
            self.is_alive = False
            print(f"{Fore.RED}🚫 Disabled {self.name} after 2 consecutive errors.{Style.RESET_ALL}")
            return

        # Detect rate-limit responses and enforce 10-min cooldown
        if "rate limit" in error_msg.lower() or "too many requests" in error_msg.lower():
            self.cooldown_until = time.time() + 600
            print(f"{Fore.YELLOW}⏳ Rate limited: cooling down {self.name} for 10 minutes.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}⚠️  Cooldown {self.name} for {backoff_time:.0f}s after failure.{Style.RESET_ALL}")

    
    def revive(self):
        """Revive endpoint after successful call"""
        if not self.is_alive and self.consecutive_failures > 0:
            print(f"{Fore.GREEN}♻️ Revived endpoint {self.name}{Style.RESET_ALL}")
        self.is_alive = True
        self.consecutive_failures = 0
        self.cooldown_until = 0


class RPCManager:
    def __init__(self):
        # Load from json or env fallback
        json_path = "rpc_endpoints.json"
        print(f"\n{Fore.CYAN}Looking for RPC config at: {os.path.abspath(json_path)}{Style.RESET_ALL}")
        
        if os.path.exists(json_path):
            print(f"{Fore.GREEN}✅ Found rpc_endpoints.json{Style.RESET_ALL}")
            with open(json_path) as f:
                data = json.load(f)
                print(f"{Fore.GREEN}✅ Loaded JSON successfully{Style.RESET_ALL}")
                print(f"   Primary tiers: {list(data.get('primary', {}).keys())}")
                print(f"   Secondary endpoints: {len(data.get('secondary', []))}")
        else:
            print(f"{Fore.RED}❌ rpc_endpoints.json NOT FOUND!{Style.RESET_ALL}")
            print(f"{Fore.RED}   Create it at: {os.path.abspath(json_path)}{Style.RESET_ALL}")
            data = {"primary": {"alchemy": [], "infura": [], "quicknode": []}, "secondary": []}

        self.endpoints: List[RPCEndpoint] = []
        
        # Add primary endpoints
        endpoint_counter = 0
        for tier_name, entries in data["primary"].items():
            for url in entries:
                self.endpoints.append(RPCEndpoint(
                    f"{tier_name.upper()}-{endpoint_counter}", 
                    url, 
                    rate_limit=100 if tier_name in ["alchemy", "infura", "quicknode"] else 30,
                    tier="primary"
                ))
                endpoint_counter += 1
        
        # Add secondary endpoints
        for url in data["secondary"]:
            self.endpoints.append(RPCEndpoint(
                f"SECONDARY-{endpoint_counter}", 
                url, 
                rate_limit=30,
                tier="secondary"
            ))
            endpoint_counter += 1

        self.current_idx = 0
        self.w3_cache = {}
        
        print(f"\n{Fore.GREEN}✅ RPC Manager Initialized{Style.RESET_ALL}")
        print(f"   Total endpoints: {len(self.endpoints)}")
        print(f"   Primaries: {len([e for e in self.endpoints if e.tier == 'primary'])}")
        print(f"   Secondaries: {len([e for e in self.endpoints if e.tier == 'secondary'])}")
        
        # Show first few endpoints for debugging
        if self.endpoints:
            print(f"\n   First 3 endpoints:")
            for i, e in enumerate(self.endpoints[:3]):
                print(f"     {i+1}. {e.name} ({e.tier}) - {e.url[:50]}...")
        else:
            print(f"{Fore.RED}   ⚠️  WARNING: No endpoints loaded!{Style.RESET_ALL}")
        
    def get_web3(self, endpoint: RPCEndpoint) -> Web3:
        if endpoint.url not in self.w3_cache:
            self.w3_cache[endpoint.url] = Web3(Web3.HTTPProvider(endpoint.url, request_kwargs={'timeout': 10}))
        return self.w3_cache[endpoint.url]
    
    def get_available_endpoint(self, tier="primary") -> Optional[RPCEndpoint]:
        pool = [e for e in self.endpoints if e.tier == tier and e.is_alive]
        if not pool:
            print(f"{Fore.RED}   DEBUG: No alive endpoints for tier '{tier}'{Style.RESET_ALL}")
            return None
        max_attempts = len(pool)
        tried = []
        for _ in range(max_attempts):
            endpoint = pool[self.current_idx % len(pool)]
            self.current_idx += 1
            can_call = endpoint.can_call()
            tried.append(f"{endpoint.name}:{'Y' if can_call else 'N'}")
            if can_call:
                return endpoint
        print(f"{Fore.YELLOW}   DEBUG: Tried {tier} endpoints: {', '.join(tried)} - all busy{Style.RESET_ALL}")
        return None
    
    def execute_with_failover(self, func: Callable, max_retries: int = 3) -> Any:
        last_error = None

        for tier in ["primary", "secondary"]:
            retries = 0  # Reset retries for each tier
            tier_endpoints = [e for e in self.endpoints if e.tier == tier]
            
            if not tier_endpoints:
                print(f"{Fore.YELLOW}⚠️  No {tier} endpoints configured{Style.RESET_ALL}")
                continue
            
            while retries < max_retries:
                endpoint = self.get_available_endpoint(tier)
                if not endpoint:
                    # No available endpoints in this tier, try next tier
                    alive_count = sum(1 for e in tier_endpoints if e.is_alive)
                    print(f"{Fore.YELLOW}⚠️  No available {tier} endpoints (alive: {alive_count}/{len(tier_endpoints)}){Style.RESET_ALL}")
                    break
                
                try:
                    w3 = self.get_web3(endpoint)
                    result = func(w3)
                    endpoint.record_call()
                    endpoint.revive()
                    return result
                except Exception as e:
                    error_msg = str(e)
                    endpoint.record_failure(error_msg)
                    last_error = e
                    print(f"{Fore.YELLOW}⚠️  RPC failed ({endpoint.name}): {error_msg[:60]}...{Style.RESET_ALL}")
                    retries += 1
                    time.sleep(0.5 * retries)
        
        # Build detailed error message
        total_alive = sum(1 for e in self.endpoints if e.is_alive)
        error_details = f"All RPC retries failed. Alive: {total_alive}/{len(self.endpoints)}"
        if last_error:
            error_details += f", Last error: {last_error}"
        raise Exception(error_details)
    
    def log(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {msg}\n"
        print(entry.strip())
        with open(RPC_HEALTH_LOG, "a") as f:
            f.write(entry)
            
    def batch_call(self, calls: List[Callable], max_concurrent: int = 5) -> List[Any]:
        results = []
        for i, func in enumerate(calls):
            try:
                result = self.execute_with_failover(func)
                results.append(result)
            except Exception as e:
                print(f"{Fore.RED}❌ Batch call {i} failed: {e}{Style.RESET_ALL}")
                results.append(None)
        return results
    
    def stats(self) -> Dict[str, Dict]:
        """Get statistics for all endpoints"""
        stats = {}
        for endpoint in self.endpoints:
            stats[endpoint.name] = {
                "calls": endpoint.calls,
                "failures": endpoint.failures,
                "ok": endpoint.is_alive,
                "cooldown": max(0, endpoint.cooldown_until - time.time()),
                "consecutive_failures": endpoint.consecutive_failures
            }
        return stats

    def health_check(self) -> Dict:
        print(f"\n{Fore.CYAN}🔍 Running health check on all endpoints...{Style.RESET_ALL}\n")
        results = {"working": [], "failed": [], "total": len(self.endpoints)}
        for endpoint in self.endpoints:
            try:
                w3 = self.get_web3(endpoint)
                block = w3.eth.block_number
                print(f"   ✅ {endpoint.name:<20} Block: {block:,}")
                results["working"].append(endpoint.name)
            except Exception as e:
                print(f"   ❌ {endpoint.name:<20} Error: {str(e)}")
                print(f"      URL: {endpoint.url}")
                results["failed"].append(endpoint.name)
                endpoint.record_failure(str(e))
        print(f"\n   Working: {len(results['working'])}/{len(self.endpoints)}")
        print(f"   Failed:  {len(results['failed'])}/{len(self.endpoints)}\n")
        return results

    def print_stats(self):
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📡 RPC MANAGER STATISTICS")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        total_calls = sum(e.calls for e in self.endpoints)
        total_failures = sum(e.failures for e in self.endpoints)
        alive_count = sum(1 for e in self.endpoints if e.is_alive)
        print(f"   Total Endpoints: {len(self.endpoints)}")
        print(f"   Alive: {alive_count} | Dead: {len(self.endpoints) - alive_count}")
        print(f"   Total Calls: {total_calls:,}")
        print(f"   Total Failures: {total_failures:,}")
        print(f"   Success Rate: {(total_calls - total_failures) / max(total_calls, 1) * 100:.1f}%\n")
        
        # Sort by calls
        sorted_endpoints = sorted(self.endpoints, key=lambda e: e.calls, reverse=True)
        
        print(f"   {'Endpoint':<20} {'Status':<10} {'Calls':<8} {'Fails':<8} {'Cooldown'}")
        print(f"   {'-'*70}")
        
        for endpoint in sorted_endpoints[:10]:
            status = f"{Fore.GREEN}✅ OK{Style.RESET_ALL}" if endpoint.is_alive else f"{Fore.RED}❌ DEAD{Style.RESET_ALL}"
            cd = max(0, endpoint.cooldown_until - time.time())
            cooldown_str = f"{cd:.0f}s" if cd > 0 else "-"
            print(f"   {endpoint.name:<20} {status:<20} {endpoint.calls:<8} {endpoint.failures:<8} {cooldown_str}")
        
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    mgr = RPCManager()
    health = mgr.health_check()
    mgr.print_stats()