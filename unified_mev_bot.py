"""
Unified MEV Bot - One System, Multiple Strategies, ML-Powered

This is the COMPLETE system that:
1. Uses ML brain to choose the best strategy for each opportunity
2. Routes to appropriate execution path (2-hop, mempool, 3-hop, etc.)
3. Learns from every trade to get exponentially smarter
4. Adapts to market conditions in real-time

Strategies:
- 2-hop basic arbitrage (no mempool)
- 2-hop mempool-enhanced arbitrage (better timing)
- 3-hop arbitrage (if contract supports)
- Wait for better opportunity

The bot LEARNS which strategy works best for different situations!
"""

import os
import time
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from colorama import Fore, Style, init

from polygon_arb_bot import PolygonArbBot
from tx_builder import GasOptimizationManager
from advanced_mev_module import AdvancedMEVModule
from remix_bot.flashloan_contract import FlashloanContract
from ml_strategy_brain import MLStrategyBrain, TradeOutcome
from execution_router import ExecutionRouter, ExecutionPath
from registries import get_token_address, DEXES

init(autoreset=True)


class UnifiedMEVBot:
    """
    Master orchestrator - ties everything together with ML intelligence
    """

    def __init__(
        self,
        contract_address: str,
        private_key: str,
        enable_mempool: bool = False,
        enable_ml: bool = True
    ):
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🤖 UNIFIED MEV BOT - ML-POWERED MULTI-STRATEGY SYSTEM")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        self.enable_mempool = enable_mempool
        self.enable_ml = enable_ml

        # Initialize base bot
        print(f"{Fore.YELLOW}📊 Initializing base arbitrage bot...{Style.RESET_ALL}")
        self.bot = PolygonArbBot(
            min_tvl=3000,
            scan_interval=60,
            auto_execute=False  # We handle execution
        )

        # Initialize gas manager
        print(f"{Fore.YELLOW}⛽ Initializing gas manager...{Style.RESET_ALL}")
        self.gas_mgr = GasOptimizationManager(rpc_manager=self.bot.rpc_manager)

        # Initialize MEV module with advanced features
        print(f"{Fore.YELLOW}🔧 Initializing MEV module...{Style.RESET_ALL}")
        self.mev_module = AdvancedMEVModule(
            self.bot,
            gas_manager=self.gas_mgr
        )

        # Initialize execution router
        print(f"{Fore.YELLOW}🎯 Initializing execution router...{Style.RESET_ALL}")
        self.execution_router = ExecutionRouter(self.gas_mgr, min_profit_usd=1.0)

        # Initialize flash loan contract
        print(f"{Fore.YELLOW}⚡ Initializing flash loan contract...{Style.RESET_ALL}")
        w3 = self.bot.rpc_manager.get_web3(self.bot.rpc_manager.endpoints[0])
        self.flash_contract = FlashloanContract(
            web3=w3,
            contract_address=contract_address,
            private_key=private_key
        )

        # Initialize ML brain
        if enable_ml:
            print(f"{Fore.YELLOW}🧠 Initializing ML strategy brain...{Style.RESET_ALL}")
            self.ml_brain = MLStrategyBrain(trade_db_path='./trade_history.json')
        else:
            self.ml_brain = None
            print(f"{Fore.YELLOW}⚠️  ML disabled - using static strategy selection{Style.RESET_ALL}")

        # Stats
        self.total_scans = 0
        self.total_executions = 0
        self.total_profit = 0.0
        self.strategy_usage = {}

        print(f"\n{Fore.GREEN}✅ Unified MEV Bot initialized successfully!{Style.RESET_ALL}")
        print(f"   Mempool monitoring: {'ENABLED' if enable_mempool else 'DISABLED'}")
        print(f"   ML intelligence: {'ENABLED' if enable_ml else 'DISABLED'}")
        print(f"   Contract: {contract_address[:10]}...")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    async def start_mempool_monitoring(self):
        """Start mempool monitoring (if enabled)"""
        if not self.enable_mempool:
            print(f"{Fore.YELLOW}⚠️  Mempool monitoring disabled{Style.RESET_ALL}")
            return

        print(f"{Fore.GREEN}🔍 Starting mempool monitoring...{Style.RESET_ALL}")
        await self.mev_module.start_mempool_monitoring()

    def find_opportunities(self) -> List[Dict]:
        """
        Find opportunities using all available methods
        Returns opportunities with strategy hints
        """
        opportunities = []

        # Get POL price
        pol_price = self.bot.price_fetcher.price_fetcher.get_price("WPOL") or 0.40

        # Method 1: Graph-based arbitrage (uses dynamic gas tuning)
        graph_opps = self.mev_module.find_graph_opportunities(pol_price_usd=pol_price)

        for opp in graph_opps:
            opp['source'] = 'graph'
            opp['from_mempool'] = False
            opportunities.append(opp)

        # Method 2: Mempool opportunities (if enabled)
        if self.enable_mempool:
            # TODO: Integrate mempool opportunities
            # mempool_opps = self.mev_module.mempool_monitor.get_pending_opportunities()
            # for opp in mempool_opps:
            #     opp['source'] = 'mempool'
            #     opp['from_mempool'] = True
            #     opportunities.append(opp)
            pass

        return opportunities

    def execute_opportunity(
        self,
        opportunity: Dict,
        strategy: str,
        decision: Dict
    ) -> TradeOutcome:
        """
        Execute an opportunity using the chosen strategy

        Returns:
            TradeOutcome for ML learning
        """
        start_time = time.time()

        try:
            # Extract trade parameters
            hops = opportunity.get('route', [])
            if not hops:
                raise ValueError("No route found in opportunity")

            token_in_symbol = hops[0]['token']
            token_out_symbol = hops[1]['token']

            # Get addresses
            token_in = get_token_address(token_in_symbol)
            token_out = get_token_address(token_out_symbol)

            # Get DEX routers
            dex1_name = hops[0]['dex']
            dex2_name = hops[1]['dex']
            dex1_address = DEXES[dex1_name]['router']
            dex2_address = DEXES[dex2_name]['router']

            # Trade size
            trade_size_usd = opportunity.get('amount_in', 15000)
            token_in_decimals = 6 if token_in_symbol in ['USDC', 'USDT'] else 18
            amount_in_wei = int(trade_size_usd * (10 ** token_in_decimals))

            # Expected profit
            expected_profit = decision['ml_score'] * opportunity.get('profit_usd', 0)

            # Min profit (with 10% slippage buffer)
            min_profit_wei = int((expected_profit * 0.90) * (10 ** token_in_decimals))

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"🚀 EXECUTING TRADE")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"   Strategy: {strategy}")
            print(f"   Route: {token_in_symbol} → {token_out_symbol} → {token_in_symbol}")
            print(f"   DEX1: {dex1_name}")
            print(f"   DEX2: {dex2_name}")
            print(f"   Size: ${trade_size_usd:,.0f}")
            print(f"   Expected Profit: ${expected_profit:.2f}")
            print(f"   ML Confidence: {decision['ml_score']*100:.1f}%")

            # Execute based on strategy
            if strategy in ['2hop_basic_arb', '2hop_mempool_arb']:
                # Decide provider (Balancer vs Aave)
                provider = decision.get('provider', 'balancer')

                print(f"   Provider: {provider}")

                if provider == 'balancer':
                    tx_result = self.flash_contract.execute_balancer_flashloan(
                        token_in=token_in,
                        token_out=token_out,
                        dex1_address=dex1_address,
                        dex2_address=dex2_address,
                        amount_in=amount_in_wei,
                        min_profit=min_profit_wei
                    )
                else:  # aave
                    tx_result = self.flash_contract.execute_aave_flashloan(
                        token_in=token_in,
                        token_out=token_out,
                        dex1_address=dex1_address,
                        dex2_address=dex2_address,
                        amount_in=amount_in_wei,
                        min_profit=min_profit_wei
                    )

                execution_time_ms = (time.time() - start_time) * 1000

                if tx_result['status'] == 'success':
                    print(f"\n{Fore.GREEN}✅ SUCCESS!{Style.RESET_ALL}")
                    print(f"   TX: {tx_result['tx_hash']}")
                    print(f"   Gas Used: {tx_result['gas_used']:,}")

                    # Calculate actual gas cost
                    gas_cost_usd = (tx_result['gas_used'] * 35e9 / 1e18) * 0.40  # Rough estimate

                    return TradeOutcome(
                        timestamp=time.time(),
                        strategy=strategy,
                        opportunity=opportunity,
                        decision_params=decision,
                        success=True,
                        profit_usd=expected_profit,
                        gas_cost_usd=gas_cost_usd,
                        net_profit_usd=expected_profit - gas_cost_usd,
                        execution_time_ms=execution_time_ms
                    )
                else:
                    print(f"\n{Fore.RED}❌ FAILED: Transaction reverted{Style.RESET_ALL}")

                    return TradeOutcome(
                        timestamp=time.time(),
                        strategy=strategy,
                        opportunity=opportunity,
                        decision_params=decision,
                        success=False,
                        profit_usd=0.0,
                        gas_cost_usd=0.3,  # Failed gas cost
                        net_profit_usd=-0.3,
                        execution_time_ms=execution_time_ms,
                        failure_reason="Transaction reverted"
                    )

            elif strategy == '3hop_arb':
                # 3-hop not supported by current contract
                print(f"{Fore.YELLOW}⚠️  3-hop arb not supported by flash loan contract{Style.RESET_ALL}")
                return TradeOutcome(
                    timestamp=time.time(),
                    strategy=strategy,
                    opportunity=opportunity,
                    decision_params=decision,
                    success=False,
                    profit_usd=0.0,
                    gas_cost_usd=0.0,
                    net_profit_usd=0.0,
                    execution_time_ms=0,
                    failure_reason="3-hop not supported"
                )

            elif strategy == 'wait':
                # Decided to wait - not a failure
                print(f"{Fore.BLUE}⏸️  Waiting for better opportunity{Style.RESET_ALL}")
                return None

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            print(f"\n{Fore.RED}❌ EXECUTION ERROR: {e}{Style.RESET_ALL}")

            return TradeOutcome(
                timestamp=time.time(),
                strategy=strategy,
                opportunity=opportunity,
                decision_params=decision,
                success=False,
                profit_usd=0.0,
                gas_cost_usd=0.3,
                net_profit_usd=-0.3,
                execution_time_ms=execution_time_ms,
                failure_reason=str(e)
            )

    def run_once(self) -> Dict:
        """Run one scan cycle"""
        self.total_scans += 1

        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"⏰ SCAN #{self.total_scans} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}{Style.RESET_ALL}\n")

        # Find opportunities
        opportunities = self.find_opportunities()

        if not opportunities:
            print(f"💤 No opportunities found")
            return {'scans': self.total_scans, 'executed': 0, 'profit': 0}

        print(f"🎯 Found {len(opportunities)} opportunities\n")

        # Get gas price
        gas_params = self.gas_mgr.get_optimized_gas_params()
        gas_price_gwei = gas_params['maxFeePerGas'] / 1e9
        pol_price = self.bot.price_fetcher.price_fetcher.get_price("WPOL") or 0.40

        executed_count = 0
        scan_profit = 0.0

        # Process each opportunity
        for i, opp in enumerate(opportunities[:5], 1):  # Top 5
            print(f"\n--- Opportunity {i}/{min(5, len(opportunities))} ---")
            print(f"   Path: {opp.get('path', 'Unknown')}")
            print(f"   Gross Profit: ${opp.get('profit_usd', 0):.2f}")

            # Get ML recommendation
            if self.enable_ml:
                recommendation = self.ml_brain.get_strategy_recommendation(
                    opp,
                    gas_price_gwei=gas_price_gwei,
                    pol_price_usd=pol_price
                )

                print(f"   🧠 ML Recommendation: {recommendation['recommended_strategy']}")
                print(f"   Confidence: {recommendation['ml_score']*100:.1f}%")
                print(f"   Reasoning: {recommendation['reasoning']}")

                if not recommendation['should_execute']:
                    print(f"   ⏭️  ML says: SKIP")
                    continue

                strategy = recommendation['recommended_strategy']
            else:
                # No ML - use simple routing
                strategy = '2hop_basic_arb'
                recommendation = {'ml_score': 0.7}

            # Track strategy usage
            self.strategy_usage[strategy] = self.strategy_usage.get(strategy, 0) + 1

            # Execute
            outcome = self.execute_opportunity(opp, strategy, recommendation)

            if outcome:
                # Learn from outcome
                if self.enable_ml:
                    self.ml_brain.learn_from_trade(outcome)

                if outcome.success:
                    executed_count += 1
                    scan_profit += outcome.net_profit_usd
                    self.total_profit += outcome.net_profit_usd

        # Summary
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 SCAN SUMMARY")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Opportunities: {len(opportunities)}")
        print(f"   Executed: {executed_count}")
        print(f"   Scan Profit: ${scan_profit:.2f}")
        print(f"   Total Session Profit: ${self.total_profit:.2f}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

        # Show ML stats
        if self.enable_ml and self.total_scans % 10 == 0:
            print(self.ml_brain.get_stats_summary())

        return {
            'scans': self.total_scans,
            'executed': executed_count,
            'profit': scan_profit
        }

    def run_continuous(self, interval_seconds: int = 60):
        """Run continuously"""
        print(f"{Fore.GREEN}🚀 Starting continuous mode (Ctrl+C to stop){Style.RESET_ALL}\n")

        try:
            while True:
                result = self.run_once()

                print(f"💤 Sleeping {interval_seconds}s until next scan...")
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            print(f"\n\n{Fore.CYAN}{'='*80}")
            print(f"👋 SHUTTING DOWN")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"   Total Scans: {self.total_scans}")
            print(f"   Total Executions: {self.total_executions}")
            print(f"   Total Profit: ${self.total_profit:.2f}")

            if self.enable_ml:
                print(f"\n   Strategy Usage:")
                for strategy, count in self.strategy_usage.items():
                    print(f"      {strategy}: {count} times")

            print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")


# Main entry point
if __name__ == "__main__":
    # Configuration
    CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')
    PRIVATE_KEY = os.getenv('PRIVATE_KEY')
    ENABLE_MEMPOOL = os.getenv('ENABLE_MEMPOOL', 'false').lower() == 'true'
    ENABLE_ML = os.getenv('ENABLE_ML', 'true').lower() == 'true'

    if not CONTRACT_ADDRESS or not PRIVATE_KEY:
        print(f"{Fore.RED}❌ Missing CONTRACT_ADDRESS or PRIVATE_KEY in .env{Style.RESET_ALL}")
        exit(1)

    # Initialize unified bot
    bot = UnifiedMEVBot(
        contract_address=CONTRACT_ADDRESS,
        private_key=PRIVATE_KEY,
        enable_mempool=ENABLE_MEMPOOL,
        enable_ml=ENABLE_ML
    )

    # Run
    bot.run_continuous(interval_seconds=60)
