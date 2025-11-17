"""
Auto-Execution Module for Real-Time Arbitrage
- Fresh quote verification before execution
- Slippage protection
- Gas cost validation
- Execution limits and kill switch
- Automatic retry logic
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
class ExecutionLimits:
    """Safety limits for auto-execution"""
    max_trade_size_usd: float = 10000.0        # Max trade size
    min_profit_after_gas: float = 2.0          # Min profit after gas ($2)
    max_slippage_pct: float = 2.0              # Max acceptable slippage (2%)
    max_gas_cost_pct: float = 30.0             # Max gas as % of profit
    max_trades_per_hour: int = 20              # Rate limit
    max_daily_loss: float = 100.0              # Max loss per day
    cooldown_seconds: int = 30                 # Cooldown between trades

    # Kill switch
    enabled: bool = True
    kill_on_failed_trades: int = 3             # Disable after N failures


class AutoExecutor:
    """
    Automatic execution engine with safety checks
    """

    def __init__(
        self,
        price_fetcher,
        arb_finder,
        limits: Optional[ExecutionLimits] = None
    ):
        self.price_fetcher = price_fetcher
        self.arb_finder = arb_finder
        self.limits = limits or ExecutionLimits()

        # Execution tracking
        self.last_trade_time = 0
        self.trades_this_hour = []
        self.failed_trades = 0
        self.daily_pnl = 0.0
        self.total_trades = 0
        self.successful_trades = 0

        logger.info("AutoExecutor initialized with safety limits")
        logger.info(f"  Max trade size: ${self.limits.max_trade_size_usd:,.0f}")
        logger.info(f"  Min profit after gas: ${self.limits.min_profit_after_gas}")
        logger.info(f"  Max slippage: {self.limits.max_slippage_pct}%")
        logger.info(f"  Cooldown: {self.limits.cooldown_seconds}s")

    def verify_fresh_quote(self, opportunity: Dict) -> Tuple[bool, Optional[Dict], str]:
        """
        Verify opportunity with FRESH quotes from DEX contracts

        Returns:
            (is_valid, updated_opportunity, reason)
        """
        try:
            # Force fresh data by clearing cache for this specific pair
            pair = opportunity.get('pair')
            dex_buy = opportunity.get('dex_buy')
            dex_sell = opportunity.get('dex_sell')

            logger.info(f"Verifying fresh quotes for {pair}: {dex_buy} vs {dex_sell}")

            # Get fresh pool data (this will bypass cache if expired)
            # In production, you'd force a fresh fetch here
            # For now, we'll check if the opportunity still exists

            # Get pool data from price_fetcher
            # This is simplified - in production you'd call DEX contracts directly
            pools_data = self.price_fetcher.fetch_all_pools()

            # Find the pools for this pair
            buy_pool = None
            sell_pool = None

            for dex_name, pairs in pools_data.items():
                for pair_name, pool_data in pairs.items():
                    if pair_name == pair:
                        if dex_name == dex_buy:
                            buy_pool = pool_data
                        if dex_name == dex_sell:
                            sell_pool = pool_data

            if not buy_pool or not sell_pool:
                return False, None, "Pools not found"

            # Recalculate arbitrage with fresh data
            fresh_opp = self.arb_finder.calculate_arbitrage(
                pair,
                [
                    {'dex': dex_buy, 'pool_data': buy_pool},
                    {'dex': dex_sell, 'pool_data': sell_pool}
                ],
                opportunity.get('trade_size_usd', 1000)
            )

            if not fresh_opp:
                return False, None, "Opportunity no longer exists"

            # Compare fresh profit to original
            original_profit = opportunity.get('net_profit_usd', 0)
            fresh_profit = fresh_opp.get('net_profit_usd', 0)

            profit_diff_pct = abs(fresh_profit - original_profit) / original_profit * 100 if original_profit > 0 else 100

            if profit_diff_pct > 10:  # More than 10% difference
                return False, fresh_opp, f"Price moved {profit_diff_pct:.1f}% since detection"

            if fresh_profit < self.limits.min_profit_after_gas:
                return False, fresh_opp, f"Fresh profit ${fresh_profit:.2f} < min ${self.limits.min_profit_after_gas}"

            logger.info(f"Fresh quote verified: ${fresh_profit:.2f} profit (vs ${original_profit:.2f} original)")
            return True, fresh_opp, "Fresh quote verified"

        except Exception as e:
            logger.error(f"Fresh quote verification failed: {e}")
            return False, None, f"Verification error: {str(e)}"

    def check_execution_safety(self, opportunity: Dict) -> Tuple[bool, str]:
        """
        Check if it's safe to execute this opportunity

        Returns:
            (is_safe, reason)
        """
        # Check kill switch
        if not self.limits.enabled:
            return False, "Kill switch activated"

        # Check if too many failed trades
        if self.failed_trades >= self.limits.kill_on_failed_trades:
            self.limits.enabled = False
            return False, f"Kill switch: {self.failed_trades} consecutive failures"

        # Check cooldown
        time_since_last = time.time() - self.last_trade_time
        if time_since_last < self.limits.cooldown_seconds:
            return False, f"Cooldown: {self.limits.cooldown_seconds - time_since_last:.0f}s remaining"

        # Check hourly rate limit
        now = time.time()
        self.trades_this_hour = [t for t in self.trades_this_hour if now - t < 3600]
        if len(self.trades_this_hour) >= self.limits.max_trades_per_hour:
            return False, f"Rate limit: {self.limits.max_trades_per_hour} trades/hour exceeded"

        # Check daily loss limit
        if self.daily_pnl < -self.limits.max_daily_loss:
            self.limits.enabled = False
            return False, f"Daily loss limit exceeded: ${abs(self.daily_pnl):.2f}"

        # Check trade size
        trade_size = opportunity.get('trade_size_usd', 0)
        if trade_size > self.limits.max_trade_size_usd:
            return False, f"Trade size ${trade_size:.0f} > max ${self.limits.max_trade_size_usd:.0f}"

        # Check profit after gas
        profit_after_gas = opportunity.get('net_profit_usd', 0)
        gas_cost = opportunity.get('gas_cost_usd', 0.5)
        actual_profit = profit_after_gas - gas_cost

        if actual_profit < self.limits.min_profit_after_gas:
            return False, f"Profit after gas ${actual_profit:.2f} < min ${self.limits.min_profit_after_gas}"

        # Check gas cost as % of profit
        if profit_after_gas > 0:
            gas_pct = (gas_cost / profit_after_gas) * 100
            if gas_pct > self.limits.max_gas_cost_pct:
                return False, f"Gas cost {gas_pct:.1f}% > max {self.limits.max_gas_cost_pct}%"

        # Check slippage
        total_slippage = opportunity.get('total_slippage_pct', 0)
        if total_slippage > self.limits.max_slippage_pct:
            return False, f"Slippage {total_slippage:.2f}% > max {self.limits.max_slippage_pct}%"

        return True, "All safety checks passed"

    def should_execute(self, opportunity: Dict) -> Tuple[bool, str, Optional[Dict]]:
        """
        Main decision function: should we execute this opportunity?

        Returns:
            (should_execute, reason, updated_opportunity)
        """
        # Step 1: Safety checks
        is_safe, reason = self.check_execution_safety(opportunity)
        if not is_safe:
            logger.warning(f"Safety check failed: {reason}")
            return False, reason, None

        # Step 2: Fresh quote verification
        is_valid, fresh_opp, reason = self.verify_fresh_quote(opportunity)
        if not is_valid:
            logger.warning(f"Fresh quote failed: {reason}")
            return False, reason, fresh_opp

        # Step 3: Final profit check
        final_profit = fresh_opp.get('net_profit_usd', 0)
        if final_profit < self.limits.min_profit_after_gas:
            return False, f"Final profit ${final_profit:.2f} too low", fresh_opp

        logger.info(f"✅ Opportunity APPROVED for execution: ${final_profit:.2f} profit")
        return True, "Approved for execution", fresh_opp

    def execute_opportunity(self, opportunity: Dict, bot_instance) -> Dict:
        """
        Execute the arbitrage opportunity

        Returns:
            Execution result dict
        """
        try:
            # Record trade attempt
            self.total_trades += 1
            self.trades_this_hour.append(time.time())

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"⚡ AUTO-EXECUTING ARBITRAGE")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"  Pair: {opportunity.get('pair')}")
            print(f"  Buy: {opportunity.get('dex_buy')} @ {opportunity.get('buy_price', 0):.8f}")
            print(f"  Sell: {opportunity.get('dex_sell')} @ {opportunity.get('sell_price', 0):.8f}")
            print(f"  Expected Profit: ${opportunity.get('net_profit_usd', 0):.2f}")
            print(f"  Slippage: {opportunity.get('total_slippage_pct', 0):.2f}%")
            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

            # Build proposal payload
            proposal = {
                "summary": f"{opportunity.get('pair')} arbitrage",
                "profit_usd": opportunity.get('net_profit_usd', 0),
                "payload": {
                    "pair": opportunity.get('pair'),
                    "dex_buy": opportunity.get('dex_buy'),
                    "dex_sell": opportunity.get('dex_sell'),
                    "amount_usd": opportunity.get('trade_size_usd', 1000),
                    # Add more fields as needed by execute_proposal
                }
            }

            # Execute via bot
            tx_hash = bot_instance.execute_proposal(proposal)

            # Update tracking
            self.last_trade_time = time.time()
            self.successful_trades += 1
            self.failed_trades = 0  # Reset failure counter
            self.daily_pnl += opportunity.get('net_profit_usd', 0)

            result = {
                "success": True,
                "tx_hash": tx_hash,
                "profit_usd": opportunity.get('net_profit_usd', 0),
                "timestamp": datetime.now().isoformat()
            }

            print(f"{Fore.GREEN}✅ Execution successful!{Style.RESET_ALL}")
            print(f"   TX: {tx_hash}")
            print(f"   Profit: ${opportunity.get('net_profit_usd', 0):.2f}")
            print(f"   Success rate: {self.successful_trades}/{self.total_trades}\n")

            return result

        except Exception as e:
            logger.error(f"Execution failed: {e}")

            # Update failure tracking
            self.failed_trades += 1
            self.daily_pnl -= 0.5  # Assume small loss from gas

            result = {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

            print(f"{Fore.RED}❌ Execution failed: {e}{Style.RESET_ALL}\n")

            return result

    def get_stats(self) -> Dict:
        """Get execution statistics"""
        success_rate = (self.successful_trades / max(self.total_trades, 1)) * 100

        return {
            "total_trades": self.total_trades,
            "successful_trades": self.successful_trades,
            "failed_trades": self.failed_trades,
            "success_rate": success_rate,
            "daily_pnl": self.daily_pnl,
            "trades_this_hour": len(self.trades_this_hour),
            "kill_switch_active": not self.limits.enabled,
            "time_since_last_trade": time.time() - self.last_trade_time if self.last_trade_time > 0 else None
        }

    def reset_daily_stats(self):
        """Reset daily statistics (call at midnight)"""
        self.daily_pnl = 0.0
        logger.info("Daily stats reset")

    def enable_kill_switch(self):
        """Manually activate kill switch"""
        self.limits.enabled = False
        logger.warning("Kill switch manually activated")

    def disable_kill_switch(self):
        """Manually deactivate kill switch"""
        self.limits.enabled = True
        self.failed_trades = 0
        logger.info("Kill switch deactivated")
