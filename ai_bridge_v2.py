#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Bridge V2 - ArbiGirl with Consolidated Core
Uses the new arb_core.py module with AI monitoring and cache awareness

Features:
- Run components independently (fetch_pools, find_arbitrage, run_full_scan)
- AI monitoring for every call and calculation
- Cache expiration warnings with auto-fetch option
- Ask ArbiGirl questions about any operation

Usage:
  python ai_bridge_v2.py
"""

import os
import sys
import time
import queue
import threading
from typing import Optional, Dict, List
from colorama import Fore, Style, init

# Import the consolidated core
from arb_core import ConsolidatedArbSystem
from cache import Cache
from rpc_mgr import RPCManager

init(autoreset=True)


class ArbiGirl:
    """
    AI-powered arbitrage assistant using the consolidated core system.
    Can run any component independently or together as a well-oiled machine.
    """

    def __init__(self):
        """Initialize ArbiGirl with the consolidated arbitrage system"""
        print(f"\n{Fore.MAGENTA}{'='*80}")
        print(f"         🤖 ArbiGirl MEV Bot v4.0 - Consolidated Core Edition")
        print(f"         Run any component independently or together!")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Initialize consolidated system
        self.system = ConsolidatedArbSystem(
            min_tvl_usd=10000,
            min_profit_usd=1.0
        )

        # State
        self.auto_scan = False
        self.auto_fetch_on_expire = False
        self.last_opportunities = []
        self.scan_count = 0

        print(f"{Fore.GREEN}✓ ArbiGirl initialized with consolidated core!{Style.RESET_ALL}")
        print(f"  • Data Fetcher: Ready (1hr pair cache, 3hr TVL cache)")
        print(f"  • Arb Engine: Ready (instant arb detection from cache)")
        print(f"  • AI Monitor: Ready (tracks every operation)")
        self._show_help()

    def _show_help(self):
        """Show available commands"""
        print(f"\n{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}fetch{Style.RESET_ALL}        - Fetch fresh pool data (caches for 1hr/3hr)")
        print(f"  {Fore.YELLOW}scan{Style.RESET_ALL}         - Find arbitrage from cached data (instant)")
        print(f"  {Fore.YELLOW}full{Style.RESET_ALL}         - Run full scan (fetch + find arbs)")
        print(f"  {Fore.YELLOW}auto{Style.RESET_ALL}         - Toggle automatic scanning every 5s")
        print(f"  {Fore.YELLOW}ask <question>{Style.RESET_ALL} - Ask me about any operation")
        print(f"  {Fore.YELLOW}cache{Style.RESET_ALL}        - Check cache status and expiration")
        print(f"  {Fore.YELLOW}stats{Style.RESET_ALL}        - Show AI monitor statistics")
        print(f"  {Fore.YELLOW}status{Style.RESET_ALL}       - Show current status")
        print(f"  {Fore.YELLOW}clear{Style.RESET_ALL}        - Clear the screen")
        print(f"  {Fore.YELLOW}help{Style.RESET_ALL}         - Show this help")
        print(f"  {Fore.YELLOW}exit{Style.RESET_ALL}         - Exit ArbiGirl")

    def handle_fetch(self):
        """Fetch fresh pool data and cache it"""
        print(f"\n{Fore.CYAN}📡 Fetching fresh pool data...{Style.RESET_ALL}")
        start_time = time.time()

        try:
            pools = self.system.fetch_pools()
            elapsed = time.time() - start_time

            pool_count = sum(len(pairs) for pairs in pools.values())

            print(f"\n{Fore.GREEN}✅ Fetch complete!{Style.RESET_ALL}")
            print(f"  • Pools fetched: {pool_count}")
            print(f"  • Time: {elapsed:.2f}s")
            print(f"  • Cached: Pair prices (1hr), TVL (3hr)")

            return pools

        except Exception as e:
            print(f"\n{Fore.RED}❌ Fetch failed: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            return None

    def handle_scan(self):
        """Find arbitrage from cached data (instant)"""
        print(f"\n{Fore.CYAN}💰 Scanning for arbitrage (using cached data)...{Style.RESET_ALL}")

        # Check cache status first
        status = self.system.check_cache_status()
        pair_status = status.get('pair_prices', {})
        tvl_status = status.get('tvl_data', {})

        if pair_status.get('expired') or tvl_status.get('expired'):
            print(f"\n{Fore.YELLOW}⚠️  Cache expired! Running fresh fetch first...{Style.RESET_ALL}")

            if self.auto_fetch_on_expire:
                pools = self.handle_fetch()
                if not pools:
                    return
            else:
                # Ask user
                response = input(f"\n{Fore.YELLOW}Fetch fresh data? (y/n): {Style.RESET_ALL}").strip().lower()
                if response == 'y':
                    pools = self.handle_fetch()
                    if not pools:
                        return
                else:
                    print(f"\n{Fore.YELLOW}Using stale cache data...{Style.RESET_ALL}")
                    pools = {}  # Will use whatever is in cache

        start_time = time.time()

        try:
            # Get pools from cache (or recently fetched)
            if not hasattr(self, '_last_fetched_pools'):
                # Fetch if never fetched
                pools = self.handle_fetch()
                if not pools:
                    return
                self._last_fetched_pools = pools
            else:
                pools = self._last_fetched_pools

            # Find arbitrage
            opportunities = self.system.find_arbitrage(pools)
            elapsed = time.time() - start_time

            self.last_opportunities = opportunities
            self.scan_count += 1

            if opportunities:
                print(f"\n{Fore.GREEN}✨ Found {len(opportunities)} opportunities!{Style.RESET_ALL}\n")
                for i, opp in enumerate(opportunities[:5], 1):
                    print(f"  {i}. {opp['pair']}: ${opp['profit_usd']:.2f} profit ({opp['roi_percent']:.2f}% ROI)")
                    print(f"     Buy: {opp['dex_buy']} | Sell: {opp['dex_sell']}")
                    print()
            else:
                print(f"\n{Fore.YELLOW}No opportunities found this scan.{Style.RESET_ALL}")

            print(f"\n{Fore.BLUE}Scan completed in {elapsed:.2f}s (instant - using cache){Style.RESET_ALL}")

        except Exception as e:
            print(f"\n{Fore.RED}❌ Scan failed: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()

    def handle_full(self):
        """Run full scan (fetch + find arbitrage)"""
        print(f"\n{Fore.CYAN}🔄 Running full scan (fetch + arb detection)...{Style.RESET_ALL}")

        start_time = time.time()

        try:
            opportunities = self.system.run_full_scan()
            elapsed = time.time() - start_time

            self.last_opportunities = opportunities
            self.scan_count += 1

            if opportunities:
                print(f"\n{Fore.GREEN}✨ Found {len(opportunities)} opportunities!{Style.RESET_ALL}\n")
                for i, opp in enumerate(opportunities[:5], 1):
                    print(f"  {i}. {opp['pair']}: ${opp['profit_usd']:.2f} profit ({opp['roi_percent']:.2f}% ROI)")
                    print(f"     Buy: {opp['dex_buy']} | Sell: {opp['dex_sell']}")
                    print()
            else:
                print(f"\n{Fore.YELLOW}No opportunities found this scan.{Style.RESET_ALL}")

            print(f"\n{Fore.BLUE}Full scan completed in {elapsed:.2f}s{Style.RESET_ALL}")

            # Store for future instant scans
            # (pools are already in cache)

        except Exception as e:
            print(f"\n{Fore.RED}❌ Scan failed: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()

    def handle_auto(self):
        """Toggle automatic scanning"""
        self.auto_scan = not self.auto_scan

        if self.auto_scan:
            print(f"\n{Fore.GREEN}🔄 Automatic scanning ENABLED{Style.RESET_ALL}")
            print(f"  Scanning every 5 seconds...")
            print(f"  Type 'auto' again to stop")

            # Ask about auto-fetch on expire
            response = input(f"\n{Fore.YELLOW}Auto-fetch on cache expiry? (y/n): {Style.RESET_ALL}").strip().lower()
            self.auto_fetch_on_expire = (response == 'y')

            if self.auto_fetch_on_expire:
                print(f"{Fore.GREEN}✓ Will auto-fetch fresh data when cache expires{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠️  Will prompt before fetching on expiry{Style.RESET_ALL}")

            # Start auto scan in background
            thread = threading.Thread(target=self._auto_scan_loop, daemon=True)
            thread.start()
        else:
            print(f"\n{Fore.YELLOW}🛑 Automatic scanning DISABLED{Style.RESET_ALL}")

    def _auto_scan_loop(self):
        """Background loop for automatic scanning"""
        while self.auto_scan:
            try:
                self.handle_scan()
                time.sleep(5)
            except Exception as e:
                print(f"\n{Fore.RED}Auto-scan error: {e}{Style.RESET_ALL}")
                time.sleep(5)

    def handle_ask(self, question: str):
        """Ask ArbiGirl a question about operations"""
        if not question:
            print(f"\n{Fore.YELLOW}Usage: ask <your question>{Style.RESET_ALL}")
            print(f"Examples:")
            print(f"  • ask what coins were checked?")
            print(f"  • ask how many opportunities found?")
            print(f"  • ask show me the latest opportunities")
            print(f"  • ask show stats")
            return

        print(f"\n{Fore.MAGENTA}ArbiGirl: {Style.RESET_ALL}", end="")
        answer = self.system.ask_arbigirl(question)
        print(answer)

    def handle_cache(self):
        """Check cache status"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💾 CACHE STATUS")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        status = self.system.check_cache_status()

        for cache_type, cache_status in status.items():
            if cache_status['entry_count'] == 0:
                continue

            expired = cache_status['expired']
            time_left = cache_status['time_remaining']
            percentage = cache_status['percentage_fresh']
            count = cache_status['entry_count']
            duration = cache_status['duration'] / 3600

            if expired:
                status_icon = f"{Fore.RED}❌ EXPIRED"
            elif time_left < 300:  # < 5 min
                status_icon = f"{Fore.YELLOW}⚠️  EXPIRING SOON"
            else:
                status_icon = f"{Fore.GREEN}✅ FRESH"

            print(f"  {status_icon} {cache_type.upper()}{Style.RESET_ALL}")
            print(f"     Entries: {count}")
            print(f"     Duration: {duration:.0f}h")

            if not expired:
                hours_left = time_left / 3600
                mins_left = (time_left % 3600) / 60
                print(f"     Time left: {hours_left:.0f}h {mins_left:.0f}m")
                print(f"     Freshness: {percentage:.1f}%")

            print()

        # Show warning if any critical cache expired
        warning = self.system.cache.get_expiration_warning()
        if warning:
            print(f"{Fore.YELLOW}{warning}{Style.RESET_ALL}\n")
            print(f"{Fore.CYAN}Recommendation: Run 'fetch' to get fresh data{Style.RESET_ALL}")

        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    def handle_stats(self):
        """Show AI monitor statistics"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 AI MONITOR STATISTICS")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        stats = self.system.get_ai_stats()

        print(f"  • Total fetches: {stats['total_fetches']:,}")
        print(f"  • Total calculations: {stats['total_calculations']:,}")
        print(f"  • Total arb checks: {stats['total_arb_checks']:,}")
        print(f"  • Total opportunities: {stats['total_opportunities_found']:,}")
        print(f"\n  • User scans: {self.scan_count}")
        print(f"  • Last opportunities: {len(self.last_opportunities)}")

        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        print(f"{Fore.YELLOW}Ask me questions like:{Style.RESET_ALL}")
        print(f"  • 'ask what coins were checked?'")
        print(f"  • 'ask show me the latest opportunities'")

    def handle_status(self):
        """Show current status"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"         System Status")
        print(f"{'='*80}{Style.RESET_ALL}")

        print(f"  • Scanner: Consolidated Core (arb_core.py)")
        print(f"  • Auto-scan: {'ON' if self.auto_scan else 'OFF'}")
        print(f"  • Auto-fetch on expire: {'ON' if self.auto_fetch_on_expire else 'OFF'}")
        print(f"  • Total scans: {self.scan_count}")
        print(f"  • Last opportunities: {len(self.last_opportunities)}")

        # Cache status summary
        status = self.system.check_cache_status()
        pair_status = status.get('pair_prices', {})
        tvl_status = status.get('tvl_data', {})

        print(f"\n  {Fore.CYAN}Cache:{Style.RESET_ALL}")

        if pair_status.get('expired'):
            print(f"    • Pair prices: {Fore.RED}EXPIRED{Style.RESET_ALL}")
        else:
            time_left = pair_status.get('time_remaining', 0) / 60
            print(f"    • Pair prices: {Fore.GREEN}FRESH{Style.RESET_ALL} ({time_left:.0f}m left)")

        if tvl_status.get('expired'):
            print(f"    • TVL data: {Fore.RED}EXPIRED{Style.RESET_ALL}")
        else:
            time_left = tvl_status.get('time_remaining', 0) / 60
            print(f"    • TVL data: {Fore.GREEN}FRESH{Style.RESET_ALL} ({time_left:.0f}m left)")

        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    def handle_clear(self):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\n{Fore.MAGENTA}{'='*80}")
        print(f"         🤖 ArbiGirl MEV Bot v4.0")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        self._show_help()

    def run(self):
        """Main CLI loop"""
        print(f"\n{Fore.GREEN}Ready! Type commands or ask me questions naturally.{Style.RESET_ALL}\n")

        while True:
            try:
                user_input = input(f"{Fore.MAGENTA}You> {Style.RESET_ALL}").strip()

                if not user_input:
                    continue

                # Parse command
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if command in ['exit', 'quit', 'bye']:
                    print(f"\n{Fore.MAGENTA}👋 Goodbye!{Style.RESET_ALL}\n")
                    break

                elif command == 'fetch':
                    self.handle_fetch()

                elif command == 'scan':
                    self.handle_scan()

                elif command == 'full':
                    self.handle_full()

                elif command == 'auto':
                    self.handle_auto()

                elif command == 'ask':
                    self.handle_ask(args)

                elif command == 'cache':
                    self.handle_cache()

                elif command == 'stats':
                    self.handle_stats()

                elif command == 'status':
                    self.handle_status()

                elif command == 'clear':
                    self.handle_clear()

                elif command == 'help':
                    self._show_help()

                else:
                    print(f"{Fore.YELLOW}Unknown command: '{command}'. Type 'help' for available commands.{Style.RESET_ALL}")

            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Use 'exit' to quit{Style.RESET_ALL}")

            except Exception as e:
                print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()


def main():
    """Main entry point"""
    try:
        # Check for required files
        required_files = ['arb_core.py', 'cache.py', 'rpc_mgr.py', 'price_math.py', 'registries.py', 'price_fetcher.py']
        missing = [f for f in required_files if not os.path.exists(f)]

        if missing:
            print(f"{Fore.RED}Missing required files:{Style.RESET_ALL}")
            for file in missing:
                print(f"  • {file}")
            print(f"\n{Fore.YELLOW}Please make sure all files are in the same directory!{Style.RESET_ALL}")
            return

        # Start ArbiGirl
        bot = ArbiGirl()
        bot.run()

    except Exception as e:
        print(f"{Fore.RED}Failed to start ArbiGirl: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
