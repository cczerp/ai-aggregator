# aggregator_mev_engine.py - COMPLETE VERSION
from web3 import Web3
import requests
import time
from typing import Dict, List, Optional, Tuple
from colorama import Fore, Style, init
from flashbots_tx_builder import FlashbotsTxBuilder
from registries import (
    TOKENS, AGGREGATORS, FLASHLOAN_PROVIDERS, 
    get_token_address, get_token_decimals
)
import os
from dotenv import load_dotenv

init(autoreset=True)
load_dotenv()


class AggregatorMEVEngine:
    """
    MEV Engine using aggregators (1inch, Paraswap) for optimal routing.
    Scans all token pairs from registry, uses aggregators to find best prices.
    """
    
    def __init__(self, w3: Web3, oracle):
        self.w3 = w3
        self.oracle = oracle
        
        # Load from registries
        self.tokens = TOKENS
        self.aggregators = AGGREGATORS
        self.flashloan_providers = FLASHLOAN_PROVIDERS
        
        # Configuration
        self.max_borrow_usd = 500000
        self.min_profit_usd = 50
        self.min_profit_percentage = 0.5
        
        # Initialize Flashbots
        self.tx_builder = FlashbotsTxBuilder(
            contract_address=os.getenv("CONTRACT_ADDRESS"),
            private_key=os.getenv("PRIVATE_KEY"),
            rpc_url=os.getenv("RPC_URL"),
            flashbots_relay_url="https://relay.flashbots.net"
        )
        
        # API keys for aggregators
        self.oneinch_api_key = os.getenv("ONEINCH_API_KEY", "")
        
        # Tracking
        self.opportunities_found = []
        self.executed_trades = []
        
        print(f"{Fore.GREEN}✅ Aggregator MEV Engine initialized{Style.RESET_ALL}")
        print(f"   Tokens: {len(self.tokens)}")
        print(f"   Aggregators: {', '.join(self.aggregators.keys())}")
    
    def get_1inch_quote(self, from_token: str, to_token: str, amount: int) -> Optional[Dict]:
        """
        Get quote from 1inch aggregator.
        Returns best price across ALL DEXs.
        """
        try:
            url = "https://api.1inch.dev/swap/v6.0/1/quote"
            
            params = {
                "src": from_token,
                "dst": to_token,
                "amount": str(amount)
            }
            
            headers = {
                "Authorization": f"Bearer {self.oneinch_api_key}",
                "accept": "application/json"
            } if self.oneinch_api_key else {"accept": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                
                return {
                    "aggregator": "1inch",
                    "from_token": from_token,
                    "to_token": to_token,
                    "from_amount": amount,
                    "to_amount": int(data.get("dstAmount", 0)),
                    "estimated_gas": int(data.get("gas", 200000)),
                    "protocols": data.get("protocols", []),
                    "tx_data": data.get("tx", {})
                }
            
            return None
            
        except Exception as e:
            # Don't print every error to avoid spam
            return None
    
    def get_paraswap_quote(self, from_token: str, to_token: str, amount: int) -> Optional[Dict]:
        """Get quote from Paraswap aggregator."""
        try:
            from_decimals = self._get_decimals_from_address(from_token)
            to_decimals = self._get_decimals_from_address(to_token)
            
            url = "https://apiv5.paraswap.io/prices"
            
            params = {
                "srcToken": from_token,
                "destToken": to_token,
                "amount": str(amount),
                "srcDecimals": from_decimals,
                "destDecimals": to_decimals,
                "side": "SELL",
                "network": 1
            }
            
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                price_route = data.get("priceRoute", {})
                
                return {
                    "aggregator": "Paraswap",
                    "from_token": from_token,
                    "to_token": to_token,
                    "from_amount": amount,
                    "to_amount": int(price_route.get("destAmount", 0)),
                    "estimated_gas": int(price_route.get("gasCost", 200000)),
                    "protocols": price_route.get("bestRoute", [])
                }
            
            return None
            
        except Exception as e:
            return None
    
    def _get_decimals_from_address(self, token_address: str) -> int:
        """Get token decimals from registry by address."""
        for symbol, data in self.tokens.items():
            if data['address'].lower() == token_address.lower():
                return data['decimals']
        return 18
    
    def _get_symbol_from_address(self, token_address: str) -> str:
        """Get token symbol from address."""
        for symbol, data in self.tokens.items():
            if data['address'].lower() == token_address.lower():
                return symbol
        return "UNKNOWN"
    
    def get_best_quote(self, from_token: str, to_token: str, amount: int) -> Optional[Dict]:
        """
        Get best quote across all aggregators.
        """
        quotes = []
        
        # Try 1inch
        quote_1inch = self.get_1inch_quote(from_token, to_token, amount)
        if quote_1inch:
            quotes.append(quote_1inch)
        
        # Try Paraswap
        quote_paraswap = self.get_paraswap_quote(from_token, to_token, amount)
        if quote_paraswap:
            quotes.append(quote_paraswap)
        
        if not quotes:
            return None
        
        # Return quote with highest output amount
        return max(quotes, key=lambda x: x['to_amount'])
    
    def scan_arbitrage_opportunities(self) -> List[Dict]:
        """
        Scan for arbitrage opportunities across all token pairs.
        Uses aggregators to find best buy/sell prices.
        """
        opportunities = []
        
        print(f"\n{Fore.CYAN}{'═'*100}")
        print(f"🔍 SCANNING ARBITRAGE OPPORTUNITIES (Aggregator-Based)")
        print(f"{'═'*100}{Style.RESET_ALL}\n")
        
        token_symbols = list(self.tokens.keys())
        
        # Check all token pairs
        for i, token_in_symbol in enumerate(token_symbols):
            for token_out_symbol in token_symbols:
                if token_in_symbol == token_out_symbol:
                    continue
                
                # Get token addresses
                token_in_addr = get_token_address(token_in_symbol)
                token_out_addr = get_token_address(token_out_symbol)
                
                if not token_in_addr or not token_out_addr:
                    continue
                
                # Calculate trade size
                token_in_price_usd = self.oracle.get_price(token_in_symbol)
                if not token_in_price_usd:
                    continue

                # Test multiple loan amounts: $1k, $10k, $100k
                for test_value_usd in [1000, 10000, 100000]:
                    if test_value_usd > self.max_borrow_usd:
                        continue

                    trade_size_tokens = test_value_usd / token_in_price_usd

                    # Convert to wei
                    decimals = get_token_decimals(token_in_symbol)
                    amount_in_wei = int(trade_size_tokens * (10 ** decimals))

                    # Get best buy price (token_in -> token_out)
                    buy_quote = self.get_best_quote(token_in_addr, token_out_addr, amount_in_wei)

                    if not buy_quote:
                        continue

                    # Get best sell price (token_out -> token_in)
                    sell_quote = self.get_best_quote(token_out_addr, token_in_addr, buy_quote['to_amount'])

                    if not sell_quote:
                        continue

                    # Calculate profit
                    amount_back = sell_quote['to_amount']
                    profit_wei = amount_back - amount_in_wei

                    if profit_wei <= 0:
                        continue

                    # Convert profit to USD
                    profit_tokens = profit_wei / (10 ** decimals)
                    profit_usd = profit_tokens * token_in_price_usd

                    # Calculate fees
                    flashloan_fee_usd = test_value_usd * self.flashloan_providers['AAVE_V3']['fee']

                    # Estimate gas cost (using POL price for Polygon network)
                    total_gas = buy_quote['estimated_gas'] + sell_quote['estimated_gas'] + 100000  # +flashloan overhead
                    gas_price_gwei = self.w3.eth.gas_price / 1e9
                    gas_cost_pol = (total_gas * gas_price_gwei) / 1e9
                    pol_price = self.oracle.get_price("POL") or self.oracle.get_price("MATIC") or 0.40
                    gas_cost_usd = gas_cost_pol * pol_price

                    # Net profit
                    net_profit_usd = profit_usd - flashloan_fee_usd - gas_cost_usd
                    net_profit_pct = (net_profit_usd / test_value_usd) * 100

                    # Check if profitable
                    if net_profit_usd >= self.min_profit_usd and net_profit_pct >= self.min_profit_percentage:
                        opportunity = {
                            "type": "2-pool-aggregator",
                            "token_in": token_in_symbol,
                            "token_out": token_out_symbol,
                            "token_in_addr": token_in_addr,
                            "token_out_addr": token_out_addr,
                            "amount_in_wei": amount_in_wei,
                            "buy_quote": buy_quote,
                            "sell_quote": sell_quote,
                            "trade_size": trade_size_tokens,
                            "profit_calculation": {
                                "trade_value_usd": test_value_usd,
                                "gross_profit_usd": profit_usd,
                                "flashloan_fee_usd": flashloan_fee_usd,
                                "gas_cost_usd": gas_cost_usd,
                                "net_profit_usd": net_profit_usd,
                                "net_profit_pct": net_profit_pct
                            },
                            "timestamp": time.time()
                        }

                        opportunities.append(opportunity)
                        self._print_opportunity(opportunity)
        
        return opportunities
    
    def _print_opportunity(self, opp: Dict):
        """Print arbitrage opportunity."""
        print(f"{Fore.LIGHTGREEN_EX}💰 OPPORTUNITY FOUND!{Style.RESET_ALL}")
        print(f"  Pair: {opp['token_in']} → {opp['token_out']} → {opp['token_in']}")
        print(f"  Buy via: {opp['buy_quote']['aggregator']}")
        print(f"  Sell via: {opp['sell_quote']['aggregator']}")
        print(f"  Trade Size: {opp['trade_size']:.4f} {opp['token_in']}")
        print(f"  {Fore.GREEN}Net Profit: ${opp['profit_calculation']['net_profit_usd']:.2f} ({opp['profit_calculation']['net_profit_pct']:.2f}%){Style.RESET_ALL}")
        print()
    
    def execute_opportunity(self, opportunity: Dict) -> Dict:
        """
        Execute arbitrage opportunity via Flashbots.
        """
        print(f"\n{Fore.YELLOW}{'='*100}")
        print(f"⚡ EXECUTING ARBITRAGE")
        print(f"{'='*100}{Style.RESET_ALL}\n")
        
        # Extract data
        token_in_addr = opportunity['token_in_addr']
        token_out_addr = opportunity['token_out_addr']
        amount_in_wei = opportunity['amount_in_wei']
        
        # Calculate minimum acceptable profit (95% of expected)
        expected_profit_usd = opportunity['profit_calculation']['net_profit_usd']
        token_in_price = self.oracle.get_price(opportunity['token_in'])
        min_profit_tokens = (expected_profit_usd / token_in_price) * 0.95
        decimals = get_token_decimals(opportunity['token_in'])
        min_profit_wei = int(min_profit_tokens * (10 ** decimals))
        
        # Get aggregator router addresses
        buy_aggregator = opportunity['buy_quote']['aggregator']
        sell_aggregator = opportunity['sell_quote']['aggregator']
        
        buy_router = self.aggregators.get(buy_aggregator, {}).get('router', '')
        sell_router = self.aggregators.get(sell_aggregator, {}).get('router', '')
        
        print(f"Token Pair: {opportunity['token_in']} <-> {opportunity['token_out']}")
        print(f"Buy via: {buy_aggregator}")
        print(f"Sell via: {sell_aggregator}")
        print(f"Amount: {opportunity['trade_size']:.6f} {opportunity['token_in']}")
        print(f"Expected Profit: ${expected_profit_usd:.2f}")
        
        # Note: Aggregators are essentially V2-style routers for our contract
        # They handle the complex routing internally
        
        result = self.tx_builder.send_arbitrage_tx(
            token_in_address=token_in_addr,
            token_out_address=token_out_addr,
            dex1_address=buy_router,
            dex2_address=sell_router,
            dex1_version=0,  # Treat aggregators as V2-style
            dex2_version=0,
            amount_in_wei=amount_in_wei,
            min_profit_wei=min_profit_wei,
            dex1_data=b'',
            dex2_data=b'',
            use_flashbots=True,
            bot_source="aggregator-scanner"
        )
        
        if result['success']:
            self.executed_trades.append({
                "opportunity": opportunity,
                "result": result,
                "timestamp": time.time()
            })
        
        return result
    
    def run_continuous_scan(self, scan_interval: int = 10, auto_execute: bool = False):
        """
        Run continuous arbitrage scanning.
        
        Args:
            scan_interval: Seconds between scans
            auto_execute: If True, automatically execute profitable opportunities
        """
        print(f"\n{Fore.CYAN}{'='*100}")
        print(f"⚡ AGGREGATOR MEV ENGINE - CONTINUOUS MODE")
        print(f"{'='*100}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}Max Borrow:{Style.RESET_ALL}    ${self.max_borrow_usd:,}")
        print(f"{Fore.GREEN}Min Profit:{Style.RESET_ALL}     ${self.min_profit_usd} ({self.min_profit_percentage}%)")
        print(f"{Fore.GREEN}Auto-Execute:{Style.RESET_ALL}  {'YES' if auto_execute else 'NO'}")
        print(f"{Fore.GREEN}Scan Interval:{Style.RESET_ALL} {scan_interval}s")
        print(f"{Fore.GREEN}Tokens:{Style.RESET_ALL}         {len(self.tokens)}")
        print(f"\n{Fore.YELLOW}Press Ctrl+C to stop...{Style.RESET_ALL}\n")
        
        scan_count = 0
        
        try:
            while True:
                scan_count += 1
                print(f"{Fore.CYAN}[Scan #{scan_count}] {time.strftime('%H:%M:%S')}{Style.RESET_ALL}")
                
                # Scan for opportunities
                opportunities = self.scan_arbitrage_opportunities()
                
                if opportunities:
                    # Sort by profit
                    opportunities.sort(key=lambda x: x['profit_calculation']['net_profit_usd'], reverse=True)
                    
                    best_opp = opportunities[0]
                    print(f"\n{Fore.GREEN}Found {len(opportunities)} profitable opportunities{Style.RESET_ALL}")
                    print(f"{Fore.GREEN}Best: ${best_opp['profit_calculation']['net_profit_usd']:.2f} profit{Style.RESET_ALL}\n")
                    
                    # Auto-execute if enabled
                    if auto_execute:
                        print(f"{Fore.YELLOW}Executing best opportunity...{Style.RESET_ALL}")
                        result = self.execute_opportunity(best_opp)
                        
                        if result['success']:
                            print(f"{Fore.GREEN}✅ Successfully executed arbitrage!{Style.RESET_ALL}\n")
                        else:
                            print(f"{Fore.RED}❌ Execution failed: {result.get('error')}{Style.RESET_ALL}\n")
                    
                    self.opportunities_found.extend(opportunities)
                else:
                    print(f"{Fore.YELLOW}No profitable opportunities found this scan{Style.RESET_ALL}\n")
                
                # Wait for next scan
                time.sleep(scan_interval)
        
        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}Stopping engine...{Style.RESET_ALL}")
            self._print_session_summary()
    
    def _print_session_summary(self):
        """Print summary of scanning session."""
        print(f"\n{Fore.CYAN}{'='*100}")
        print(f"📊 SESSION SUMMARY")
        print(f"{'='*100}{Style.RESET_ALL}\n")
        
        if not self.opportunities_found:
            print(f"{Fore.YELLOW}No opportunities found{Style.RESET_ALL}")
            return
        
        total_potential_profit = sum(o['profit_calculation']['net_profit_usd'] for o in self.opportunities_found)
        
        print(f"{Fore.GREEN}Total Opportunities Found:{Style.RESET_ALL} {len(self.opportunities_found)}")
        print(f"{Fore.GREEN}Total Potential Profit:{Style.RESET_ALL}    ${total_potential_profit:,.2f}")
        print(f"{Fore.GREEN}Trades Executed:{Style.RESET_ALL}           {len(self.executed_trades)}")
        
        if self.executed_trades:
            actual_profit = sum(t['opportunity']['profit_calculation']['net_profit_usd'] for t in self.executed_trades)
            print(f"{Fore.GREEN}Actual Profit (Executed):{Style.RESET_ALL}  ${actual_profit:,.2f}")
        
        # Top opportunities
        sorted_opps = sorted(
            self.opportunities_found,
            key=lambda x: x['profit_calculation']['net_profit_usd'],
            reverse=True
        )[:5]
        
        print(f"\n{Fore.YELLOW}Top 5 Opportunities:{Style.RESET_ALL}")
        for i, opp in enumerate(sorted_opps, 1):
            profit = opp['profit_calculation']['net_profit_usd']
            pair = f"{opp['token_in']} → {opp['token_out']}"
            print(f"  {i}. ${profit:.2f} - {pair}")
        
        print(f"\n{Fore.CYAN}{'='*100}{Style.RESET_ALL}\n")


# Main execution
if __name__ == "__main__":
    from web3 import Web3
    
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(os.getenv("RPC_URL")))
    
    # Initialize oracle (you'll need to provide your oracle implementation)
    # from your_oracle import ChainlinkOracle
    # oracle = ChainlinkOracle(w3)
    
    # For now, create a simple mock oracle
    class MockOracle:
        def get_price(self, symbol):
            prices = {
                "ETH": 2000,
                "WETH": 2000,
                "USDC": 1,
                "USDT": 1,
                "DAI": 1,
                "WBTC": 40000,
                "LINK": 15,
                "UNI": 7
            }
            return prices.get(symbol, 1)
    
    oracle = MockOracle()
    
    # Initialize and run engine
    engine = AggregatorMEVEngine(w3, oracle)
    
    # Run in continuous mode with auto-execution disabled (set to True to auto-execute)
    engine.run_continuous_scan(scan_interval=15, auto_execute=False)