"""
Execution Router - Multiple Execution Paths for Different Opportunity Types
Routes opportunities to the best execution method based on:
- Path length (2-hop vs 3+ hop)
- Gas costs
- Profit margins
- Capital requirements
"""

import os
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from colorama import Fore, Style, init
import logging

from registries import DEXES, get_token_address
from tx_builder import GasOptimizationManager

init(autoreset=True)
logger = logging.getLogger(__name__)


class ExecutionPath(Enum):
    """Execution path types"""
    FLASH_LOAN_2HOP = "flash_loan_2hop"      # Use existing contract (2-hop only)
    DIRECT_2HOP = "direct_2hop"               # Direct swap with wallet capital
    SKIP = "skip"                             # Skip execution (not profitable)


@dataclass
class ExecutionDecision:
    """Decision from router about how to execute"""
    path: ExecutionPath
    reason: str
    estimated_gas_usd: float
    estimated_profit_after_gas: float
    method_details: Dict


class ExecutionRouter:
    """
    Routes arbitrage opportunities to the optimal execution method

    Execution Paths:
    1. FLASH_LOAN_2HOP: Your existing contract (2-hop, zero capital)
    2. DIRECT_2HOP: Direct swaps with wallet funds (2-hop, requires capital)
    3. SKIP: Not profitable enough after gas
    """

    def __init__(self, gas_manager: GasOptimizationManager, min_profit_usd: float = 1.0):
        """
        Args:
            gas_manager: GasOptimizationManager instance for gas estimation
            min_profit_usd: Minimum profit threshold (after gas)
        """
        self.gas_mgr = gas_manager
        self.min_profit_usd = min_profit_usd

        # Gas cost estimates (in gas units)
        self.GAS_COSTS = {
            'flash_loan_2hop_aave': 450000,      # Flash loan + 2 swaps + Aave fee
            'flash_loan_2hop_balancer': 400000,  # Flash loan + 2 swaps (no fee)
            'direct_2hop': 250000,                # 2 direct swaps (no flash loan overhead)
        }

        # Flash loan fees
        self.FLASH_LOAN_FEES = {
            'aave': 0.0009,      # 0.09%
            'balancer': 0.0000   # 0.00% (FREE!)
        }

        logger.info(f"{Fore.GREEN}✅ Execution Router initialized{Style.RESET_ALL}")
        logger.info(f"   Min profit after gas: ${min_profit_usd}")
        logger.info(f"   Available paths: FLASH_LOAN_2HOP (2-hop zero capital), DIRECT_2HOP (requires capital)")

    def _calculate_gas_cost_usd(self, gas_units: int, pol_price_usd: float = 0.40) -> float:
        """Calculate gas cost in USD"""
        try:
            gas_params = self.gas_mgr.get_optimized_gas_params()
            max_fee_per_gas = gas_params['maxFeePerGas']

            # Gas cost in POL
            gas_cost_wei = gas_units * max_fee_per_gas
            gas_cost_pol = gas_cost_wei / 1e18

            # Convert to USD
            return gas_cost_pol * pol_price_usd
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}, using default 40 gwei")
            # Fallback: 40 gwei
            return (gas_units * 40e9 / 1e18) * pol_price_usd

    def _calculate_flash_loan_fee(self, amount_usd: float, provider: str = 'balancer') -> float:
        """Calculate flash loan fee in USD"""
        fee_pct = self.FLASH_LOAN_FEES.get(provider, 0)
        return amount_usd * fee_pct

    def decide_execution_path(
        self,
        opportunity: Dict,
        pol_price_usd: float = 0.40,
        has_capital: bool = False
    ) -> ExecutionDecision:
        """
        Decide the best execution path for an opportunity

        Args:
            opportunity: Arbitrage opportunity dict with:
                - path: List of tokens (e.g., ['USDC', 'WETH', 'USDC'])
                - hops: List of swap hops with dex info
                - gross_profit_usd: Profit before gas/fees
                - trade_size_usd: Trade size
            pol_price_usd: Current POL/MATIC price
            has_capital: Whether wallet has capital for direct swaps

        Returns:
            ExecutionDecision with chosen path and details
        """
        path_tokens = opportunity.get('path', [])
        hops = opportunity.get('hops', [])
        gross_profit = opportunity.get('gross_profit_usd', 0)
        trade_size = opportunity.get('trade_size_usd', 0)

        # Determine path length
        num_hops = len(hops) if hops else len(path_tokens) - 1

        logger.info(f"\n{Fore.CYAN}🔀 ROUTING DECISION{Style.RESET_ALL}")
        logger.info(f"   Path: {' → '.join(path_tokens)}")
        logger.info(f"   Hops: {num_hops}")
        logger.info(f"   Gross Profit: ${gross_profit:.2f}")
        logger.info(f"   Trade Size: ${trade_size:,.0f}")

        # ============================================================
        # PATH 1: 2-HOP OPPORTUNITIES
        # ============================================================
        if num_hops == 2:
            # Check both flash loan options

            # Option A: Balancer flash loan (FREE - 0% fee!)
            gas_cost_balancer = self._calculate_gas_cost_usd(
                self.GAS_COSTS['flash_loan_2hop_balancer'],
                pol_price_usd
            )
            flash_fee_balancer = self._calculate_flash_loan_fee(trade_size, 'balancer')
            net_profit_balancer = gross_profit - gas_cost_balancer - flash_fee_balancer

            logger.info(f"\n   💰 Balancer Flash Loan (0% fee):")
            logger.info(f"      Gas: ${gas_cost_balancer:.2f}")
            logger.info(f"      Flash fee: ${flash_fee_balancer:.2f}")
            logger.info(f"      Net profit: ${net_profit_balancer:.2f}")

            if net_profit_balancer >= self.min_profit_usd:
                return ExecutionDecision(
                    path=ExecutionPath.FLASH_LOAN_2HOP,
                    reason=f"Balancer flash loan: ${net_profit_balancer:.2f} profit (0% fee)",
                    estimated_gas_usd=gas_cost_balancer,
                    estimated_profit_after_gas=net_profit_balancer,
                    method_details={
                        'provider': 'balancer',
                        'gas_units': self.GAS_COSTS['flash_loan_2hop_balancer'],
                        'flash_fee_pct': 0.0,
                        'contract_function': 'executeBalancerFlashloan'
                    }
                )

            # Option B: Aave flash loan (0.09% fee)
            gas_cost_aave = self._calculate_gas_cost_usd(
                self.GAS_COSTS['flash_loan_2hop_aave'],
                pol_price_usd
            )
            flash_fee_aave = self._calculate_flash_loan_fee(trade_size, 'aave')
            net_profit_aave = gross_profit - gas_cost_aave - flash_fee_aave

            logger.info(f"\n   💰 Aave Flash Loan (0.09% fee):")
            logger.info(f"      Gas: ${gas_cost_aave:.2f}")
            logger.info(f"      Flash fee: ${flash_fee_aave:.2f}")
            logger.info(f"      Net profit: ${net_profit_aave:.2f}")

            if net_profit_aave >= self.min_profit_usd:
                return ExecutionDecision(
                    path=ExecutionPath.FLASH_LOAN_2HOP,
                    reason=f"Aave flash loan: ${net_profit_aave:.2f} profit (0.09% fee)",
                    estimated_gas_usd=gas_cost_aave,
                    estimated_profit_after_gas=net_profit_aave,
                    method_details={
                        'provider': 'aave',
                        'gas_units': self.GAS_COSTS['flash_loan_2hop_aave'],
                        'flash_fee_pct': 0.09,
                        'contract_function': 'executeFlashloan'
                    }
                )

            # Option C: Direct swap (if has capital)
            if has_capital:
                gas_cost_direct = self._calculate_gas_cost_usd(
                    self.GAS_COSTS['direct_2hop'],
                    pol_price_usd
                )
                net_profit_direct = gross_profit - gas_cost_direct

                logger.info(f"\n   💰 Direct Swap (requires ${trade_size:,.0f} capital):")
                logger.info(f"      Gas: ${gas_cost_direct:.2f}")
                logger.info(f"      Net profit: ${net_profit_direct:.2f}")

                if net_profit_direct >= self.min_profit_usd:
                    return ExecutionDecision(
                        path=ExecutionPath.DIRECT_2HOP,
                        reason=f"Direct swap: ${net_profit_direct:.2f} profit (saves flash loan fee)",
                        estimated_gas_usd=gas_cost_direct,
                        estimated_profit_after_gas=net_profit_direct,
                        method_details={
                            'gas_units': self.GAS_COSTS['direct_2hop'],
                            'capital_required_usd': trade_size
                        }
                    )

        # ============================================================
        # PATH 2: 3+ HOP OPPORTUNITIES
        # ============================================================
        elif num_hops >= 3:
            # Your existing flash loan contract doesn't support 3+ hops
            # Options:
            # A. Skip (recommended for now)
            # B. Break into multiple 2-hop trades (complex, high gas)
            # C. Use direct swaps with capital (if available)

            logger.info(f"\n   ⚠️  3+ hop path detected")
            logger.info(f"   Current flash loan contract only supports 2-hop")

            if has_capital:
                # Could do direct swaps, but gas cost is HIGH
                gas_cost_multi = self._calculate_gas_cost_usd(
                    self.GAS_COSTS['direct_2hop'] * (num_hops / 2),  # Rough estimate
                    pol_price_usd
                )
                net_profit = gross_profit - gas_cost_multi

                logger.info(f"   💰 Direct multi-hop: ${net_profit:.2f} profit")

                if net_profit >= self.min_profit_usd * 2:  # Higher threshold for complex paths
                    logger.info(f"   ⚠️  Skipping: 3+ hop execution not implemented yet")
                    return ExecutionDecision(
                        path=ExecutionPath.SKIP,
                        reason=f"3+ hop not supported (would be ${net_profit:.2f} profit)",
                        estimated_gas_usd=gas_cost_multi,
                        estimated_profit_after_gas=net_profit,
                        method_details={'hops': num_hops}
                    )

            return ExecutionDecision(
                path=ExecutionPath.SKIP,
                reason=f"3+ hop not supported by flash loan contract",
                estimated_gas_usd=0,
                estimated_profit_after_gas=0,
                method_details={'hops': num_hops}
            )

        # ============================================================
        # DEFAULT: SKIP
        # ============================================================
        return ExecutionDecision(
            path=ExecutionPath.SKIP,
            reason=f"Not profitable after gas (net: ${gross_profit:.2f})",
            estimated_gas_usd=0,
            estimated_profit_after_gas=0,
            method_details={}
        )

    def get_execution_stats(self) -> Dict:
        """Get statistics about execution routing decisions"""
        # TODO: Track decisions and return stats
        return {
            'flash_loan_2hop': 0,
            'direct_2hop': 0,
            'skipped': 0
        }


def format_execution_decision(decision: ExecutionDecision) -> str:
    """Format execution decision for logging"""
    lines = [
        f"\n{Fore.CYAN}{'='*80}",
        f"📋 EXECUTION DECISION",
        f"{'='*80}{Style.RESET_ALL}",
        f"   Path: {decision.path.value.upper()}",
        f"   Reason: {decision.reason}",
        f"   Gas Cost: ${decision.estimated_gas_usd:.2f}",
        f"   Net Profit: ${decision.estimated_profit_after_gas:.2f}",
        f"   Method: {decision.method_details}",
        f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}"
    ]
    return '\n'.join(lines)


if __name__ == "__main__":
    # Example usage
    from rpc_mgr import RPCManager

    rpc_mgr = RPCManager()
    gas_mgr = GasOptimizationManager(rpc_manager=rpc_mgr)
    router = ExecutionRouter(gas_mgr, min_profit_usd=1.0)

    # Test opportunity
    test_opportunity = {
        'path': ['USDC', 'WETH', 'USDC'],
        'hops': [
            {'dex': 'QuickSwap_V2', 'from': 'USDC', 'to': 'WETH'},
            {'dex': 'SushiSwap', 'from': 'WETH', 'to': 'USDC'}
        ],
        'gross_profit_usd': 5.0,
        'trade_size_usd': 10000
    }

    decision = router.decide_execution_path(test_opportunity, pol_price_usd=0.40, has_capital=False)
    print(format_execution_decision(decision))
