#!/usr/bin/env python3
"""
Integrated MEV Scanner
Combines pool discovery, cross-DEX comparison, and mempool monitoring
"""

import asyncio
import time
from datetime import datetime
from colorama import Fore, Style, init

from rpc_mgr import RPCManager
from cache import Cache
from cross_dex_comparator import CrossDEXComparator
from mempool_monitor import MempoolMonitor

init(autoreset=True)


class IntegratedMEVScanner:
    """
    Unified MEV opportunity scanner combining:
    1. Cross-DEX arbitrage detection
    2. Mempool sandwich opportunities
    3. Real-time monitoring
    """

    def __init__(self):
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🚀 INITIALIZING INTEGRATED MEV SCANNER")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Initialize components
        self.rpc_mgr = RPCManager()
        self.cache = Cache()

        print(f"{Fore.YELLOW}📊 Initializing Cross-DEX Comparator...{Style.RESET_ALL}")
        self.comparator = CrossDEXComparator(self.rpc_mgr, min_profit_bps=50)

        print(f"\n{Fore.YELLOW}👀 Initializing Mempool Monitor...{Style.RESET_ALL}")
        self.mempool_monitor = MempoolMonitor(self.rpc_mgr, min_swap_value_usd=5000)

        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"✅ MEV SCANNER READY")
        print(f"{'='*80}{Style.RESET_ALL}\n")

    def scan_cross_dex_opportunities(self, token_pairs: list = None):
        """
        Scan for cross-DEX arbitrage opportunities

        Args:
            token_pairs: List of (tokenA, tokenB) tuples to check
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"💱 SCANNING CROSS-DEX ARBITRAGE")
        print(f"{'='*80}{Style.RESET_ALL}")

        if token_pairs is None:
            # Default high-liquidity pairs
            token_pairs = [
                ('WETH', 'USDC'),
                ('WETH', 'USDT'),
                ('WETH', 'DAI'),
                ('WBTC', 'WETH'),
                ('WBTC', 'USDC'),
                ('WPOL', 'USDC'),
                ('WPOL', 'WETH'),
                ('AAVE', 'WETH'),
                ('LINK', 'WETH'),
                ('SUSHI', 'WETH'),
            ]

        all_opportunities = []

        for token_a, token_b in token_pairs:
            try:
                opps = self.comparator.compare_pair(token_a, token_b)
                all_opportunities.extend(opps)
                time.sleep(0.5)  # Rate limit
            except Exception as e:
                print(f"{Fore.RED}❌ Error comparing {token_a}/{token_b}: {e}{Style.RESET_ALL}")

        # Print summary
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 CROSS-DEX SCAN COMPLETE")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Pairs checked: {len(token_pairs)}")
        print(f"   Opportunities: {len(all_opportunities)}")

        if all_opportunities:
            print(f"\n{Fore.GREEN}💰 PROFITABLE OPPORTUNITIES:{Style.RESET_ALL}")
            for i, opp in enumerate(sorted(all_opportunities, key=lambda x: x['net_profit_bps'], reverse=True), 1):
                print(f"   {i}. {opp['pair']:15s} | {opp['buy_dex']:15s} → {opp['sell_dex']:15s} | "
                      f"{opp['net_profit_pct']:>5.2f}% (${opp['estimated_profit_usd']:>7.2f})")

        return all_opportunities

    async def monitor_mempool_continuous(self):
        """Start continuous mempool monitoring"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"👀 STARTING MEMPOOL MONITORING")
        print(f"{'='*80}{Style.RESET_ALL}")

        async def on_opportunity(tx_hash):
            # Callback for when opportunity is detected
            pass

        await self.mempool_monitor.monitor_mempool(callback=on_opportunity)

    async def run_hybrid_scanner(self, scan_interval: int = 60):
        """
        Run hybrid scanner:
        - Continuous mempool monitoring
        - Periodic cross-DEX scans

        Args:
            scan_interval: Seconds between cross-DEX scans
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🚀 STARTING HYBRID MEV SCANNER")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Cross-DEX scan interval: {scan_interval}s")
        print(f"   Mempool: Continuous monitoring")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Start mempool monitoring in background
        mempool_task = asyncio.create_task(self.monitor_mempool_continuous())

        # Periodic cross-DEX scans
        while True:
            try:
                print(f"\n{Fore.YELLOW}⏰ {datetime.now().strftime('%H:%M:%S')} - Running cross-DEX scan...{Style.RESET_ALL}")

                # Run cross-DEX scan (blocking)
                opportunities = self.scan_cross_dex_opportunities()

                # Sleep until next scan
                print(f"\n{Fore.CYAN}💤 Next scan in {scan_interval}s...{Style.RESET_ALL}")
                await asyncio.sleep(scan_interval)

            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Stopping scanner...{Style.RESET_ALL}")
                mempool_task.cancel()
                break

            except Exception as e:
                print(f"\n{Fore.RED}❌ Error in hybrid scanner: {e}{Style.RESET_ALL}")
                await asyncio.sleep(10)

    def run_single_scan(self):
        """Run a single cross-DEX scan (no mempool monitoring)"""
        return self.scan_cross_dex_opportunities()


async def main():
    """Main entry point with interactive menu"""
    scanner = IntegratedMEVScanner()

    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"🎮 SELECT MODE")
    print(f"{'='*80}{Style.RESET_ALL}")
    print(f"1. Single Cross-DEX Scan")
    print(f"2. Continuous Mempool Monitoring")
    print(f"3. Hybrid Mode (both)")
    print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")

    choice = input(f"\n{Fore.YELLOW}Select mode (1-3): {Style.RESET_ALL}").strip()

    if choice == '1':
        # Single scan
        scanner.run_single_scan()

    elif choice == '2':
        # Mempool only
        await scanner.monitor_mempool_continuous()

    elif choice == '3':
        # Hybrid mode
        await scanner.run_hybrid_scanner(scan_interval=60)

    else:
        print(f"{Fore.RED}Invalid choice{Style.RESET_ALL}")


if __name__ == "__main__":
    asyncio.run(main())
