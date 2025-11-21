#!/usr/bin/env python3
"""
Mempool Monitor
Monitors pending transactions for large swaps and detects sandwich opportunities
"""

import asyncio
import time
from typing import Dict, Optional, Callable
from web3 import Web3
from colorama import Fore, Style, init
import logging

from registries import DEXES, TOKENS
from rpc_mgr import RPCManager

init(autoreset=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MempoolMonitor:
    """
    Monitors mempool for profitable MEV opportunities
    Detects:
    - Large swaps (frontrun/sandwich targets)
    - Arbitrage triggers
    - Liquidation opportunities
    """

    # Known DEX router addresses
    DEX_ROUTERS = {
        '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff': 'QuickSwap_V2',
        '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506': 'SushiSwap',
        '0xE592427A0AEce92De3Edee1F18E0157C05861564': 'Uniswap_V3',
        '0xC0788A3aD43d79aa53B09c2EaCc313A787d1d607': 'ApeSwap',
        '0xA102072A4C07F06EC3B4900FDC4C7B80b6c57429': 'Dfyn',
    }

    # Swap function signatures
    SWAP_SIGS = {
        '0x38ed1739': 'swapExactTokensForTokens',
        '0x8803dbee': 'swapTokensForExactTokens',
        '0x7ff36ab5': 'swapExactETHForTokens',
        '0x18cbafe5': 'swapExactTokensForETH',
        '0x414bf389': 'exactInputSingle',  # V3
        '0xc04b8d59': 'exactInput',        # V3
    }

    def __init__(
        self,
        rpc_manager: RPCManager,
        min_swap_value_usd: float = 10000,
        max_price_impact: float = 0.03
    ):
        """
        Args:
            rpc_manager: RPC manager
            min_swap_value_usd: Minimum swap size to monitor (default $10k)
            max_price_impact: Max price impact to sandwich (default 3%)
        """
        self.rpc_manager = rpc_manager
        self.w3 = rpc_manager.get_web3()
        self.min_swap_value = min_swap_value_usd
        self.max_price_impact = max_price_impact

        self.monitored_txs = {}
        self.sandwich_opportunities = []

        # Token address -> symbol
        self.addr_to_symbol = {}
        for sym, info in TOKENS.items():
            self.addr_to_symbol[info['address'].lower()] = sym

        logger.info(f"{Fore.GREEN}✅ Mempool Monitor initialized{Style.RESET_ALL}")
        logger.info(f"   Min swap value: ${min_swap_value_usd:,}")
        logger.info(f"   Max price impact: {max_price_impact*100}%")

    def is_dex_swap(self, tx: Dict) -> tuple[bool, Optional[str]]:
        """Check if transaction is a DEX swap"""
        if not tx or not tx.get('to'):
            return False, None

        to_addr = tx['to'].lower()
        if to_addr not in self.DEX_ROUTERS:
            return False, None

        input_data = tx.get('input', '0x')
        if len(input_data) < 10:
            return False, None

        sig = input_data[:10]
        if sig not in self.SWAP_SIGS:
            return False, None

        return True, self.DEX_ROUTERS[to_addr]

    def estimate_swap_value(self, tx: Dict) -> float:
        """Estimate swap value in USD (simplified)"""
        # This is a simplified estimation
        # In production, decode the tx input to get exact amounts
        value_eth = tx.get('value', 0) / 1e18

        if value_eth > 0:
            # ETH swap, estimate at ~$2000/ETH
            return value_eth * 2000

        # For token swaps, we'd need to decode input data
        # For now, return 0 (will be improved)
        return 0

    def calculate_sandwich_profit(self, target_tx: Dict, dex: str) -> Optional[Dict]:
        """
        Calculate potential sandwich profit

        Sandwich strategy:
        1. Frontrun: Buy token_out before victim's swap
        2. Victim: Executes swap at worse price (slippage)
        3. Backrun: Sell token_out after victim's swap

        Returns:
            Dict with sandwich parameters or None
        """
        # This is a simplified calculation
        # In production, simulate the swaps to get exact profits

        swap_value = self.estimate_swap_value(target_tx)

        if swap_value < self.min_swap_value:
            return None

        # Estimate price impact
        # (Simplified: 1% impact per $100k of swap)
        price_impact = (swap_value / 100000) * 0.01

        if price_impact > self.max_price_impact:
            return None

        # Estimate sandwich profit
        # Profit ≈ price_impact × frontrun_size
        # With frontrun_size = 50% of target_tx
        frontrun_size = swap_value * 0.5
        estimated_profit = price_impact * frontrun_size

        # Account for gas (simplified: $5)
        gas_cost = 5.0
        net_profit = estimated_profit - gas_cost

        if net_profit > 1.0:
            return {
                'target_tx': target_tx['hash'].hex() if 'hash' in tx else 'pending',
                'dex': dex,
                'target_value': swap_value,
                'price_impact': price_impact,
                'frontrun_size': frontrun_size,
                'estimated_profit': estimated_profit,
                'gas_cost': gas_cost,
                'net_profit': net_profit
            }

        return None

    async def process_pending_tx(self, tx_hash: str):
        """Process a single pending transaction"""
        try:
            tx = self.w3.eth.get_transaction(tx_hash)

            if not tx:
                return

            # Check if it's a DEX swap
            is_swap, dex = self.is_dex_swap(tx)

            if not is_swap:
                return

            logger.info(f"{Fore.CYAN}📥 Swap detected: {dex} | TX: {tx_hash.hex()[:10]}...{Style.RESET_ALL}")

            # Calculate sandwich opportunity
            sandwich = self.calculate_sandwich_profit(tx, dex)

            if sandwich:
                logger.info(f"{Fore.GREEN}🥪 SANDWICH OPPORTUNITY!{Style.RESET_ALL}")
                logger.info(f"   Target value: ${sandwich['target_value']:,.0f}")
                logger.info(f"   Est. profit: ${sandwich['net_profit']:.2f}")

                self.sandwich_opportunities.append(sandwich)

        except Exception as e:
            logger.debug(f"Error processing tx: {e}")

    async def monitor_mempool(self, callback: Optional[Callable] = None):
        """
        Monitor mempool for opportunities

        Args:
            callback: Optional async function to call for each opportunity
        """
        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"👀 STARTING MEMPOOL MONITORING")
        logger.info(f"{'='*80}{Style.RESET_ALL}")

        try:
            # Subscribe to pending transactions
            pending_filter = self.w3.eth.filter('pending')

            logger.info(f"{Fore.GREEN}✅ Subscribed to mempool{Style.RESET_ALL}")
            logger.info(f"   Monitoring for swaps ≥ ${self.min_swap_value:,}")

            while True:
                try:
                    # Get new pending transactions
                    for tx_hash in pending_filter.get_new_entries():
                        await self.process_pending_tx(tx_hash)

                        if callback:
                            await callback(tx_hash)

                    # Brief sleep to avoid hammering RPC
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info(f"\n{Fore.YELLOW}Stopping mempool monitor...{Style.RESET_ALL}")
            self.print_stats()

    def print_stats(self):
        """Print monitoring statistics"""
        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"📊 MEMPOOL MONITOR STATISTICS")
        logger.info(f"{'='*80}{Style.RESET_ALL}")
        logger.info(f"   Transactions monitored: {len(self.monitored_txs)}")
        logger.info(f"   Sandwich opportunities: {len(self.sandwich_opportunities)}")

        if self.sandwich_opportunities:
            total_profit = sum(s['net_profit'] for s in self.sandwich_opportunities)
            logger.info(f"   Total potential profit: ${total_profit:.2f}")

        logger.info(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")


async def main():
    """Example usage"""
    rpc_mgr = RPCManager()
    monitor = MempoolMonitor(rpc_mgr, min_swap_value_usd=5000)

    # Monitor mempool
    await monitor.monitor_mempool()


if __name__ == "__main__":
    asyncio.run(main())
