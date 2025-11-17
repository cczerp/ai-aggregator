"""
Auto-Execution Module for Flash Loan Arbitrage
OPTIMIZED FOR FLASH LOANS - Zero Capital Risk!

Key Differences from Regular Trading:
- Flash loans auto-revert on failure = NO CAPITAL RISK
- Only cost is gas (~$0.20-0.50 per attempt on Polygon)
- Can be MUCH more aggressive with execution
- No cooldowns needed (gas is cheap on Polygon)
- No daily loss limits (only losing gas, not capital)

Safety Focus:
- Minimum profit after gas + flash loan fees
- Pool liquidity checks (avoid excessive slippage)
- Gas cost must be < profit
"""

import os
import time
import logging
from typing import Dict, Optional, Tuple
from colorama import Fore, Style, init
from dataclasses import dataclass
from datetime import datetime

init(autoreset=True)

logger = logging.getLogger(__name__)


@dataclass
class FlashLoanLimits:
    """Safety limits for flash loan arbitrage (ZERO capital risk!)"""

    # Trade sizing (flash loan amounts)
    min_trade_size_usd: float = 1000.0         # Minimum flash loan size
    max_trade_size_usd: float = 100000.0       # Maximum flash loan size
    optimal_trade_size_usd: float = 15000.0    # Sweet spot for most pools

    # Profit requirements
    min_profit_after_gas: float = 0.75         # Min profit after gas ($0.75 - gas is cheap!)
    min_profit_after_fees: float = 1.00        # Min after gas + flash loan fees

    # Slippage and liquidity
    max_slippage_pct: float = 3.0              # Can be higher - no capital risk!
    min_pool_tvl: float = 5000.0               # Minimum pool liquidity

    # Rate limiting (can be aggressive - only cost is gas)
    max_trades_per_minute: int = 10            # Max 10 trades/min
    max_gas_spent_per_hour: float = 5.0        # Max $5 gas/hour
    cooldown_seconds: float = 0.1              # Minimal cooldown (100ms)

    # Kill switch (for repeated failures only)
    enabled: bool = True
    kill_on_consecutive_failures: int = 10     # Higher threshold - failures are cheap!

    # Flash loan provider preference
    prefer_balancer: bool = True               # Balancer = 0% fees!
    max_flash_loan_fee_pct: float = 0.09       # Max 0.09% (Aave)


class FlashLoanExecutor:
    """
    Flash Loan execution engine - ZERO CAPITAL RISK
    Optimized for aggressive execution since failures only cost gas
    """

    def __init__(
        self,
        price_fetcher,
        arb_finder,
        limits: Optional[FlashLoanLimits] = None,
        use_flash_loans: bool = True
    ):
        self.price_fetcher = price_fetcher
        self.arb_finder = arb_finder
        self.limits = limits or FlashLoanLimits()
        self.use_flash_loans = use_flash_loans

        # Execution tracking
        self.last_trade_time = 0
        self.trades_this_minute = []
        self.gas_spent_this_hour = []
        self.consecutive_failures = 0
        self.total_trades = 0
        self.successful_trades = 0
        self.total_gas_spent = 0.0
        self.total_profit = 0.0

        print(f"{Fore.GREEN}✅ Flash Loan Executor initialized (ZERO CAPITAL RISK!){Style.RESET_ALL}")
        print(f"   Flash loan sizes: ${self.limits.min_trade_size_usd:,.0f} - ${self.limits.max_trade_size_usd:,.0f}")
        print(f"   Optimal size: ${self.limits.optimal_trade_size_usd:,.0f}")
        print(f"   Min profit after fees: ${self.limits.min_profit_after_fees}")
        print(f"   Max slippage: {self.limits.max_slippage_pct}%")
        print(f"   Cooldown: {self.limits.cooldown_seconds}s")
        print(f"   Flash loan provider: {'Balancer (0% fees)' if self.limits.prefer_balancer else 'Aave (0.09% fees)'}")

    def check_execution_safety(self, opportunity: Dict) -> Tuple[bool, str]:
        """
        Minimal safety checks for flash loans (failures are cheap!)

        Returns:
            (is_safe, reason)
        """
        # Check kill switch
        if not self.limits.enabled:
            return False, "Kill switch activated"

        # Check consecutive failures
        if self.consecutive_failures >= self.limits.kill_on_consecutive_failures:
            self.limits.enabled = False
            return False, f"Kill switch: {self.consecutive_failures} consecutive failures"

        # Minimal cooldown (100ms by default)
        time_since_last = time.time() - self.last_trade_time
        if time_since_last < self.limits.cooldown_seconds:
            return False, f"Cooldown: {self.limits.cooldown_seconds - time_since_last:.3f}s"

        # Rate limiting (trades per minute)
        now = time.time()
        self.trades_this_minute = [t for t in self.trades_this_minute if now - t < 60]
        if len(self.trades_this_minute) >= self.limits.max_trades_per_minute:
            return False, f"Rate limit: {self.limits.max_trades_per_minute} trades/min"

        # Gas spending limit (hourly)
        self.gas_spent_this_hour = [g for g in self.gas_spent_this_hour if now - g[0] < 3600]
        hourly_gas = sum(g[1] for g in self.gas_spent_this_hour)
        if hourly_gas >= self.limits.max_gas_spent_per_hour:
            return False, f"Gas limit: ${hourly_gas:.2f} spent this hour (max ${self.limits.max_gas_spent_per_hour})"

        # Check profit after gas
        profit_after_gas = opportunity.get('net_profit_usd', 0)
        gas_cost = opportunity.get('gas_cost_usd', 0.3)  # ~$0.30 on Polygon

        # Calculate flash loan fee
        trade_size = opportunity.get('trade_size_usd', self.limits.optimal_trade_size_usd)
        flash_loan_fee = 0 if self.limits.prefer_balancer else (trade_size * 0.0009)  # 0.09%

        net_profit = profit_after_gas - gas_cost - flash_loan_fee

        if net_profit < self.limits.min_profit_after_fees:
            return False, f"Net profit ${net_profit:.2f} < min ${self.limits.min_profit_after_fees}"

        # Check slippage (can be higher since no capital risk)
        total_slippage = opportunity.get('total_slippage_pct', 0)
        if total_slippage > self.limits.max_slippage_pct:
            return False, f"Slippage {total_slippage:.2f}% > max {self.limits.max_slippage_pct}%"

        # Check pool TVL (liquidity)
        buy_tvl = opportunity.get('buy_tvl_usd', 0)
        sell_tvl = opportunity.get('sell_tvl_usd', 0)
        min_tvl = min(buy_tvl, sell_tvl)

        if min_tvl < self.limits.min_pool_tvl:
            return False, f"Pool TVL ${min_tvl:,.0f} < min ${self.limits.min_pool_tvl:,.0f}"

        return True, "All safety checks passed"

    def should_execute(self, opportunity: Dict) -> Tuple[bool, str, Optional[Dict]]:
        """
        Flash loan decision: execute immediately if profitable!
        No need for extensive checks - flash loans auto-revert on failure

        Returns:
            (should_execute, reason, updated_opportunity)
        """
        # Quick safety check
        is_safe, reason = self.check_execution_safety(opportunity)
        if not is_safe:
            return False, reason, None

        # For flash loans, we can skip fresh quote verification!
        # The smart contract will verify quotes on-chain
        # If prices moved, the transaction will revert (no loss!)

        final_profit = opportunity.get('net_profit_usd', 0)
        trade_size = opportunity.get('trade_size_usd', self.limits.optimal_trade_size_usd)

        logger.info(f"✅ Flash loan opportunity APPROVED: ${final_profit:.2f} profit, ${trade_size:,.0f} size")
        return True, "Approved for flash loan execution", opportunity

    def execute_opportunity(self, opportunity: Dict, bot_instance) -> Dict:
        """
        Execute flash loan arbitrage

        Returns:
            Execution result dict
        """
        try:
            # Record trade attempt
            self.total_trades += 1
            self.trades_this_minute.append(time.time())

            trade_size = opportunity.get('trade_size_usd', self.limits.optimal_trade_size_usd)
            expected_profit = opportunity.get('net_profit_usd', 0)

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"⚡ FLASH LOAN ARBITRAGE EXECUTION")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"  Pair: {opportunity.get('pair')}")
            print(f"  Flash Loan: ${trade_size:,.0f}")
            print(f"  Buy: {opportunity.get('dex_buy')} @ {opportunity.get('buy_price', 0):.8f}")
            print(f"  Sell: {opportunity.get('dex_sell')} @ {opportunity.get('sell_price', 0):.8f}")
            print(f"  Expected Profit: ${expected_profit:.2f}")
            print(f"  Slippage: {opportunity.get('total_slippage_pct', 0):.2f}%")
            print(f"  Provider: {'Balancer (0% fee)' if self.limits.prefer_balancer else 'Aave (0.09% fee)'}")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

            # Build proposal payload
            proposal = {
                "summary": f"{opportunity.get('pair')} flash loan arbitrage",
                "profit_usd": expected_profit,
                "payload": {
                    "pair": opportunity.get('pair'),
                    "dex_buy": opportunity.get('dex_buy'),
                    "dex_sell": opportunity.get('dex_sell'),
                    "amount_usd": trade_size,
                    "use_balancer": self.limits.prefer_balancer,
                    # Add more fields as needed
                }
            }

            # Execute via bot
            tx_hash = bot_instance.execute_proposal(proposal)

            # Estimate gas cost
            gas_cost = 0.3  # ~$0.30 on Polygon (flash loan trades use more gas)

            # Update tracking
            self.last_trade_time = time.time()
            self.successful_trades += 1
            self.consecutive_failures = 0  # Reset on success!
            self.total_gas_spent += gas_cost
            self.total_profit += expected_profit
            self.gas_spent_this_hour.append((time.time(), gas_cost))

            result = {
                "success": True,
                "tx_hash": tx_hash,
                "profit_usd": expected_profit,
                "gas_cost_usd": gas_cost,
                "net_profit_usd": expected_profit - gas_cost,
                "timestamp": datetime.now().isoformat()
            }

            print(f"{Fore.GREEN}✅ Flash loan executed successfully!{Style.RESET_ALL}")
            print(f"   TX: {tx_hash}")
            print(f"   Gross Profit: ${expected_profit:.2f}")
            print(f"   Gas Cost: ${gas_cost:.2f}")
            print(f"   Net Profit: ${expected_profit - gas_cost:.2f}")
            print(f"   Success rate: {self.successful_trades}/{self.total_trades} ({self.successful_trades/max(self.total_trades,1)*100:.1f}%)\n")

            return result

        except Exception as e:
            logger.error(f"Flash loan execution failed: {e}")

            # Update failure tracking
            self.consecutive_failures += 1
            gas_cost = 0.3  # Still spent gas on failed transaction
            self.total_gas_spent += gas_cost
            self.gas_spent_this_hour.append((time.time(), gas_cost))

            result = {
                "success": False,
                "error": str(e),
                "gas_cost_usd": gas_cost,
                "timestamp": datetime.now().isoformat()
            }

            print(f"{Fore.RED}❌ Flash loan failed: {e}{Style.RESET_ALL}")
            print(f"   Gas cost: ${gas_cost:.2f} (transaction reverted)")
            print(f"   Consecutive failures: {self.consecutive_failures}\n")

            return result

    def get_stats(self) -> Dict:
        """Get execution statistics"""
        success_rate = (self.successful_trades / max(self.total_trades, 1)) * 100
        net_profit = self.total_profit - self.total_gas_spent

        return {
            "total_trades": self.total_trades,
            "successful_trades": self.successful_trades,
            "failed_trades": self.total_trades - self.successful_trades,
            "success_rate": success_rate,
            "consecutive_failures": self.consecutive_failures,
            "total_profit": self.total_profit,
            "total_gas_spent": self.total_gas_spent,
            "net_profit": net_profit,
            "trades_this_minute": len(self.trades_this_minute),
            "gas_this_hour": sum(g[1] for g in self.gas_spent_this_hour),
            "kill_switch_active": not self.limits.enabled,
            "time_since_last_trade": time.time() - self.last_trade_time if self.last_trade_time > 0 else None
        }

    def reset_failure_counter(self):
        """Reset consecutive failure counter"""
        self.consecutive_failures = 0
        logger.info("Failure counter reset")

    def enable_kill_switch(self):
        """Manually activate kill switch"""
        self.limits.enabled = False
        logger.warning("Kill switch manually activated")

    def disable_kill_switch(self):
        """Manually deactivate kill switch"""
        self.limits.enabled = True
        self.consecutive_failures = 0
        logger.info("Kill switch deactivated")


# Legacy alias for backward compatibility
AutoExecutor = FlashLoanExecutor
ExecutionLimits = FlashLoanLimits
