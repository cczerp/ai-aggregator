"""
Dynamic Gas-Based Graph Tuning
Adjusts arbitrage search parameters based on real-time gas costs:
- Max hops (2-hop vs 3-hop vs 4-hop)
- Min profit thresholds
- Test trade amounts
- Pool TVL requirements
- Max paths to search

Strategy: When gas is expensive, only search for high-profit 2-hop opportunities.
When gas is cheap, search more aggressively for 3-4 hop opportunities.
"""

from typing import Dict, List
from dataclasses import dataclass
from colorama import Fore, Style, init
import logging

from tx_builder import GasOptimizationManager

init(autoreset=True)
logger = logging.getLogger(__name__)


@dataclass
class GraphSearchParams:
    """Dynamic parameters for graph-based arbitrage search"""
    max_hops: int                      # Maximum path length
    min_profit_after_gas: float        # Minimum profit threshold (USD)
    test_amounts_usd: List[float]      # Trade sizes to test
    min_pool_tvl_usd: float            # Minimum pool liquidity
    max_paths: int                     # Maximum paths to search per token
    gas_cost_per_hop_usd: float        # Estimated gas cost per hop
    reasoning: str                      # Why these parameters were chosen


class DynamicGasTuner:
    """
    Dynamically tunes graph search parameters based on gas costs

    Gas Cost Tiers:
    - CHEAP (<$0.20/hop): Aggressive 4-hop search
    - NORMAL ($0.20-$0.40/hop): Standard 3-hop search
    - EXPENSIVE ($0.40-$0.70/hop): Conservative 2-hop search
    - VERY_EXPENSIVE (>$0.70/hop): Only best 2-hop opportunities
    """

    # Gas cost per hop (gas units)
    GAS_PER_HOP = {
        'direct_swap': 120000,        # Direct swap (no flash loan)
        'flash_loan_hop': 150000,     # Flash loan + swap
    }

    def __init__(self, gas_manager: GasOptimizationManager, use_flash_loans: bool = True):
        """
        Args:
            gas_manager: GasOptimizationManager for real-time gas prices
            use_flash_loans: Whether flash loans are being used (higher gas cost)
        """
        self.gas_mgr = gas_manager
        self.use_flash_loans = use_flash_loans

        # Base gas per hop
        self.base_gas_per_hop = (
            self.GAS_PER_HOP['flash_loan_hop'] if use_flash_loans
            else self.GAS_PER_HOP['direct_swap']
        )

        logger.info(f"{Fore.GREEN}✅ Dynamic Gas Tuner initialized{Style.RESET_ALL}")
        logger.info(f"   Flash loans: {use_flash_loans}")
        logger.info(f"   Base gas/hop: {self.base_gas_per_hop:,} units")

    def _get_gas_cost_per_hop(self, pol_price_usd: float = 0.40) -> float:
        """Calculate current gas cost per hop in USD"""
        try:
            # Get current gas params
            gas_params = self.gas_mgr.get_optimized_gas_params()
            max_fee_per_gas = gas_params['maxFeePerGas']

            # Calculate cost in POL
            gas_cost_wei = self.base_gas_per_hop * max_fee_per_gas
            gas_cost_pol = gas_cost_wei / 1e18

            # Convert to USD
            return gas_cost_pol * pol_price_usd

        except Exception as e:
            logger.warning(f"Gas cost estimation failed: {e}, using fallback")
            # Fallback: assume 40 gwei
            gas_cost_pol = (self.base_gas_per_hop * 40e9) / 1e18
            return gas_cost_pol * pol_price_usd

    def get_optimal_params(self, pol_price_usd: float = 0.40) -> GraphSearchParams:
        """
        Get optimal search parameters based on current gas costs

        Args:
            pol_price_usd: Current POL/MATIC price in USD

        Returns:
            GraphSearchParams with tuned parameters
        """
        gas_cost_per_hop = self._get_gas_cost_per_hop(pol_price_usd)

        logger.info(f"\n{Fore.CYAN}⚙️  DYNAMIC GAS TUNING{Style.RESET_ALL}")
        logger.info(f"   Gas cost per hop: ${gas_cost_per_hop:.3f}")

        # ============================================================
        # TIER 1: CHEAP GAS (<$0.20/hop) - AGGRESSIVE
        # ============================================================
        if gas_cost_per_hop < 0.20:
            return GraphSearchParams(
                max_hops=4,
                min_profit_after_gas=1.0,
                test_amounts_usd=[
                    2000,     # Small
                    10000,    # Medium
                    50000     # Large
                ],
                min_pool_tvl_usd=5000,
                max_paths=100,
                gas_cost_per_hop_usd=gas_cost_per_hop,
                reasoning=f"CHEAP GAS (${gas_cost_per_hop:.3f}/hop): Aggressive 4-hop search, low profit threshold"
            )

        # ============================================================
        # TIER 2: NORMAL GAS ($0.20-$0.40/hop) - STANDARD
        # ============================================================
        elif gas_cost_per_hop < 0.40:
            return GraphSearchParams(
                max_hops=3,
                min_profit_after_gas=2.0,
                test_amounts_usd=[
                    5000,     # Small
                    15000,    # Medium
                    50000     # Large
                ],
                min_pool_tvl_usd=10000,
                max_paths=75,
                gas_cost_per_hop_usd=gas_cost_per_hop,
                reasoning=f"NORMAL GAS (${gas_cost_per_hop:.3f}/hop): Standard 3-hop search"
            )

        # ============================================================
        # TIER 3: EXPENSIVE GAS ($0.40-$0.70/hop) - CONSERVATIVE
        # ============================================================
        elif gas_cost_per_hop < 0.70:
            return GraphSearchParams(
                max_hops=2,
                min_profit_after_gas=3.0,
                test_amounts_usd=[
                    10000,    # Medium
                    25000,    # Large
                    100000    # XL
                ],
                min_pool_tvl_usd=20000,
                max_paths=50,
                gas_cost_per_hop_usd=gas_cost_per_hop,
                reasoning=f"EXPENSIVE GAS (${gas_cost_per_hop:.3f}/hop): Conservative 2-hop only, higher profit threshold"
            )

        # ============================================================
        # TIER 4: VERY EXPENSIVE GAS (>$0.70/hop) - MINIMAL
        # ============================================================
        else:
            return GraphSearchParams(
                max_hops=2,
                min_profit_after_gas=5.0,
                test_amounts_usd=[
                    25000,    # Large only
                    100000    # XL
                ],
                min_pool_tvl_usd=50000,
                max_paths=25,
                gas_cost_per_hop_usd=gas_cost_per_hop,
                reasoning=f"VERY EXPENSIVE GAS (${gas_cost_per_hop:.3f}/hop): Only best 2-hop opportunities"
            )

    def print_params(self, params: GraphSearchParams):
        """Print tuned parameters"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"⚙️  TUNED GRAPH SEARCH PARAMETERS")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Reasoning: {params.reasoning}")
        print(f"   Gas cost/hop: ${params.gas_cost_per_hop_usd:.3f}")
        print(f"")
        print(f"   Max hops: {params.max_hops}")
        print(f"   Min profit after gas: ${params.min_profit_after_gas:.2f}")
        print(f"   Test amounts: {[f'${a:,.0f}' for a in params.test_amounts_usd]}")
        print(f"   Min pool TVL: ${params.min_pool_tvl_usd:,.0f}")
        print(f"   Max paths/token: {params.max_paths}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    def should_search_arbitrage(
        self,
        pol_price_usd: float = 0.40,
        max_gas_cost_usd: float = 2.0
    ) -> bool:
        """
        Determine if it's worth searching for arbitrage given current gas costs

        Args:
            pol_price_usd: Current POL price
            max_gas_cost_usd: Maximum acceptable gas cost for a 2-hop arb

        Returns:
            True if gas is cheap enough to make arbitrage worthwhile
        """
        gas_cost_per_hop = self._get_gas_cost_per_hop(pol_price_usd)
        two_hop_gas_cost = gas_cost_per_hop * 2

        if two_hop_gas_cost > max_gas_cost_usd:
            logger.warning(
                f"{Fore.YELLOW}⚠️  Gas too expensive for arbitrage: "
                f"${two_hop_gas_cost:.2f} > ${max_gas_cost_usd:.2f} threshold{Style.RESET_ALL}"
            )
            return False

        return True


# Example usage
if __name__ == "__main__":
    from rpc_mgr import RPCManager

    rpc_mgr = RPCManager()
    gas_mgr = GasOptimizationManager(rpc_manager=rpc_mgr)
    tuner = DynamicGasTuner(gas_mgr, use_flash_loans=True)

    # Get current optimal parameters
    params = tuner.get_optimal_params(pol_price_usd=0.40)
    tuner.print_params(params)

    # Check if should search
    should_search = tuner.should_search_arbitrage(pol_price_usd=0.40, max_gas_cost_usd=2.0)
    print(f"Should search for arbitrage: {should_search}")
