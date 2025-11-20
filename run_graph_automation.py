#!/usr/bin/env python3
"""
Background Graph-Based Arbitrage Automation
Runs continuously in the background using the graph method for finding opportunities

Features:
- Graph-based multi-hop arbitrage detection
- Continuous scanning with configurable intervals
- Auto-execution with flash loans (optional)
- Comprehensive logging and error handling
- Signal handling for graceful shutdown
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime
from pathlib import Path
from colorama import Fore, Style, init

# Import core bot components
from polygon_arb_bot import PolygonArbBot
from advanced_mev_module import GraphArbitrageFinder, AdvancedMEVModule
from dotenv import load_dotenv

init(autoreset=True)
load_dotenv()

# Configure logging
LOG_DIR = Path(os.getenv("LOG_DIR", "./logs"))
LOG_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"graph_automation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
SHUTDOWN_FLAG = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global SHUTDOWN_FLAG
    logger.info(f"\n{Fore.YELLOW}Received shutdown signal {signum}. Initiating graceful shutdown...{Style.RESET_ALL}")
    SHUTDOWN_FLAG = True


class GraphArbitrageAutomation:
    """
    Automated arbitrage bot using graph-based pathfinding
    Runs continuously in the background
    """

    def __init__(
        self,
        min_tvl: float = None,
        scan_interval: int = None,
        auto_execute: bool = None,
        use_graph_method: bool = True
    ):
        """
        Initialize the automation

        Args:
            min_tvl: Minimum pool TVL (default from env or 3000)
            scan_interval: Seconds between scans (default from env or 60)
            auto_execute: Enable auto-execution (default from env or False)
            use_graph_method: Use graph-based pathfinding (default True)
        """
        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"🚀 INITIALIZING GRAPH-BASED ARBITRAGE AUTOMATION")
        logger.info(f"{'='*80}{Style.RESET_ALL}\n")

        # Load configuration from environment with fallbacks
        self.min_tvl = min_tvl or float(os.getenv("MIN_TVL_USD", "3000"))
        self.scan_interval = scan_interval or int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
        self.auto_execute = auto_execute if auto_execute is not None else \
                           os.getenv("AUTO_EXECUTE", "false").lower() in ("true", "1", "yes")
        self.use_graph_method = use_graph_method

        # Initialize the main bot
        logger.info("Initializing PolygonArbBot...")
        self.bot = PolygonArbBot(
            min_tvl=self.min_tvl,
            scan_interval=self.scan_interval,
            auto_execute=self.auto_execute
        )

        # Initialize graph-based MEV module if enabled
        self.graph_finder = None
        self.mev_module = None

        if self.use_graph_method:
            logger.info(f"\n{Fore.YELLOW}Initializing Graph-Based Arbitrage Finder...{Style.RESET_ALL}")
            self.graph_finder = GraphArbitrageFinder(self.bot.arb_finder)

            # Optionally initialize full MEV module
            # self.mev_module = AdvancedMEVModule(self.bot)
            logger.info(f"{Fore.GREEN}✅ Graph method enabled{Style.RESET_ALL}")

        # Statistics
        self.start_time = time.time()
        self.total_scans = 0
        self.total_graph_opportunities = 0
        self.total_regular_opportunities = 0
        self.total_executions = 0
        self.errors = []

        logger.info(f"\n{Fore.GREEN}{'='*80}")
        logger.info(f"✅ AUTOMATION INITIALIZED SUCCESSFULLY")
        logger.info(f"{'='*80}{Style.RESET_ALL}")
        logger.info(f"  Min TVL: ${self.min_tvl:,.0f}")
        logger.info(f"  Scan Interval: {self.scan_interval}s")
        logger.info(f"  Auto Execute: {self.auto_execute}")
        logger.info(f"  Graph Method: {self.use_graph_method}")
        logger.info(f"  Log File: {log_file}")
        logger.info(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")

    def run_graph_scan(self) -> list:
        """
        Run a graph-based arbitrage scan

        Returns:
            List of opportunities found
        """
        try:
            logger.info(f"\n{Fore.CYAN}{'='*80}")
            logger.info(f"🔍 RUNNING GRAPH-BASED ARBITRAGE SCAN #{self.total_scans + 1}")
            logger.info(f"{'='*80}{Style.RESET_ALL}\n")

            start_time = time.time()

            # Fetch all pools
            logger.info(f"{Fore.YELLOW}Step 1/3: Fetching pool data...{Style.RESET_ALL}")
            pools = self.bot.scan_pools()

            pool_count = sum(len(pairs) for pairs in pools.values())
            logger.info(f"{Fore.GREEN}✓ Fetched {pool_count} pools{Style.RESET_ALL}")

            # Find opportunities using graph method
            logger.info(f"\n{Fore.YELLOW}Step 2/3: Finding arbitrage opportunities (GRAPH METHOD)...{Style.RESET_ALL}")

            if self.use_graph_method and self.graph_finder:
                # Use graph-based pathfinding
                base_tokens = os.getenv("BASE_TOKENS", "USDC,WETH,WPOL,DAI").split(",")
                test_amounts = [
                    float(amt) for amt in
                    os.getenv("TEST_AMOUNTS", "1000,5000,10000").split(",")
                ]

                opportunities = self.graph_finder.find_all_opportunities(
                    pools_data=pools,
                    base_tokens=base_tokens,
                    test_amounts=test_amounts
                )

                self.total_graph_opportunities += len(opportunities)
                logger.info(f"{Fore.GREEN}✓ Found {len(opportunities)} graph-based opportunities{Style.RESET_ALL}")
            else:
                # Fall back to regular 2-hop arbitrage
                opportunities = self.bot.find_arbitrage(pools)
                self.total_regular_opportunities += len(opportunities)
                logger.info(f"{Fore.GREEN}✓ Found {len(opportunities)} regular opportunities{Style.RESET_ALL}")

            # Display top opportunities
            logger.info(f"\n{Fore.YELLOW}Step 3/3: Analyzing results...{Style.RESET_ALL}")

            if opportunities:
                logger.info(f"\n{Fore.GREEN}{'='*80}")
                logger.info(f"💰 TOP OPPORTUNITIES")
                logger.info(f"{'='*80}{Style.RESET_ALL}\n")

                for i, opp in enumerate(opportunities[:5], 1):
                    logger.info(f"{Fore.GREEN}{i}. {opp.get('path', opp.get('pair', 'Unknown'))}{Style.RESET_ALL}")
                    logger.info(f"   Profit: ${opp.get('profit_usd', 0):.2f}")
                    logger.info(f"   ROI: {opp.get('roi_percent', opp.get('roi', 0)):.2f}%")

                    if 'route' in opp:
                        logger.info(f"   Route: {' → '.join([r['from'] for r in opp['route']] + [opp['route'][-1]['to']])}")
                    else:
                        logger.info(f"   Buy: {opp.get('dex_buy', 'N/A')}")
                        logger.info(f"   Sell: {opp.get('dex_sell', 'N/A')}")
                    logger.info("")

                logger.info(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")
            else:
                logger.info(f"\n{Fore.YELLOW}No profitable opportunities found in this scan.{Style.RESET_ALL}\n")

            elapsed = time.time() - start_time
            logger.info(f"⏱️  Scan completed in {elapsed:.2f}s\n")

            return opportunities

        except Exception as e:
            logger.error(f"\n{Fore.RED}{'='*80}")
            logger.error(f"❌ SCAN ERROR")
            logger.error(f"{'='*80}{Style.RESET_ALL}")
            logger.error(f"   Error: {str(e)}\n")

            import traceback
            traceback.print_exc()

            self.errors.append({
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'traceback': traceback.format_exc()
            })

            return []

    def print_statistics(self):
        """Print automation statistics"""
        uptime = time.time() - self.start_time
        uptime_hours = uptime / 3600

        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"📊 AUTOMATION STATISTICS")
        logger.info(f"{'='*80}{Style.RESET_ALL}")
        logger.info(f"  Uptime: {uptime_hours:.2f}h ({uptime/60:.1f}m)")
        logger.info(f"  Total Scans: {self.total_scans}")
        logger.info(f"  Graph Opportunities: {self.total_graph_opportunities}")
        logger.info(f"  Regular Opportunities: {self.total_regular_opportunities}")
        logger.info(f"  Total Executions: {self.total_executions}")
        logger.info(f"  Errors: {len(self.errors)}")

        if self.total_scans > 0:
            avg_graph_opps = self.total_graph_opportunities / self.total_scans
            avg_regular_opps = self.total_regular_opportunities / self.total_scans
            logger.info(f"  Avg Graph Opps/Scan: {avg_graph_opps:.2f}")
            logger.info(f"  Avg Regular Opps/Scan: {avg_regular_opps:.2f}")

        logger.info(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    def run_continuous(self):
        """
        Run continuous scanning loop
        Handles shutdown gracefully
        """
        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"🔁 STARTING CONTINUOUS GRAPH-BASED SCANNING")
        logger.info(f"{'='*80}{Style.RESET_ALL}")
        logger.info(f"  Scan Interval: {self.scan_interval}s")
        logger.info(f"  Min TVL: ${self.min_tvl:,.0f}")
        logger.info(f"  Auto Execute: {self.auto_execute}")
        logger.info(f"  Graph Method: {self.use_graph_method}")
        logger.info(f"  Press Ctrl+C to stop gracefully")
        logger.info(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        while not SHUTDOWN_FLAG:
            try:
                # Run graph-based scan
                opportunities = self.run_graph_scan()
                self.total_scans += 1

                # Auto-execute if enabled
                if self.auto_execute and opportunities and self.bot.auto_executor:
                    logger.info(f"\n{Fore.YELLOW}{'='*80}")
                    logger.info(f"⚡ AUTO-EXECUTION MODE ACTIVE")
                    logger.info(f"{'='*80}{Style.RESET_ALL}\n")

                    for i, opp in enumerate(opportunities, 1):
                        if SHUTDOWN_FLAG:
                            break

                        logger.info(f"\n{Fore.CYAN}[{i}/{len(opportunities)}] Evaluating opportunity...{Style.RESET_ALL}")

                        # Check if should execute
                        should_exec, reason, updated_opp = self.bot.auto_executor.should_execute(opp)

                        if should_exec:
                            # Execute the opportunity
                            result = self.bot.auto_executor.execute_opportunity(updated_opp or opp, self.bot)

                            if result.get("success"):
                                self.total_executions += 1
                                logger.info(f"{Fore.GREEN}✅ Execution #{self.total_executions} successful!{Style.RESET_ALL}\n")
                            else:
                                logger.info(f"{Fore.RED}❌ Execution failed: {result.get('error')}{Style.RESET_ALL}\n")
                        else:
                            logger.info(f"{Fore.YELLOW}⏭️  Skipped: {reason}{Style.RESET_ALL}\n")

                # Print statistics every 10 scans
                if self.total_scans % 10 == 0:
                    self.print_statistics()

                # Sleep until next scan (with early exit on shutdown)
                logger.info(f"{Fore.CYAN}💤 Sleeping {self.scan_interval}s until next scan...{Style.RESET_ALL}\n")

                for _ in range(self.scan_interval):
                    if SHUTDOWN_FLAG:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info(f"\n{Fore.YELLOW}Keyboard interrupt received. Shutting down...{Style.RESET_ALL}")
                break

            except Exception as e:
                logger.error(f"\n{Fore.RED}❌ Scan loop error: {e}{Style.RESET_ALL}\n")
                import traceback
                traceback.print_exc()

                self.errors.append({
                    'timestamp': datetime.now().isoformat(),
                    'error': str(e),
                    'traceback': traceback.format_exc()
                })

                logger.info(f"{Fore.YELLOW}Retrying in 10s...{Style.RESET_ALL}\n")
                time.sleep(10)

        # Cleanup
        logger.info(f"\n{Fore.YELLOW}{'='*80}")
        logger.info(f"⏹️  AUTOMATION STOPPED")
        logger.info(f"{'='*80}{Style.RESET_ALL}\n")

        self.print_statistics()

        if hasattr(self.bot, 'cleanup'):
            self.bot.cleanup()

        logger.info(f"{Fore.GREEN}✅ Shutdown complete{Style.RESET_ALL}\n")


def main():
    """Main entry point"""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize automation
        automation = GraphArbitrageAutomation(
            min_tvl=float(os.getenv("MIN_TVL_USD", "3000")),
            scan_interval=int(os.getenv("SCAN_INTERVAL_SECONDS", "60")),
            auto_execute=os.getenv("AUTO_EXECUTE", "false").lower() in ("true", "1", "yes"),
            use_graph_method=True  # Always use graph method
        )

        # Run continuous scanning
        automation.run_continuous()

    except Exception as e:
        logger.error(f"{Fore.RED}Failed to start automation: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
