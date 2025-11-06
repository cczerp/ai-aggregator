"""
AI Bridge (ArbiGirl) - Updated for Modular Scanner
Now aware of the price_math.py module
"""

import json
import time
from web3 import Web3
from colorama import Fore, Style, init
import threading
import queue
import os
import sys

# Import BOTH modules now
from price_math import PriceCalculator
from arb_scanner import ArbScanner

init(autoreset=True)


class ArbiGirl:
    """AI-powered arbitrage bot with modular scanner"""
    
    def __init__(self):
        """Initialize ArbiGirl with the new modular scanner"""
        print(f"\n{Fore.MAGENTA}{'='*60}")
        print(f"         🤖 ArbiGirl MEV Bot v2.0 (Modular)")
        print(f"         Now with separated price_math module!")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        
        # Initialize the scanner with modular structure
        self.scanner = ArbScanner()
        
        # Quick access to price calculator for debug control
        self.price_calc = self.scanner.price_calc
        
        # Command queue for async operations
        self.command_queue = queue.Queue()
        
        # State
        self.auto_scan = False
        self.last_opportunities = []
        
        print(f"{Fore.GREEN}✓ ArbiGirl initialized successfully!{Style.RESET_ALL}")
        print(f"  • Scanner: Loaded {len(self.scanner.pools)} pools")
        print(f"  • V3 Debug: {'ON' if self.price_calc.debug else 'OFF'}")
        print(f"  • Modules: arb_scanner.py + price_math.py")
        self._show_help()
    
    def _show_help(self):
        """Show available commands"""
        print(f"\n{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}scan{Style.RESET_ALL}       - Run one arbitrage scan")
        print(f"  {Fore.YELLOW}auto{Style.RESET_ALL}       - Start/stop automatic scanning")
        print(f"  {Fore.YELLOW}debug on{Style.RESET_ALL}   - Enable V3 debug output")
        print(f"  {Fore.YELLOW}debug off{Style.RESET_ALL}  - Disable V3 debug output")
        print(f"  {Fore.YELLOW}status{Style.RESET_ALL}     - Show current status")
        print(f"  {Fore.YELLOW}pools{Style.RESET_ALL}      - List loaded pools")
        print(f"  {Fore.YELLOW}clear{Style.RESET_ALL}      - Clear the screen")
        print(f"  {Fore.YELLOW}help{Style.RESET_ALL}       - Show this help")
        print(f"  {Fore.YELLOW}exit{Style.RESET_ALL}       - Exit ArbiGirl")
    
    def handle_scan(self):
        """Run a single scan"""
        print(f"\n{Fore.CYAN}🔍 Running arbitrage scan...{Style.RESET_ALL}")
        
        start_time = time.time()
        opportunities = self.scanner.scan_opportunities()
        scan_time = time.time() - start_time
        
        self.last_opportunities = opportunities
        
        if opportunities:
            print(f"\n{Fore.GREEN}✨ Found {len(opportunities)} opportunities!{Style.RESET_ALL}")
            self.scanner.display_opportunities(opportunities)
        else:
            print(f"\n{Fore.YELLOW}No opportunities found this scan.{Style.RESET_ALL}")
        
        print(f"\n{Fore.BLUE}Scan completed in {scan_time:.2f}s{Style.RESET_ALL}")
    
    def handle_auto(self):
        """Toggle automatic scanning"""
        self.auto_scan = not self.auto_scan
        
        if self.auto_scan:
            print(f"\n{Fore.GREEN}🔄 Automatic scanning ENABLED{Style.RESET_ALL}")
            print(f"  Scanning every 5 seconds...")
            print(f"  Type 'auto' again to stop")
            
            # Start auto scan in background
            thread = threading.Thread(target=self._auto_scan_loop)
            thread.daemon = True
            thread.start()
        else:
            print(f"\n{Fore.YELLOW}⏸️ Automatic scanning DISABLED{Style.RESET_ALL}")
    
    def _auto_scan_loop(self):
        """Background scanning loop"""
        while self.auto_scan:
            self.handle_scan()
            time.sleep(5)
    
    def handle_debug(self, args):
        """Toggle debug mode"""
        if len(args) < 2:
            current = "ON" if self.price_calc.debug else "OFF"
            print(f"\n{Fore.CYAN}Debug mode is currently: {current}{Style.RESET_ALL}")
            print(f"  Use 'debug on' or 'debug off' to change")
            return
        
        if args[1].lower() == 'on':
            self.price_calc.set_debug_mode(True)
            print(f"\n{Fore.GREEN}✓ V3 Debug mode ENABLED{Style.RESET_ALL}")
            print(f"  You'll now see detailed calculation steps")
        elif args[1].lower() == 'off':
            self.price_calc.set_debug_mode(False)
            print(f"\n{Fore.YELLOW}✓ V3 Debug mode DISABLED{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}Invalid option. Use 'debug on' or 'debug off'{Style.RESET_ALL}")
    
    def handle_status(self):
        """Show current status"""
        print(f"\n{Fore.CYAN}{'='*40}")
        print(f"         System Status")
        print(f"{'='*40}{Style.RESET_ALL}")
        
        print(f"  • Pools loaded: {len(self.scanner.pools)}")
        print(f"  • Auto-scan: {'ON' if self.auto_scan else 'OFF'}")
        print(f"  • V3 Debug: {'ON' if self.price_calc.debug else 'OFF'}")
        print(f"  • Cache duration: {self.price_calc.cache_duration}s")
        print(f"  • Last scan: {len(self.last_opportunities)} opportunities")
        
        # Show module info
        print(f"\n{Fore.CYAN}Modules:{Style.RESET_ALL}")
        print(f"  • arb_scanner.py (main logic)")
        print(f"  • price_math.py (calculations)")
        
        # Check if files exist
        if os.path.exists('price_math.py'):
            print(f"  {Fore.GREEN}✓ price_math.py found{Style.RESET_ALL}")
        else:
            print(f"  {Fore.RED}✗ price_math.py NOT FOUND!{Style.RESET_ALL}")
    
    def handle_pools(self):
        """List loaded pools"""
        print(f"\n{Fore.CYAN}Loaded Pools:{Style.RESET_ALL}")
        
        # Group by DEX
        by_dex = {}
        for pool in self.scanner.pools:
            dex = pool['dex']
            if dex not in by_dex:
                by_dex[dex] = []
            by_dex[dex].append(pool)
        
        for dex, pools in by_dex.items():
            print(f"\n  {Fore.YELLOW}{dex.upper()}{Style.RESET_ALL} ({len(pools)} pools):")
            for p in pools[:3]:  # Show first 3
                # Get token symbols
                t0 = self.scanner.tokens.get(p['token0'], {}).get('symbol', 'UNKNOWN')
                t1 = self.scanner.tokens.get(p['token1'], {}).get('symbol', 'UNKNOWN')
                print(f"    • {t0}/{t1} - {p['address'][:10]}...")
            if len(pools) > 3:
                print(f"    ... and {len(pools)-3} more")
    
    def handle_clear(self):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        self._show_help()
    
    def run(self):
        """Main command loop"""
        print(f"\n{Fore.GREEN}ArbiGirl is ready! Type 'help' for commands.{Style.RESET_ALL}\n")
        
        while True:
            try:
                # Get user input
                user_input = input(f"{Fore.MAGENTA}You> {Style.RESET_ALL}").strip().lower()
                
                if not user_input:
                    continue
                
                # Parse command
                args = user_input.split()
                command = args[0]
                
                # Handle commands
                if command == 'scan':
                    self.handle_scan()
                
                elif command == 'auto':
                    self.handle_auto()
                
                elif command == 'debug':
                    self.handle_debug(args)
                
                elif command == 'status':
                    self.handle_status()
                
                elif command == 'pools':
                    self.handle_pools()
                
                elif command == 'clear':
                    self.handle_clear()
                
                elif command == 'help':
                    self._show_help()
                
                elif command in ['exit', 'quit', 'bye']:
                    print(f"\n{Fore.MAGENTA}Goodbye! 👋{Style.RESET_ALL}")
                    break
                
                else:
                    print(f"{Fore.RED}Unknown command. Type 'help' for available commands.{Style.RESET_ALL}")
                    
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Use 'exit' to quit properly.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")


def main():
    """Entry point"""
    try:
        # Check for required files
        required_files = ['price_math.py', 'arb_scanner.py', 'config.json', 'abis.py']
        missing = []
        
        for file in required_files:
            if not os.path.exists(file):
                missing.append(file)
        
        if missing:
            print(f"{Fore.RED}Missing required files:{Style.RESET_ALL}")
            for file in missing:
                print(f"  • {file}")
            print(f"\n{Fore.YELLOW}Please make sure all files are in the same directory!{Style.RESET_ALL}")
            print(f"Required: price_math.py, arb_scanner.py, config.json, abis.py")
            return
        
        # Start ArbiGirl
        bot = ArbiGirl()
        bot.run()
        
    except Exception as e:
        print(f"{Fore.RED}Failed to start ArbiGirl: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Make sure you have:{Style.RESET_ALL}")
        print(f"  1. price_math.py (calculation module)")
        print(f"  2. arb_scanner.py (scanner module)")
        print(f"  3. config.json (configuration)")
        print(f"  4. abis.py (contract ABIs)")


if __name__ == "__main__":
    main()