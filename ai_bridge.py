"""
AI Bridge (ArbiGirl) - Updated to use PolygonArbBot with 300+ pools
"""

import json
import time
from web3 import Web3
from colorama import Fore, Style, init
import threading
import queue
import os
import sys

# Import PolygonArbBot which has 300+ pools and ArbiGirl compatibility
from polygon_arb_bot import PolygonArbBot

init(autoreset=True)


class ArbiGirl:
    """AI-powered arbitrage bot with 300+ pool scanner"""

    def __init__(self):
        """Initialize ArbiGirl with PolygonArbBot (300+ pools)"""
        print(f"\n{Fore.MAGENTA}{'='*60}")
        print(f"         🤖 ArbiGirl MEV Bot v3.0")
        print(f"         Now with 300+ pools from pool_registry!")
        print(f"{'='*60}{Style.RESET_ALL}\n")

        # Initialize PolygonArbBot (has 300+ pools + ArbiGirl compatibility)
        self.bot = PolygonArbBot(
            min_tvl=10000,
            scan_interval=60,
            cache_duration_hours=6,
            auto_execute=False
        )

        # Command queue for async operations
        self.command_queue = queue.Queue()

        # State
        self.auto_scan = False
        self.last_opportunities = []

        print(f"{Fore.GREEN}✓ ArbiGirl initialized successfully!{Style.RESET_ALL}")
        print(f"  • Ready to scan 300+ pools from pool_registry.json")
        print(f"  • Cache duration: 6 hours for DEX prices")
        self._show_help()
    
    def _show_help(self):
        """Show available commands"""
        print(f"\n{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}scan{Style.RESET_ALL}       - Run one arbitrage scan (300+ pools)")
        print(f"  {Fore.YELLOW}auto{Style.RESET_ALL}       - Start/stop automatic scanning")
        print(f"  {Fore.YELLOW}status{Style.RESET_ALL}     - Show current status and statistics")
        print(f"  {Fore.YELLOW}pools{Style.RESET_ALL}      - Show pool registry info")
        print(f"  {Fore.YELLOW}clear{Style.RESET_ALL}      - Clear the screen")
        print(f"  {Fore.YELLOW}help{Style.RESET_ALL}       - Show this help")
        print(f"  {Fore.YELLOW}exit{Style.RESET_ALL}       - Exit ArbiGirl")
    
    def handle_scan(self):
        """Run a single scan"""
        print(f"\n{Fore.CYAN}🔍 Running arbitrage scan (300+ pools)...{Style.RESET_ALL}")

        start_time = time.time()
        opportunities = self.bot.run_single_scan()
        scan_time = time.time() - start_time

        self.last_opportunities = opportunities

        if opportunities:
            print(f"\n{Fore.GREEN}✨ Found {len(opportunities)} opportunities!{Style.RESET_ALL}")
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
        """Toggle debug mode (not applicable with PolygonArbBot)"""
        print(f"\n{Fore.YELLOW}Debug mode not available with PolygonArbBot scanner{Style.RESET_ALL}")
        print(f"  PolygonArbBot uses optimized pool scanning")
        print(f"  Check bot logs for detailed information")
    
    def handle_status(self):
        """Show current status"""
        print(f"\n{Fore.CYAN}{'='*40}")
        print(f"         System Status")
        print(f"{'='*40}{Style.RESET_ALL}")

        print(f"  • Scanner: PolygonArbBot (300+ pools)")
        print(f"  • Auto-scan: {'ON' if self.auto_scan else 'OFF'}")
        print(f"  • Cache duration: {self.bot.cache.cache_duration / 3600:.0f}h")
        print(f"  • Min TVL: ${self.bot.min_tvl:,}")
        print(f"  • Last scan: {len(self.last_opportunities)} opportunities")
        print(f"  • Total scans: {self.bot.total_scans}")
        print(f"  • Total opportunities: {self.bot.total_opportunities}")

        # Show module info
        print(f"\n{Fore.CYAN}Modules:{Style.RESET_ALL}")
        print(f"  • polygon_arb_bot.py (main bot)")
        print(f"  • pool_scanner.py (300+ pools)")
        print(f"  • cache.py (6h cache)")

        # Check if files exist
        if os.path.exists('pool_registry.json'):
            print(f"  {Fore.GREEN}✓ pool_registry.json found{Style.RESET_ALL}")
        else:
            print(f"  {Fore.RED}✗ pool_registry.json NOT FOUND!{Style.RESET_ALL}")
    
    def handle_pools(self):
        """List loaded pools from pool_registry"""
        print(f"\n{Fore.CYAN}Pool Registry Summary:{Style.RESET_ALL}")

        # Trigger a pool scan to show stats
        print(f"\n  Scanning pool_registry.json for available pools...")
        print(f"  (This will use cache if available)\n")

        # Show cache stats
        self.bot.cache.print_stats()

        print(f"\n  To see full pool details, check pool_registry.json")
        print(f"  Run a scan to see which pools have >$10k TVL")
    
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
        required_files = ['polygon_arb_bot.py', 'pool_scanner.py', 'pool_registry.json', 'cache.py', 'rpc_mgr.py']
        missing = []

        for file in required_files:
            if not os.path.exists(file):
                missing.append(file)

        if missing:
            print(f"{Fore.RED}Missing required files:{Style.RESET_ALL}")
            for file in missing:
                print(f"  • {file}")
            print(f"\n{Fore.YELLOW}Please make sure all files are in the same directory!{Style.RESET_ALL}")
            print(f"Required: polygon_arb_bot.py, pool_scanner.py, pool_registry.json, cache.py, rpc_mgr.py")
            return

        # Start ArbiGirl
        bot = ArbiGirl()
        bot.run()

    except Exception as e:
        print(f"{Fore.RED}Failed to start ArbiGirl: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Make sure you have:{Style.RESET_ALL}")
        print(f"  1. polygon_arb_bot.py (main bot)")
        print(f"  2. pool_scanner.py (pool scanning)")
        print(f"  3. pool_registry.json (300+ pools)")
        print(f"  4. cache.py (caching)")
        print(f"  5. rpc_mgr.py (RPC management)")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()