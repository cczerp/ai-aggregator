# price_fetcher.py
"""
CoinGecko Price Fetcher
Gets all token prices in ONE API call instead of spamming Chainlink
Free tier: 10-50 calls/min
"""
import requests
import time
from typing import Dict, Optional
from colorama import Fore, Style

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


if __name__ == "__main__":
    # Test
    fetcher = CoinGeckoPriceFetcher()
    prices = fetcher.get_all_prices()
    
    print("\n📊 Current Prices:")
    for symbol, price in sorted(prices.items()):
        print(f"   {symbol:8s}: ${price:>10,.2f}")