"""
Arbitrage Scanner - Refactored with modular price calculations
Now uses price_math.py for all DEX math calculations
"""

import json
import time
from web3 import Web3
from typing import Dict, List, Optional, Tuple
from colorama import Fore, Style, init
from pool_scanner import PoolScanner
from rpc_mgr import RPCManager
from cache import Cache

# Import our separated math module
from price_math import PriceCalculator

# Import ABIs (you'll need to have these)
from abis import (
    UNISWAP_V2_PAIR_ABI, 
    UNISWAP_V3_POOL_ABI, 
    CURVE_POOL_ABI,
    QUOTER_V2_ABI
)

init(autoreset=True)


class ArbScanner:
    """Main arbitrage scanner using modular price calculations"""
    
    def __init__(self, config_path: str = 'config.json'):
        """Initialize scanner with configuration"""
        self.pool_scanner = PoolScanner(rpc_manager=RPCManager(), cache=Cache(cache_dir="./cache", cache_duration_hours=24))
        self.pools = self.pool_scanner.scan_all_pools()
        
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.config['rpc_url']))
        if not self.w3.is_connected():
            raise Exception("Failed to connect to RPC")
        
        # Initialize price calculator with debug mode
        self.price_calc = PriceCalculator(w3=self.w3, debug=True)  # Set to False to disable debug
        
        # Token configuration
        self.tokens = self.config['tokens']
        self.scan_amount_usd = self.config.get('scan_amount_usd', 100)
        
        # Router addresses for verification
        self.routers = {
            'quickswap': self.config['routers']['quickswap'],
            'sushiswap': self.config['routers']['sushiswap'],
            'uniswap_v3': self.config['routers']['uniswap_v3'],
            'curve': self.config['routers'].get('curve', '0x0000000000000000000000000000000000000000')
        }
        
        # Pool configuration
        self.pools = []
        self._load_pools()
        
        print(f"\n{Fore.CYAN}=== Arbitrage Scanner Initialized ==={Style.RESET_ALL}")
        print(f"   Connected to: {self.config['rpc_url']}")
        print(f"   Loaded: {len(self.pools)} pools")
        print(f"   Scan amount: ${self.scan_amount_usd}")
        print(f"   V3 Debug Mode: {'ON' if self.price_calc.debug else 'OFF'}")
        print(f"   Using modular price_math.py for calculations")
    
    def _load_pools(self):
        """Load pool configurations"""
        for dex_name, dex_config in self.config['dexes'].items():
            for pool_config in dex_config['pools']:
                self.pools.append({
                    'dex': dex_name,
                    'address': pool_config['address'].lower(),
                    'token0': pool_config['token0'].lower(),
                    'token1': pool_config['token1'].lower(),
                    'fee': pool_config.get('fee', 30),  # Default 0.3% for V2
                    'type': dex_config.get('type', 'v2')
                })
    
    # ============================================================================
    # MAIN SCANNING LOGIC
    # ============================================================================
    
    def scan_opportunities(self) -> List[Dict]:
        """
        Scan for arbitrage opportunities
        Uses modular price calculations from price_math.py
        """
        opportunities = []
        
        print(f"\n{Fore.YELLOW}Scanning {len(self.pools)} pools...{Style.RESET_ALL}")
        
        # Group pools by token pair
        pair_pools = {}
        for pool in self.pools:
            pair_key = tuple(sorted([pool['token0'], pool['token1']]))
            if pair_key not in pair_pools:
                pair_pools[pair_key] = []
            pair_pools[pair_key].append(pool)
        
        # Check each token pair
        for (token0, token1), pools in pair_pools.items():
            if len(pools) < 2:
                continue
            
            # Get token info
            token0_info = self.tokens.get(token0)
            token1_info = self.tokens.get(token1)
            
            if not token0_info or not token1_info:
                continue
            
            # Calculate scan amounts
            scan_amounts_usd = [1000, 10000, 100000]  # $1k, $10k, $100k
            for scan_usd in scan_amounts_usd:
                token0_amount = int(scan_usd * (10 ** token0_info['decimals']) / token0_info['price_usd'])
                token1_amount = int(scan_usd * (10 ** token1_info['decimals']) / token1_info['price_usd'])   
            
            # Get quotes from each pool
            for direction in ['0to1', '1to0']:
                if direction == '0to1':
                    token_in, token_out = token0, token1
                    amount_in = token0_amount
                else:
                    token_in, token_out = token1, token0
                    amount_in = token1_amount
                
                quotes = []
                for pool in pools:
                    quote = self.get_quote(pool, token_in, token_out, amount_in)
                    if quote and quote > 0:
                        quotes.append({
                            'pool': pool,
                            'amount_out': quote
                        })
                
                # Find best opportunity
                if len(quotes) >= 2:
                    quotes.sort(key=lambda x: x['amount_out'], reverse=True)
                    best_buy = quotes[-1]  # Buy from cheapest
                    best_sell = quotes[0]  # Sell to most expensive
                    
                    profit = best_sell['amount_out'] - amount_in
                    profit_pct = (profit / amount_in) * 100 if amount_in > 0 else 0
                    
                    if profit_pct > 0.5:  # Only report > 0.5% profit
                        opportunities.append({
                            'token_in': token_in,
                            'token_out': token_out,
                            'amount_in': amount_in,
                            'buy_pool': best_buy['pool'],
                            'sell_pool': best_sell['pool'],
                            'buy_output': best_buy['amount_out'],
                            'sell_output': best_sell['amount_out'],
                            'profit': profit,
                            'profit_pct': profit_pct
                        })
        
        return opportunities
    
    def get_quote(self, pool: Dict, token_in: str, token_out: str, amount_in: int) -> Optional[int]:
        """
        Get quote for a swap using the appropriate calculation method
        Delegates to price_math.py module
        """
        try:
            pool_type = pool.get('type', 'v2')
            
            if pool_type == 'v2':
                # V2 style pools (QuickSwap, SushiSwap)
                reserves = self.price_calc.get_v2_reserves(
                    self.w3, 
                    pool['address'], 
                    UNISWAP_V2_PAIR_ABI
                )
                
                if not reserves:
                    return None
                
                reserve0, reserve1, token0, token1 = reserves
                
                # Determine direction
                if token_in.lower() == token0.lower():
                    return self.price_calc.calculate_v2_output(
                        amount_in, reserve0, reserve1, pool.get('fee', 30)
                    )
                else:
                    return self.price_calc.calculate_v2_output(
                        amount_in, reserve1, reserve0, pool.get('fee', 30)
                    )
            
            elif pool_type == 'v3':
                # V3 style pools (Uniswap V3)
                pool_info = self.price_calc.get_v3_price_info(
                    self.w3,
                    pool['address'],
                    UNISWAP_V3_POOL_ABI
                )
                
                if not pool_info:
                    return None
                
                token_in_is_token0 = token_in.lower() == pool_info['token0']
                
                return self.price_calc.calculate_v3_output(
                    amount_in,
                    pool_info['sqrt_price_x96'],
                    pool_info['liquidity'],
                    pool_info['fee'],
                    token_in_is_token0
                )
            
            elif pool_type == 'curve':
                # Curve pools
                return self.price_calc.get_quote_curve(
                    self.w3,
                    pool['address'],
                    token_in,
                    token_out,
                    amount_in,
                    CURVE_POOL_ABI
                )
            
            return None
            
        except Exception as e:
            return None
    
    def verify_with_router(self, opportunity: Dict) -> Tuple[int, int]:
        """
        Verify opportunity using actual router quotes
        More accurate but slower
        """
        try:
            # Get router for buy pool
            buy_router_address = self.routers.get(opportunity['buy_pool']['dex'])
            sell_router_address = self.routers.get(opportunity['sell_pool']['dex'])
            
            if not buy_router_address or not sell_router_address:
                return 0, 0
            
            # For V3, use quoter
            if opportunity['buy_pool']['type'] == 'v3':
                quoter_address = '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
                quoter = self.w3.eth.contract(
                    address=Web3.to_checksum_address(quoter_address),
                    abi=QUOTER_V2_ABI
                )
                
                try:
                    buy_quote = quoter.functions.quoteExactInputSingle((
                        opportunity['token_in'],
                        opportunity['token_out'],
                        opportunity['amount_in'],
                        opportunity['buy_pool'].get('fee', 3000),
                        0
                    )).call()
                    
                    if hasattr(buy_quote, 'amountOut'):
                        actual_buy = buy_quote.amountOut
                    else:
                        actual_buy = buy_quote[0] if isinstance(buy_quote, tuple) else buy_quote
                except:
                    actual_buy = 0
            else:
                actual_buy = opportunity['buy_output']  # Use calculated for V2
            
            # Similar for sell pool
            if opportunity['sell_pool']['type'] == 'v3':
                try:
                    sell_quote = quoter.functions.quoteExactInputSingle((
                        opportunity['token_out'],
                        opportunity['token_in'],
                        actual_buy,
                        opportunity['sell_pool'].get('fee', 3000),
                        0
                    )).call()
                    
                    if hasattr(sell_quote, 'amountOut'):
                        actual_sell = sell_quote.amountOut
                    else:
                        actual_sell = sell_quote[0] if isinstance(sell_quote, tuple) else sell_quote
                except:
                    actual_sell = 0
            else:
                actual_sell = opportunity['sell_output']  # Use calculated for V2
            
            return actual_buy, actual_sell
            
        except Exception as e:
            return 0, 0
    
    def display_opportunities(self, opportunities: List[Dict]):
        """Display found opportunities in a nice format"""
        if not opportunities:
            print(f"\n{Fore.RED}No arbitrage opportunities found.{Style.RESET_ALL}")
            return
        
        print(f"\n{Fore.GREEN}=== Found {len(opportunities)} Opportunities ==={Style.RESET_ALL}")
        
        for i, opp in enumerate(opportunities, 1):
            # Get token symbols
            token_in_info = self.tokens.get(opp['token_in'])
            token_out_info = self.tokens.get(opp['token_out'])
            
            token_in_symbol = token_in_info['symbol'] if token_in_info else 'UNKNOWN'
            token_out_symbol = token_out_info['symbol'] if token_out_info else 'UNKNOWN'
            
            # Calculate USD values
            if token_in_info:
                amount_in_usd = (opp['amount_in'] / (10 ** token_in_info['decimals'])) * token_in_info['price_usd']
                profit_usd = (opp['profit'] / (10 ** token_in_info['decimals'])) * token_in_info['price_usd']
            else:
                amount_in_usd = 0
                profit_usd = 0
            
            print(f"\n{Fore.CYAN}[Opportunity #{i}]{Style.RESET_ALL}")
            print(f"  Path: {token_in_symbol} -> {token_out_symbol} -> {token_in_symbol}")
            print(f"  Buy from: {opp['buy_pool']['dex']} ({opp['buy_pool']['address'][:10]}...)")
            print(f"  Sell to: {opp['sell_pool']['dex']} ({opp['sell_pool']['address'][:10]}...)")
            print(f"  Amount: ${amount_in_usd:.2f}")
            print(f"  Profit: ${profit_usd:.2f} ({opp['profit_pct']:.2f}%)")
            
            # Verify with router if significant opportunity
            if opp['profit_pct'] > 1:
                print(f"  {Fore.YELLOW}Verifying with router...{Style.RESET_ALL}")
                actual_buy, actual_sell = self.verify_with_router(opp)
                
                if actual_buy > 0 and actual_sell > 0:
                    actual_profit = actual_sell - opp['amount_in']
                    actual_profit_pct = (actual_profit / opp['amount_in']) * 100
                    
                    if actual_profit_pct > 0:
                        print(f"  {Fore.GREEN}✓ Verified: {actual_profit_pct:.2f}% profit{Style.RESET_ALL}")
                    else:
                        print(f"  {Fore.RED}✗ Not profitable after verification{Style.RESET_ALL}")
                else:
                    print(f"  {Fore.RED}✗ Could not verify{Style.RESET_ALL}")
    
    def run(self):
        """Main scanning loop"""
        print(f"\n{Fore.GREEN}Starting arbitrage scanner...{Style.RESET_ALL}")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while True:
                start_time = time.time()
                
                # Clear cache periodically
                self.price_calc.clear_cache()
                
                # Scan for opportunities
                opportunities = self.scan_opportunities()
                
                # Display results
                self.display_opportunities(opportunities)
                
                # Show scan time
                scan_time = time.time() - start_time
                print(f"\n{Fore.BLUE}Scan completed in {scan_time:.2f}s{Style.RESET_ALL}")
                
                # Wait before next scan
                time.sleep(5)
                
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Scanner stopped by user.{Style.RESET_ALL}")


def toggle_debug_mode():
    """Helper function to toggle V3 debug mode"""
    try:
        scanner = ArbScanner()
        current_state = scanner.price_calc.debug
        scanner.price_calc.set_debug_mode(not current_state)
        print(f"Debug mode {'enabled' if not current_state else 'disabled'}")
    except Exception as e:
        print(f"Error toggling debug mode: {e}")


if __name__ == "__main__":
    scanner = ArbScanner()
    scanner.run()
