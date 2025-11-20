#!/usr/bin/env python3
"""
MEV Bot - Main Menu System
Complete control center with automatic mode for "set it and leave it" operation
"""

import os
import sys
import asyncio
from colorama import Fore, Style, init
from dotenv import load_dotenv

# Import bot systems
from master_mev_bot import MasterMEVBot
from sandwich_bot import SandwichBot
from unified_mev_bot import UnifiedMEVBot
from rpc_mgr import RPCManager

init(autoreset=True)
load_dotenv()


class MEVBotMenu:
    """Interactive menu system for MEV bot control"""

    def __init__(self):
        self.contract_address = os.getenv('CONTRACT_ADDRESS')
        self.private_key = os.getenv('PRIVATE_KEY')
        self.flashbots_relay = os.getenv('FLASHBOTS_RELAY_URL', 'https://relay.flashbots.net')

        # Validate configuration
        if not self.contract_address or not self.private_key:
            print(f"{Fore.RED}❌ ERROR: Missing CONTRACT_ADDRESS or PRIVATE_KEY in .env{Style.RESET_ALL}")
            sys.exit(1)

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name != 'nt' else 'cls')

    def print_header(self):
        """Print main header"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{'🤖 MEV BOT CONTROL CENTER':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        print(f"   Contract: {self.contract_address[:10]}...{self.contract_address[-8:]}")
        print(f"   Wallet: {self.private_key[:10]}...****")
        print(f"   Flashbots: {self.flashbots_relay}")
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    def print_menu(self):
        """Print main menu options"""
        print(f"{Fore.GREEN}Available Modes:{Style.RESET_ALL}\n")
        print(f"  {Fore.YELLOW}1.{Style.RESET_ALL} 🚀 AUTOMATIC MODE (Set it and leave it)")
        print(f"     └─ Runs both strategies continuously with auto-restart")
        print()
        print(f"  {Fore.YELLOW}2.{Style.RESET_ALL} 🥪 SANDWICH ONLY MODE")
        print(f"     └─ PRIMARY strategy: Monitor mempool for sandwich attacks")
        print()
        print(f"  {Fore.YELLOW}3.{Style.RESET_ALL} 📊 ARBITRAGE ONLY MODE")
        print(f"     └─ SECONDARY strategy: Graph-based DEX arbitrage with ML")
        print()
        print(f"  {Fore.YELLOW}4.{Style.RESET_ALL} 🎯 DUAL MODE (Manual control)")
        print(f"     └─ Run both strategies with manual control")
        print()
        print(f"  {Fore.YELLOW}5.{Style.RESET_ALL} ⚙️  CONFIGURATION")
        print(f"     └─ View and modify bot parameters")
        print()
        print(f"  {Fore.YELLOW}6.{Style.RESET_ALL} 📈 VIEW STATISTICS")
        print(f"     └─ Show ML learning progress and trade history")
        print()
        print(f"  {Fore.YELLOW}7.{Style.RESET_ALL} 🧪 TEST MODE (Dry run)")
        print(f"     └─ Simulate trades without executing")
        print()
        print(f"  {Fore.YELLOW}8.{Style.RESET_ALL} ❌ EXIT")
        print()

    def get_choice(self) -> str:
        """Get user menu choice"""
        return input(f"{Fore.CYAN}Enter your choice [1-8]: {Style.RESET_ALL}").strip()

    async def run_automatic_mode(self):
        """
        AUTOMATIC MODE - Set it and leave it!
        Runs both strategies with auto-restart on errors
        """
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'🚀 AUTOMATIC MODE - SET IT AND LEAVE IT':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Get configuration
        enable_sandwich = True
        enable_arbitrage = True
        enable_ml = True

        print(f"Configuration:")
        print(f"  ✅ Sandwich attacks: ENABLED (PRIMARY)")
        print(f"  ✅ Arbitrage: ENABLED (SECONDARY)")
        print(f"  ✅ ML learning: ENABLED")
        print()

        # Ask for intervals
        try:
            arb_interval = int(input(f"{Fore.CYAN}Arbitrage scan interval (seconds) [default: 60]: {Style.RESET_ALL}") or "60")
            stats_interval = int(input(f"{Fore.CYAN}Stats report interval (seconds) [default: 300]: {Style.RESET_ALL}") or "300")
        except ValueError:
            print(f"{Fore.RED}Invalid input, using defaults{Style.RESET_ALL}")
            arb_interval = 60
            stats_interval = 300

        print(f"\n{Fore.YELLOW}Starting automatic mode...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}\n")

        restart_count = 0
        max_restarts = 10

        while restart_count < max_restarts:
            try:
                # Initialize master bot
                bot = MasterMEVBot(
                    contract_address=self.contract_address,
                    private_key=self.private_key,
                    enable_sandwich=enable_sandwich,
                    enable_arbitrage=enable_arbitrage,
                    enable_ml=enable_ml
                )

                # Run both strategies
                await bot.run(
                    arbitrage_scan_interval=arb_interval,
                    stats_interval=stats_interval
                )

            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}User stopped automatic mode{Style.RESET_ALL}")
                break

            except Exception as e:
                restart_count += 1
                print(f"\n{Fore.RED}❌ ERROR: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Auto-restart {restart_count}/{max_restarts} in 5 seconds...{Style.RESET_ALL}")
                await asyncio.sleep(5)

        if restart_count >= max_restarts:
            print(f"\n{Fore.RED}❌ Max restarts reached. Please check logs.{Style.RESET_ALL}")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    async def run_sandwich_only(self):
        """Run sandwich bot only"""
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'🥪 SANDWICH ATTACK MODE':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        print(f"This will continuously monitor the mempool for sandwich opportunities.")
        print(f"{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}\n")

        try:
            rpc_manager = RPCManager()
            bot = SandwichBot(
                rpc_manager=rpc_manager,
                contract_address=self.contract_address,
                private_key=self.private_key,
                flashbots_relay_url=self.flashbots_relay
            )

            await bot.monitor_mempool()

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}User stopped sandwich mode{Style.RESET_ALL}")
        except Exception as e:
            print(f"\n{Fore.RED}❌ ERROR: {e}{Style.RESET_ALL}")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    def run_arbitrage_only(self):
        """Run arbitrage bot only"""
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'📊 ARBITRAGE MODE':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Get configuration
        enable_ml = input(f"{Fore.CYAN}Enable ML learning? [Y/n]: {Style.RESET_ALL}").strip().lower() != 'n'

        try:
            scan_interval = int(input(f"{Fore.CYAN}Scan interval (seconds) [default: 60]: {Style.RESET_ALL}") or "60")
        except ValueError:
            scan_interval = 60

        print(f"\n{Fore.YELLOW}Starting arbitrage mode...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}\n")

        try:
            bot = UnifiedMEVBot(
                contract_address=self.contract_address,
                private_key=self.private_key,
                enable_mempool=False,
                enable_ml=enable_ml
            )

            bot.run_continuous(interval_seconds=scan_interval)

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}User stopped arbitrage mode{Style.RESET_ALL}")
        except Exception as e:
            print(f"\n{Fore.RED}❌ ERROR: {e}{Style.RESET_ALL}")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    async def run_dual_mode(self):
        """Run both strategies with manual control"""
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'🎯 DUAL MODE':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Get configuration
        enable_ml = input(f"{Fore.CYAN}Enable ML learning? [Y/n]: {Style.RESET_ALL}").strip().lower() != 'n'

        try:
            arb_interval = int(input(f"{Fore.CYAN}Arbitrage scan interval (seconds) [default: 60]: {Style.RESET_ALL}") or "60")
            stats_interval = int(input(f"{Fore.CYAN}Stats interval (seconds) [default: 300]: {Style.RESET_ALL}") or "300")
        except ValueError:
            arb_interval = 60
            stats_interval = 300

        print(f"\n{Fore.YELLOW}Starting dual mode...{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}\n")

        try:
            bot = MasterMEVBot(
                contract_address=self.contract_address,
                private_key=self.private_key,
                enable_sandwich=True,
                enable_arbitrage=True,
                enable_ml=enable_ml
            )

            await bot.run(
                arbitrage_scan_interval=arb_interval,
                stats_interval=stats_interval
            )

        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}User stopped dual mode{Style.RESET_ALL}")
        except Exception as e:
            print(f"\n{Fore.RED}❌ ERROR: {e}{Style.RESET_ALL}")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    def show_configuration(self):
        """Show and modify configuration"""
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'⚙️  CONFIGURATION':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        print(f"{Fore.YELLOW}Current Configuration:{Style.RESET_ALL}\n")

        # Load .env file
        env_vars = {
            'CONTRACT_ADDRESS': os.getenv('CONTRACT_ADDRESS'),
            'PRIVATE_KEY': os.getenv('PRIVATE_KEY', '')[:10] + '****',
            'FLASHBOTS_RELAY_URL': os.getenv('FLASHBOTS_RELAY_URL', 'https://relay.flashbots.net'),
            'ENABLE_SANDWICH': os.getenv('ENABLE_SANDWICH', 'true'),
            'ENABLE_ARBITRAGE': os.getenv('ENABLE_ARBITRAGE', 'true'),
            'ENABLE_ML': os.getenv('ENABLE_ML', 'true'),
            'ARBITRAGE_SCAN_INTERVAL': os.getenv('ARBITRAGE_SCAN_INTERVAL', '60'),
        }

        for key, value in env_vars.items():
            print(f"  {key}: {value}")

        print(f"\n{Fore.YELLOW}Sandwich Bot Parameters:{Style.RESET_ALL}")
        print(f"  MIN_VICTIM_VALUE_USD: $50,000 (min swap size to sandwich)")
        print(f"  MIN_PROFIT_USD: $10.00 (min profit to execute)")
        print(f"  FLASHBOTS_BRIBE_PERCENTAGE: 15% (of gross profit)")

        print(f"\n{Fore.YELLOW}Arbitrage Bot Parameters:{Style.RESET_ALL}")
        print(f"  MIN_TVL: $3,000 (min pool liquidity)")
        print(f"  MIN_PROFIT: $1.00 (after gas)")
        print(f"  MAX_HOPS: Dynamic (based on gas price)")

        print(f"\n{Fore.CYAN}Note: Edit .env file or bot source code to change parameters{Style.RESET_ALL}")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    def show_statistics(self):
        """Show ML learning progress and trade history"""
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'📈 STATISTICS & ML LEARNING PROGRESS':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Try to load trade history
        import json
        from pathlib import Path

        history_file = Path('./trade_history.json')

        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    trades = json.load(f)

                print(f"{Fore.YELLOW}Trade History Summary:{Style.RESET_ALL}\n")
                print(f"  Total Trades: {len(trades)}")

                if trades:
                    successful = [t for t in trades if t.get('success', False)]
                    failed = [t for t in trades if not t.get('success', False)]

                    print(f"  Successful: {len(successful)} ({len(successful)/len(trades)*100:.1f}%)")
                    print(f"  Failed: {len(failed)} ({len(failed)/len(trades)*100:.1f}%)")

                    total_profit = sum(t.get('net_profit_usd', 0) for t in trades)
                    avg_profit = total_profit / len(trades) if trades else 0

                    print(f"\n  Total Profit: ${total_profit:.2f}")
                    print(f"  Average Profit per Trade: ${avg_profit:.2f}")

                    # Strategy breakdown
                    strategies = {}
                    for t in trades:
                        strat = t.get('strategy', 'unknown')
                        if strat not in strategies:
                            strategies[strat] = {'count': 0, 'success': 0, 'profit': 0}
                        strategies[strat]['count'] += 1
                        if t.get('success', False):
                            strategies[strat]['success'] += 1
                        strategies[strat]['profit'] += t.get('net_profit_usd', 0)

                    print(f"\n{Fore.YELLOW}Strategy Performance:{Style.RESET_ALL}\n")
                    for strat, stats in strategies.items():
                        success_rate = (stats['success'] / stats['count'] * 100) if stats['count'] > 0 else 0
                        print(f"  {strat}:")
                        print(f"    Trades: {stats['count']}")
                        print(f"    Success Rate: {success_rate:.1f}%")
                        print(f"    Total Profit: ${stats['profit']:.2f}")
                        print()

                    # Show recent trades
                    print(f"{Fore.YELLOW}Recent Trades (Last 5):{Style.RESET_ALL}\n")
                    for i, trade in enumerate(trades[-5:], 1):
                        status = f"{Fore.GREEN}✅ SUCCESS{Style.RESET_ALL}" if trade.get('success') else f"{Fore.RED}❌ FAILED{Style.RESET_ALL}"
                        profit = trade.get('net_profit_usd', 0)
                        strategy = trade.get('strategy', 'unknown')

                        print(f"  {i}. {status} | {strategy} | ${profit:.2f}")

            except Exception as e:
                print(f"{Fore.RED}Error loading trade history: {e}{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}No trade history found yet.{Style.RESET_ALL}")
            print(f"Trade history will be created once you start trading with ML enabled.")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    async def run_test_mode(self):
        """Test mode - dry run without executing"""
        self.clear_screen()
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"{'🧪 TEST MODE (DRY RUN)':^80}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        print(f"{Fore.YELLOW}This mode will scan for opportunities but NOT execute trades.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Useful for testing configuration and monitoring opportunities.{Style.RESET_ALL}\n")

        try:
            from unified_mev_bot import UnifiedMEVBot

            bot = UnifiedMEVBot(
                contract_address=self.contract_address,
                private_key=self.private_key,
                enable_mempool=False,
                enable_ml=False
            )

            print(f"{Fore.CYAN}Running one scan cycle...{Style.RESET_ALL}\n")

            # Override execute to prevent actual execution
            original_execute = bot.execute_opportunity

            def mock_execute(opp, strategy, decision):
                print(f"\n{Fore.YELLOW}[DRY RUN] Would execute:{Style.RESET_ALL}")
                print(f"  Strategy: {strategy}")
                print(f"  Path: {opp.get('path', 'Unknown')}")
                print(f"  Expected Profit: ${opp.get('profit_usd', 0):.2f}")
                return None

            bot.execute_opportunity = mock_execute

            # Run one scan
            result = bot.run_once()

            print(f"\n{Fore.GREEN}Test scan complete!{Style.RESET_ALL}")
            print(f"  Opportunities found: {result.get('scans', 0)}")

        except Exception as e:
            print(f"\n{Fore.RED}❌ ERROR: {e}{Style.RESET_ALL}")

        input(f"\n{Fore.CYAN}Press Enter to return to main menu...{Style.RESET_ALL}")

    async def run(self):
        """Main menu loop"""
        while True:
            self.clear_screen()
            self.print_header()
            self.print_menu()

            choice = self.get_choice()

            if choice == '1':
                await self.run_automatic_mode()
            elif choice == '2':
                await self.run_sandwich_only()
            elif choice == '3':
                self.run_arbitrage_only()
            elif choice == '4':
                await self.run_dual_mode()
            elif choice == '5':
                self.show_configuration()
            elif choice == '6':
                self.show_statistics()
            elif choice == '7':
                await self.run_test_mode()
            elif choice == '8':
                print(f"\n{Fore.CYAN}Goodbye! 👋{Style.RESET_ALL}\n")
                sys.exit(0)
            else:
                print(f"\n{Fore.RED}Invalid choice. Please try again.{Style.RESET_ALL}")
                await asyncio.sleep(1)


if __name__ == "__main__":
    print(f"{Fore.CYAN}Initializing MEV Bot Control Center...{Style.RESET_ALL}")

    menu = MEVBotMenu()

    try:
        asyncio.run(menu.run())
    except KeyboardInterrupt:
        print(f"\n\n{Fore.CYAN}Goodbye! 👋{Style.RESET_ALL}\n")
        sys.exit(0)
