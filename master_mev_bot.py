"""
MASTER MEV BOT - Dual Strategy System

PRIMARY STRATEGY: Sandwich Attacks (Gemini's recommendation)
- Monitor mempool for large pending swaps
- Calculate sandwich profitability
- Execute frontrun -> victim -> backrun via Flashbots
- High profit potential ($100-1000 per sandwich)

SECONDARY STRATEGY: DEX Arbitrage (Backup)
- Runs in parallel as backup
- Catches price differences between DEXs
- Lower profit but consistent ($5-50 per arb)
- Zero victim impact (ethical)

The sandwich bot is PRIMARY. Arbitrage is just backup for when
mempool is quiet or no good sandwich opportunities exist.
"""

import asyncio
import os
import time
from datetime import datetime
from colorama import Fore, Style, init
import logging

from sandwich_bot import SandwichBot
from unified_mev_bot import UnifiedMEVBot
from rpc_mgr import RPCManager

init(autoreset=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MasterMEVBot:
    """
    Master orchestrator running both strategies:
    1. PRIMARY: Sandwich attacks (mempool monitoring)
    2. SECONDARY: Arbitrage (backup)
    """

    def __init__(
        self,
        contract_address: str,
        private_key: str,
        enable_sandwich: bool = True,
        enable_arbitrage: bool = True,
        enable_ml: bool = True
    ):
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🎯 MASTER MEV BOT - DUAL STRATEGY SYSTEM")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        self.contract_address = contract_address
        self.private_key = private_key
        self.enable_sandwich = enable_sandwich
        self.enable_arbitrage = enable_arbitrage

        # Initialize RPC manager
        print(f"{Fore.YELLOW}📡 Initializing RPC Manager...{Style.RESET_ALL}")
        self.rpc_manager = RPCManager()

        # Initialize PRIMARY: Sandwich Bot
        self.sandwich_bot = None
        if enable_sandwich:
            print(f"\n{Fore.GREEN}🥪 Initializing PRIMARY STRATEGY: Sandwich Bot{Style.RESET_ALL}")
            self.sandwich_bot = SandwichBot(
                rpc_manager=self.rpc_manager,
                contract_address=contract_address,
                private_key=private_key,
                flashbots_relay_url=os.getenv('FLASHBOTS_RELAY_URL', 'https://relay.flashbots.net')
            )
        else:
            print(f"\n{Fore.YELLOW}⚠️  Sandwich bot DISABLED{Style.RESET_ALL}")

        # Initialize SECONDARY: Arbitrage Bot
        self.arbitrage_bot = None
        if enable_arbitrage:
            print(f"\n{Fore.BLUE}📊 Initializing SECONDARY STRATEGY: Arbitrage Bot{Style.RESET_ALL}")
            self.arbitrage_bot = UnifiedMEVBot(
                contract_address=contract_address,
                private_key=private_key,
                enable_mempool=False,  # Sandwich handles mempool
                enable_ml=enable_ml
            )
        else:
            print(f"\n{Fore.YELLOW}⚠️  Arbitrage bot DISABLED{Style.RESET_ALL}")

        # Stats
        self.start_time = time.time()
        self.total_sandwich_profit = 0.0
        self.total_arbitrage_profit = 0.0

        print(f"\n{Fore.GREEN}✅ Master MEV Bot initialized!{Style.RESET_ALL}")
        print(f"   PRIMARY: Sandwich {'ENABLED' if enable_sandwich else 'DISABLED'}")
        print(f"   SECONDARY: Arbitrage {'ENABLED' if enable_arbitrage else 'DISABLED'}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    async def run_sandwich_monitor(self):
        """Run sandwich bot (PRIMARY) - monitors mempool continuously"""
        if not self.sandwich_bot:
            return

        print(f"{Fore.GREEN}🥪 Starting PRIMARY strategy: Sandwich mempool monitoring{Style.RESET_ALL}\n")

        try:
            await self.sandwich_bot.monitor_mempool()
        except Exception as e:
            logger.error(f"Sandwich monitor error: {e}")

    async def run_arbitrage_scanner(self, interval_seconds: int = 60):
        """Run arbitrage bot (SECONDARY) - scans periodically"""
        if not self.arbitrage_bot:
            return

        print(f"{Fore.BLUE}📊 Starting SECONDARY strategy: Arbitrage scanner (every {interval_seconds}s){Style.RESET_ALL}\n")

        scan_count = 0

        while True:
            try:
                scan_count += 1

                print(f"\n{Fore.BLUE}{'='*80}")
                print(f"📊 ARBITRAGE SCAN #{scan_count} (BACKUP STRATEGY)")
                print(f"{'='*80}{Style.RESET_ALL}")

                # Run one arbitrage scan
                result = self.arbitrage_bot.run_once()

                if result['profit'] > 0:
                    self.total_arbitrage_profit += result['profit']
                    print(f"{Fore.GREEN}✅ Arbitrage profit: ${result['profit']:.2f}{Style.RESET_ALL}")

                # Wait before next scan
                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.error(f"Arbitrage scanner error: {e}")
                await asyncio.sleep(interval_seconds)

    async def run_stats_reporter(self, interval_seconds: int = 300):
        """Print statistics every N seconds"""
        while True:
            await asyncio.sleep(interval_seconds)

            runtime = time.time() - self.start_time
            runtime_hours = runtime / 3600

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"📊 MASTER MEV BOT STATISTICS")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"   Runtime: {runtime_hours:.2f} hours")
            print(f"")
            print(f"   {Fore.GREEN}PRIMARY (Sandwich):{Style.RESET_ALL}")
            if self.sandwich_bot:
                print(f"      Swaps seen: {self.sandwich_bot.pending_swaps_seen:,}")
                print(f"      Sandwiches attempted: {self.sandwich_bot.sandwiches_attempted}")
                print(f"      Sandwiches successful: {self.sandwich_bot.sandwiches_successful}")
                print(f"      Total profit: ${self.sandwich_bot.total_profit:.2f}")
            else:
                print(f"      DISABLED")
            print(f"")
            print(f"   {Fore.BLUE}SECONDARY (Arbitrage):{Style.RESET_ALL}")
            if self.arbitrage_bot:
                print(f"      Scans: {self.arbitrage_bot.total_scans}")
                print(f"      Executions: {self.arbitrage_bot.total_executions}")
                print(f"      Total profit: ${self.arbitrage_bot.total_profit:.2f}")
            else:
                print(f"      DISABLED")
            print(f"")
            total = (self.sandwich_bot.total_profit if self.sandwich_bot else 0) + \
                    (self.arbitrage_bot.total_profit if self.arbitrage_bot else 0)
            print(f"   {Fore.YELLOW}TOTAL PROFIT: ${total:.2f}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    async def run(
        self,
        arbitrage_scan_interval: int = 60,
        stats_interval: int = 300
    ):
        """
        Run both strategies in parallel

        Args:
            arbitrage_scan_interval: How often to scan for arbitrage (seconds)
            stats_interval: How often to print stats (seconds)
        """
        print(f"\n{Fore.GREEN}🚀 Starting MASTER MEV BOT{Style.RESET_ALL}")
        print(f"   PRIMARY: Sandwich (continuous mempool monitoring)")
        print(f"   SECONDARY: Arbitrage (scans every {arbitrage_scan_interval}s)")
        print(f"   Stats: Every {stats_interval}s")
        print(f"\n{Fore.YELLOW}Press Ctrl+C to stop{Style.RESET_ALL}\n")

        tasks = []

        # Task 1: PRIMARY - Sandwich mempool monitoring (continuous)
        if self.enable_sandwich:
            tasks.append(asyncio.create_task(self.run_sandwich_monitor()))

        # Task 2: SECONDARY - Arbitrage scanner (periodic)
        if self.enable_arbitrage:
            tasks.append(asyncio.create_task(
                self.run_arbitrage_scanner(interval_seconds=arbitrage_scan_interval)
            ))

        # Task 3: Stats reporter
        tasks.append(asyncio.create_task(
                self.run_stats_reporter(interval_seconds=stats_interval)
        ))

        try:
            # Run all tasks in parallel
            await asyncio.gather(*tasks)

        except KeyboardInterrupt:
            print(f"\n\n{Fore.CYAN}{'='*80}")
            print(f"👋 SHUTTING DOWN MASTER MEV BOT")
            print(f"{'='*80}{Style.RESET_ALL}")

            runtime = time.time() - self.start_time
            runtime_hours = runtime / 3600

            print(f"   Total runtime: {runtime_hours:.2f} hours")
            print(f"")

            if self.sandwich_bot:
                print(f"   {Fore.GREEN}PRIMARY (Sandwich):{Style.RESET_ALL}")
                print(f"      Profit: ${self.sandwich_bot.total_profit:.2f}")
                print(f"      Success rate: {(self.sandwich_bot.sandwiches_successful/max(self.sandwich_bot.sandwiches_attempted,1))*100:.1f}%")
                print(f"")

            if self.arbitrage_bot:
                print(f"   {Fore.BLUE}SECONDARY (Arbitrage):{Style.RESET_ALL}")
                print(f"      Profit: ${self.arbitrage_bot.total_profit:.2f}")
                print(f"")

            total = (self.sandwich_bot.total_profit if self.sandwich_bot else 0) + \
                    (self.arbitrage_bot.total_profit if self.arbitrage_bot else 0)
            print(f"   {Fore.YELLOW}TOTAL PROFIT: ${total:.2f}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")


# Main entry point
if __name__ == "__main__":
    # Configuration from environment
    CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')
    PRIVATE_KEY = os.getenv('PRIVATE_KEY')
    ENABLE_SANDWICH = os.getenv('ENABLE_SANDWICH', 'true').lower() == 'true'
    ENABLE_ARBITRAGE = os.getenv('ENABLE_ARBITRAGE', 'true').lower() == 'true'
    ENABLE_ML = os.getenv('ENABLE_ML', 'true').lower() == 'true'
    ARBITRAGE_INTERVAL = int(os.getenv('ARBITRAGE_SCAN_INTERVAL', '60'))

    if not CONTRACT_ADDRESS or not PRIVATE_KEY:
        print(f"{Fore.RED}❌ Missing CONTRACT_ADDRESS or PRIVATE_KEY in .env{Style.RESET_ALL}")
        exit(1)

    # Initialize master bot
    bot = MasterMEVBot(
        contract_address=CONTRACT_ADDRESS,
        private_key=PRIVATE_KEY,
        enable_sandwich=ENABLE_SANDWICH,
        enable_arbitrage=ENABLE_ARBITRAGE,
        enable_ml=ENABLE_ML
    )

    # Run both strategies
    asyncio.run(bot.run(
        arbitrage_scan_interval=ARBITRAGE_INTERVAL,
        stats_interval=300  # Stats every 5 minutes
    ))
