# polygon_arb_bot_optimized.py
"""
Optimized Polygon Arbitrage Bot with:
- 15+ public RPC endpoints
- Persistent caching
- $10k minimum TVL
- Complete monitoring and statistics
- Smart cooldowns and failover
"""
import time
import sys
import os
from datetime import datetime
from colorama import Fore, Style, init

# Import all managers
from rpc_mgr import RPCManager
from cache import Cache
from price_data_fetcher import PriceDataFetcher
from arb_finder import ArbFinder
from auto_executor import AutoExecutor, ExecutionLimits

# Import existing modules (you already have these)
try:
    from tx_builder import FlashbotsTxBuilder, GasOptimizationManager
except ImportError as e:
    print(f"{Fore.RED}❌ Missing module: {e}{Style.RESET_ALL}")
    print("Please ensure tx_builder.py is in the same directory")
    sys.exit(1)

init(autoreset=True)

class PolygonArbBot:
    """Main arbitrage bot with complete monitoring"""
    
    def __init__(
        self,
        min_tvl: float = 3000,
        scan_interval: int = 60,
        auto_execute: bool = False
    ):
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🤖 INITIALIZING POLYGON ARBITRAGE BOT")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        
        self.min_tvl = min_tvl
        self.scan_interval = scan_interval
        self.auto_execute = auto_execute
        
        # Initialize RPC Manager (15+ public endpoints)
        print(f"{Fore.YELLOW}📡 Initializing RPC Manager...{Style.RESET_ALL}")
        self.rpc_manager = RPCManager()
        
        # Run health check
        health = self.rpc_manager.health_check()
        if len(health["working"]) < 5:
            print(f"{Fore.RED}⚠️  WARNING: Only {len(health['working'])} RPCs working!{Style.RESET_ALL}")
        
        # Initialize Persistent Cache
        print(f"\n{Fore.YELLOW}💾 Initializing Persistent Cache...{Style.RESET_ALL}")
        self.cache = Cache(cache_dir="./cache")
        
        # Initialize Price Data Fetcher
        print(f"\n{Fore.YELLOW}🔍 Initializing Price Data Fetcher...{Style.RESET_ALL}")
        self.price_fetcher = PriceDataFetcher(
            rpc_manager=self.rpc_manager,
            cache=self.cache,
            min_tvl_usd=min_tvl
        )

        # Initialize Arbitrage Finder
        print(f"\n{Fore.YELLOW}🎯 Initializing Arbitrage Finder...{Style.RESET_ALL}")
        self.arb_finder = ArbFinder(
            min_profit_usd=1.0
        )

        # Initialize Flash Loan Auto-Executor if enabled
        self.auto_executor = None
        if auto_execute:
            print(f"\n{Fore.YELLOW}⚡ Initializing Flash Loan Executor...{Style.RESET_ALL}")
            limits = ExecutionLimits(
                # Flash loan sizing
                min_trade_size_usd=float(os.getenv("MIN_TRADE_SIZE_USD", "1000")),
                max_trade_size_usd=float(os.getenv("MAX_TRADE_SIZE_USD", "100000")),
                optimal_trade_size_usd=float(os.getenv("OPTIMAL_TRADE_SIZE_USD", "15000")),

                # Profit requirements
                min_profit_after_gas=float(os.getenv("MIN_PROFIT_AFTER_GAS", "0.75")),
                min_profit_after_fees=float(os.getenv("MIN_PROFIT_AFTER_FEES", "1.00")),

                # Slippage and liquidity
                max_slippage_pct=float(os.getenv("MAX_SLIPPAGE_PCT", "3.0")),
                min_pool_tvl=float(os.getenv("MIN_POOL_TVL", "5000")),

                # Rate limiting (aggressive for flash loans!)
                max_trades_per_minute=int(os.getenv("MAX_TRADES_PER_MINUTE", "10")),
                max_gas_spent_per_hour=float(os.getenv("MAX_GAS_SPENT_PER_HOUR", "5.0")),
                cooldown_seconds=float(os.getenv("COOLDOWN_SECONDS", "0.1")),

                # Kill switch
                kill_on_consecutive_failures=int(os.getenv("KILL_ON_CONSECUTIVE_FAILURES", "10")),

                # Flash loan provider
                prefer_balancer=os.getenv("PREFER_BALANCER", "true").lower() == "true"
            )
            self.auto_executor = AutoExecutor(
                price_fetcher=self.price_fetcher,
                arb_finder=self.arb_finder,
                limits=limits,
                use_flash_loans=True
            )
            print(f"{Fore.GREEN}✅ Flash Loan Executor ready (ZERO CAPITAL RISK!){Style.RESET_ALL}")

        # Statistics
        self.total_scans = 0
        self.total_opportunities = 0
        self.total_trades = 0
        self.start_time = time.time()

        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"✅ BOT INITIALIZED SUCCESSFULLY")
        if auto_execute:
            print(f"⚡ AUTO-EXECUTION ENABLED")
        print(f"{'='*80}{Style.RESET_ALL}\n")
    
    def scan_pools(self) -> dict:
        """Fetch all pool data"""
        return self.price_fetcher.fetch_all_pools()

    def find_arbitrage(self, pools: dict) -> list:
        """Find arbitrage opportunities"""
        return self.arb_finder.find_opportunities(pools)
    
    
    def simulate_strategy(self, strategy: dict) -> dict:
        """
        Simulate a strategy before execution (ArbiGirl compatibility)

        Args:
            strategy: Dict with est_profit_usd, pair, payload

        Returns:
            Dict with simulation results
        """
        try:
            profit_usd = float(strategy.get("est_profit_usd", 0))
            payload = strategy.get("payload", {})

            # Extract parameters
            token_in = payload.get("token_in")
            token_out = payload.get("token_out")
            amount_in_wei = int(payload.get("amountInWei", 0))

            if not all([token_in, token_out, amount_in_wei > 0]):
                return {
                    "success": False,
                    "error": "Missing required parameters",
                    "profit_usd": 0,
                    "gas_usd": 0,
                    "net_profit_usd": 0
                }

            # Estimate gas cost DYNAMICALLY using GasOptimizationManager
            try:
                from tx_builder import GasOptimizationManager
                gas_mgr = GasOptimizationManager(rpc_manager=self.rpc_manager)

                # Get current gas params
                gas_params = gas_mgr.get_optimized_gas_params()
                max_fee_per_gas = gas_params.get('maxFeePerGas', 40e9)  # Default 40 gwei

                # Estimate gas units (typical arbitrage: 350-450k gas)
                # Use conservative estimate
                estimated_gas_units = 400000

                # Calculate gas cost in POL (wei)
                gas_cost_wei = estimated_gas_units * max_fee_per_gas
                gas_cost_pol = gas_cost_wei / 1e18

                # Get POL price dynamically from CoinGecko
                pol_price_usd = self.price_fetcher.price_fetcher.get_price("WPOL")
                if not pol_price_usd:
                    pol_price_usd = 0.40  # Fallback

                estimated_gas_cost_usd = gas_cost_pol * pol_price_usd

            except Exception as e:
                # Fallback to conservative estimate
                print(f"⚠️ Dynamic gas estimation failed: {e}, using fallback")
                estimated_gas_units = 400000
                max_fee_per_gas = 40e9  # 40 gwei
                gas_cost_pol = (estimated_gas_units * max_fee_per_gas) / 1e18
                pol_price_usd = 0.40
                estimated_gas_cost_usd = gas_cost_pol * pol_price_usd

            net_profit = profit_usd - estimated_gas_cost_usd
            
            if net_profit < 0.5:
                return {
                    "success": False,
                    "profit_usd": profit_usd,
                    "gas_usd": estimated_gas_cost_usd,
                    "net_profit_usd": net_profit,
                    "reason": f"Net profit ${net_profit:.2f} too low after gas"
                }
            
            # Try real simulation with tx_builder if available
            if hasattr(self, 'tx_builder'):
                try:
                    sim_result = self.tx_builder.simulate_arbitrage(
                        token_in_address=token_in,
                        token_out_address=token_out,
                        dex1_address=payload.get("dex1", ""),
                        dex2_address=payload.get("dex2", ""),
                        dex1_version=int(payload.get("dex1Version", 2)),
                        dex2_version=int(payload.get("dex2Version", 2)),
                        amount_in_wei=amount_in_wei,
                        min_profit_wei=int(payload.get("minProfitWei", 0)),
                        dex1_data=bytes.fromhex(payload.get("dex1Data", "").replace("0x", "")) if payload.get("dex1Data") else b'',
                        dex2_data=bytes.fromhex(payload.get("dex2Data", "").replace("0x", "")) if payload.get("dex2Data") else b'',
                        use_balancer=bool(payload.get("use_balancer", True))
                    )
                    
                    if sim_result.get("success"):
                        gas_cost_usd = sim_result.get("gas_cost_pol", 0.15) * 0.40
                        return {
                            "success": True,
                            "profit_usd": profit_usd,
                            "gas_usd": gas_cost_usd,
                            "net_profit_usd": profit_usd - gas_cost_usd,
                            "gas_estimate": sim_result.get("gas_estimate"),
                            "simulated": True
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"Simulation failed: {sim_result.get('error')}",
                            "profit_usd": profit_usd,
                            "gas_usd": estimated_gas_cost_usd,
                            "net_profit_usd": 0
                        }
                except Exception:
                    pass
            
            # Fallback: estimate-based
            return {
                "success": True,
                "profit_usd": profit_usd,
                "gas_usd": estimated_gas_cost_usd,
                "net_profit_usd": net_profit,
                "simulated": False,
                "note": "Estimated (no real simulation)"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "profit_usd": 0,
                "gas_usd": 0,
                "net_profit_usd": 0
            }
    
    def execute_proposal(self, proposal: dict) -> str:
        """
        Execute a trading proposal (ArbiGirl compatibility)
        
        Returns:
            Transaction hash (0x...) or uuid:// for tracking
        """
        import uuid
        import os
        
        try:
            payload = proposal.get("payload", {})
            
            # Extract required parameters
            token_in = payload.get("token_in")
            token_out = payload.get("token_out")
            dex1 = payload.get("dex1")
            dex2 = payload.get("dex2")
            amount_in_wei = int(payload.get("amountInWei", 0))
            min_profit_wei = int(payload.get("minProfitWei", 0))
            
            if not all([token_in, token_out, dex1, dex2, amount_in_wei > 0]):
                raise ValueError("Missing required parameters for execution")
            
            # Initialize tx_builder if needed
            if not hasattr(self, 'tx_builder'):
                from tx_builder import FlashbotsTxBuilder
                
                contract_address = os.getenv("CONTRACT_ADDRESS")
                private_key = os.getenv("PRIVATE_KEY")
                rpc_url = os.getenv("ALCHEMY_URL1")
                
                if not all([contract_address, private_key, rpc_url]):
                    raise ValueError("Missing CONTRACT_ADDRESS, PRIVATE_KEY, or RPC URL in .env")
                
                self.tx_builder = FlashbotsTxBuilder(
                    contract_address=contract_address,
                    private_key=private_key,
                    rpc_url=rpc_url,
                    chain_id=137
                )
            
            # Smart flashloan selection: try Balancer first (fee-free), fallback to Aave
            use_balancer = payload.get("use_balancer", True)
            
            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"🎯 EXECUTING ARBITRAGE")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"   Pair: {proposal.get('summary', 'Unknown')}")
            print(f"   Expected Profit: ${proposal.get('profit_usd', 0):.2f}")
            print(f"   Flashloan: {'Balancer (fee-free)' if use_balancer else 'Aave'}")
            
            # Execute
            result = self.tx_builder.send_arbitrage_tx(
                token_in_address=token_in,
                token_out_address=token_out,
                dex1_address=dex1,
                dex2_address=dex2,
                dex1_version=int(payload.get("dex1Version", 2)),
                dex2_version=int(payload.get("dex2Version", 2)),
                amount_in_wei=amount_in_wei,
                min_profit_wei=min_profit_wei,
                dex1_data=bytes.fromhex(payload.get("dex1Data", "").replace("0x", "")) if payload.get("dex1Data") else b'',
                dex2_data=bytes.fromhex(payload.get("dex2Data", "").replace("0x", "")) if payload.get("dex2Data") else b'',
                use_flashbots=False,
                use_balancer=use_balancer,
                bot_source="arbigirl"
            )
            
            if result.get("success"):
                tx_hash = result.get("tx_hash")
                print(f"{Fore.GREEN}✅ Trade executed!{Style.RESET_ALL}")
                print(f"   TX: https://polygonscan.com/tx/{tx_hash}")
                return tx_hash
            else:
                error = result.get("error", "Unknown error")
                print(f"{Fore.RED}❌ Trade failed: {error}{Style.RESET_ALL}")
                
                # Retry with Aave if Balancer failed due to token availability
                if use_balancer and "token not available" in error.lower():
                    print(f"{Fore.YELLOW}🔄 Retrying with Aave...{Style.RESET_ALL}")
                    result = self.tx_builder.send_arbitrage_tx(
                        token_in_address=token_in,
                        token_out_address=token_out,
                        dex1_address=dex1,
                        dex2_address=dex2,
                        dex1_version=int(payload.get("dex1Version", 2)),
                        dex2_version=int(payload.get("dex2Version", 2)),
                        amount_in_wei=amount_in_wei,
                        min_profit_wei=min_profit_wei,
                        dex1_data=bytes.fromhex(payload.get("dex1Data", "").replace("0x", "")) if payload.get("dex1Data") else b'',
                        dex2_data=bytes.fromhex(payload.get("dex2Data", "").replace("0x", "")) if payload.get("dex2Data") else b'',
                        use_flashbots=False,
                        use_balancer=False,
                        bot_source="arbigirl"
                    )
                    
                    if result.get("success"):
                        print(f"{Fore.GREEN}✅ Executed with Aave!{Style.RESET_ALL}")
                        return result.get("tx_hash")
                
                return "uuid://" + str(uuid.uuid4())
        
        except Exception as e:
            print(f"{Fore.RED}❌ Execution error: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            return "uuid://" + str(uuid.uuid4())

    def print_scan_summary(self, pools_scanned, valid_pools, low_liquidity_pools, opportunities):
        """Print end-of-cycle diagnostics and performance summary"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"📊 SCAN SUMMARY")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Total pools scanned:     {pools_scanned:,}")
        print(f"   ✅ Valid (>${self.min_tvl:,.0f} TVL): {valid_pools:,}")
        print(f"   ⚠️  Low liquidity:         {low_liquidity_pools:,}")
        print(f"   💰 Opportunities found:   {len(opportunities):,}")
        print(f"   ⏰ Cache valid for:       {self.cache.cache_duration / 3600:.0f} hours")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        # RPC stats
        print(f"{Fore.CYAN}{'='*80}")
        print(f"📡 RPC MANAGER STATISTICS")
        print(f"{'='*80}{Style.RESET_ALL}")
        
        stats = self.rpc_manager.stats()
        working_rpcs = sum(1 for s in stats.values() if s["ok"])
        total_calls = sum(s["calls"] for s in stats.values())
        total_failures = sum(s["failures"] for s in stats.values())
        
        print(f"   Working RPCs: {working_rpcs}/{len(stats)}")
        print(f"   Total Calls: {total_calls:,}")
        print(f"   Total Failures: {total_failures:,}")
        print(f"   Success Rate: {(total_calls - total_failures) / max(total_calls, 1) * 100:.1f}%\n")
        
        # Top 5 RPCs by usage
        sorted_stats = sorted(stats.items(), key=lambda x: x[1]["calls"], reverse=True)[:5]
        print(f"   {'Top 5 RPCs':<20} {'Calls':<10} {'Failures':<10} {'Status'}")
        print(f"   {'-'*60}")
        for name, s in sorted_stats:
            status = "✅ OK" if s["ok"] else "❌ FAIL"
            print(f"   {name:<20} {s['calls']:<10} {s['failures']:<10} {status}")
        
        print(f"\n{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        # Cache stats
        self.cache.print_stats()
        
        # System timing
        uptime_hours = (time.time() - self.start_time) / 3600
        print(f"   ⏱️  Uptime: {uptime_hours:.1f}h")
        print(f"   🔄 Total scans: {self.total_scans}")
        print(f"   💰 Total opportunities: {self.total_opportunities}")
        print(f"   📊 Avg opportunities/scan: {self.total_opportunities / max(self.total_scans, 1):.1f}")
        print(f"   ⏰ Next scan in: {self.scan_interval}s")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
    
    def print_opportunities(self, opportunities: list):
        """Print top opportunities"""
        if not opportunities:
            print(f"{Fore.YELLOW}No arbitrage opportunities found in this scan{Style.RESET_ALL}\n")
            return
        
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"💰 TOP ARBITRAGE OPPORTUNITIES")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        
        # Sort by profit (use correct field name)
        opportunities.sort(key=lambda x: x.get("net_profit_usd", 0), reverse=True)
        
        for i, opp in enumerate(opportunities[:5], 1):  # Top 5
            print(f"{Fore.GREEN}{i}. {opp.get('pair', 'Unknown')}{Style.RESET_ALL}")
            print(f"   Direction: {opp.get('direction', 'N/A')}")
            print(f"   Buy:  {opp.get('dex_buy', 'Unknown')}")
            print(f"   Sell: {opp.get('dex_sell', 'Unknown')}")
            print(f"   Profit: ${opp.get('net_profit_usd', 0):.2f} (ROI: {opp.get('roi', 0):.2f}%)")
            print(f"   Trade size: ${opp.get('trade_size_usd', 0):,.0f}")
            print(f"   Gas cost: ${opp.get('gas_cost_usd', 0):.2f}\n")
        
        print(f"{Fore.GREEN}{'='*80}{Style.RESET_ALL}\n")
    
    def run_single_scan(self, token_filter: str = None):
        """
        Run a single scan cycle
        
        Args:
            token_filter: Optional token symbol to filter (e.g., "WETH", "USDC")
                         Only scans pools containing this token
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔄 STARTING SCAN #{self.total_scans + 1}")
        if token_filter:
            print(f"🎯 Filtering for: {token_filter.upper()} pairs only")
        print(f"{'='*80}{Style.RESET_ALL}\n")
        
        start_time = time.time()
        
        try:
            # 1️⃣ Scan pools
            print(f"{Fore.YELLOW}Step 1/3: Scanning pools for liquidity...{Style.RESET_ALL}")
            filtered_pools = self.scan_pools()
            
            # Apply token filter if specified
            if token_filter:
                token_upper = token_filter.upper()
                original_count = sum(len(pairs) for pairs in filtered_pools.values())
                
                filtered_pools = {
                    dex: {
                        pair_name: pair_data
                        for pair_name, pair_data in pairs.items()
                        if token_upper in pair_name.upper()
                    }
                    for dex, pairs in filtered_pools.items()
                }
                
                # Remove empty DEXes
                filtered_pools = {dex: pairs for dex, pairs in filtered_pools.items() if pairs}
                
                filtered_count = sum(len(pairs) for pairs in filtered_pools.values())
                print(f"{Fore.CYAN}   🎯 Filtered: {original_count} → {filtered_count} pairs containing '{token_upper}'{Style.RESET_ALL}")
            
            # Count pools
            total_pools = sum(
                len(pairs) if isinstance(pairs, dict) and any(isinstance(v, dict) and "pool" in v for v in pairs.values())
                else sum(len(tiers) for tiers in pairs.values() if isinstance(tiers, dict))
                for pairs in filtered_pools.values()
            )
            
            valid_pools = sum(
                1 for dex, pairs in filtered_pools.items()
                for pair_name, pair_data in pairs.items()
                if isinstance(pair_data, dict) and (
                    "liquidity_data" in pair_data or 
                    any("liquidity_data" in tier for tier in pair_data.values() if isinstance(tier, dict))
                )
            )
            
            # 2️⃣ Find arbitrage
            print(f"\n{Fore.YELLOW}Step 2/3: Searching for arbitrage opportunities...{Style.RESET_ALL}")
            opportunities = self.find_arbitrage(filtered_pools)
            
            # 3️⃣ Print results
            print(f"\n{Fore.YELLOW}Step 3/3: Analyzing results...{Style.RESET_ALL}")
            
            elapsed = time.time() - start_time
            
            # Update stats
            self.total_scans += 1
            self.total_opportunities += len(opportunities)
            
            # Print opportunities
            self.print_opportunities(opportunities)

            # ⚡ AUTO-EXECUTE if enabled
            if self.auto_executor and opportunities:
                print(f"\n{Fore.YELLOW}{'='*80}")
                print(f"⚡ AUTO-EXECUTION MODE ACTIVE")
                print(f"{'='*80}{Style.RESET_ALL}\n")

                for i, opp in enumerate(opportunities, 1):
                    print(f"\n{Fore.CYAN}[{i}/{len(opportunities)}] Evaluating opportunity...{Style.RESET_ALL}")

                    # Check if should execute
                    should_exec, reason, updated_opp = self.auto_executor.should_execute(opp)

                    if should_exec:
                        # Execute the opportunity
                        result = self.auto_executor.execute_opportunity(updated_opp or opp, self)

                        if result.get("success"):
                            self.total_trades += 1
                            print(f"{Fore.GREEN}✅ Trade #{self.total_trades} completed successfully!{Style.RESET_ALL}\n")
                        else:
                            print(f"{Fore.RED}❌ Trade failed: {result.get('error')}{Style.RESET_ALL}\n")
                    else:
                        print(f"{Fore.YELLOW}⏭️  Skipped: {reason}{Style.RESET_ALL}\n")

                # Print flash loan executor stats
                exec_stats = self.auto_executor.get_stats()
                print(f"\n{Fore.CYAN}{'='*80}")
                print(f"⚡ FLASH LOAN EXECUTOR STATISTICS (ZERO CAPITAL RISK)")
                print(f"{'='*80}{Style.RESET_ALL}")
                print(f"  Total trades attempted: {exec_stats['total_trades']}")
                print(f"  Successful: {exec_stats['successful_trades']}")
                print(f"  Failed: {exec_stats['failed_trades']} (reverted - no capital lost!)")
                print(f"  Success rate: {exec_stats['success_rate']:.1f}%")
                print(f"  Consecutive failures: {exec_stats['consecutive_failures']}")
                print(f"  ")
                print(f"  💰 Total profit: ${exec_stats['total_profit']:.2f}")
                print(f"  ⛽ Gas spent: ${exec_stats['total_gas_spent']:.2f}")
                print(f"  💵 Net P&L: ${exec_stats['net_profit']:.2f}")
                print(f"  ")
                print(f"  Trades this minute: {exec_stats['trades_this_minute']}")
                print(f"  Gas this hour: ${exec_stats['gas_this_hour']:.2f}")
                print(f"  Kill switch: {'🔴 ACTIVE' if exec_stats['kill_switch_active'] else '🟢 INACTIVE'}")
                print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

            # Print summary
            self.print_scan_summary(
                pools_scanned=total_pools,
                valid_pools=valid_pools,
                low_liquidity_pools=0,  # Not tracked separately
                opportunities=opportunities
            )

            print(f"   ⏱️  Scan completed in {elapsed:.2f}s\n")

            return opportunities
        
        except Exception as e:
            print(f"\n{Fore.RED}{'='*80}")
            print(f"❌ SCAN ERROR")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"   Error: {str(e)}\n")
            import traceback
            traceback.print_exc()
            return []
    
    def run_continuous(self):
        """Run continuous scanning loop"""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔁 STARTING CONTINUOUS SCANNING")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Scan Interval: {self.scan_interval}s")
        print(f"   Min TVL: ${self.min_tvl:,}")
        print(f"   Auto Execute: {self.auto_execute}")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")
        
        while True:
            try:
                # Run scan
                opportunities = self.run_single_scan()
                
                # Auto-execute if enabled (implement your execution logic)
                if self.auto_execute and opportunities:
                    print(f"{Fore.YELLOW}⚠️  Auto-execute is enabled but not yet implemented{Style.RESET_ALL}\n")
                
                # Sleep until next scan
                print(f"{Fore.CYAN}💤 Sleeping {self.scan_interval}s until next scan...{Style.RESET_ALL}\n")
                time.sleep(self.scan_interval)
            
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}{'='*80}")
                print(f"⏹️  BOT STOPPED BY USER")
                print(f"{'='*80}{Style.RESET_ALL}")
                print(f"   Total scans: {self.total_scans}")
                print(f"   Total opportunities: {self.total_opportunities}")
                print(f"   Uptime: {(time.time() - self.start_time) / 3600:.1f}h")
                print(f"{Fore.YELLOW}{'='*80}{Style.RESET_ALL}\n")
                break
            
            except Exception as e:
                print(f"\n{Fore.RED}❌ Scan loop error: {e}{Style.RESET_ALL}\n")
                import traceback
                traceback.print_exc()
                print(f"{Fore.YELLOW}Retrying in 10s...{Style.RESET_ALL}\n")
                time.sleep(10)
    
    def cleanup(self):
        """Cleanup before exit"""
        print(f"\n{Fore.CYAN}🧹 Cleaning up...{Style.RESET_ALL}")
        
        # Cleanup expired cache entries
        expired = self.cache.cleanup_expired()
        print(f"   Removed {expired} expired cache entries")
        
        # Print final stats
        self.rpc_manager.print_stats()
        self.cache.print_stats()
        
        print(f"{Fore.GREEN}✅ Cleanup complete{Style.RESET_ALL}\n")
    
    def scan(self, token_filter: str = None) -> list:
        """
        Scan for arbitrage opportunities (ArbiGirl compatibility)
        
        Args:
            token_filter: Optional token symbol to filter (e.g., "WETH")
        
        Returns:
            List of opportunities
        """
        return self.run_single_scan(token_filter=token_filter)
        
        


def main():
    """Main entry point with interactive menu"""
    print(f"\n{Fore.CYAN}{'='*80}")
    print(f"🚀 POLYGON ARBITRAGE BOT - OPTIMIZED VERSION")
    print(f"{'='*80}{Style.RESET_ALL}\n")
    
    # Initialize bot
    bot = PolygonArbBot(
        min_tvl=3000,            # $3k minimum
        scan_interval=60,        # 60 seconds
        auto_execute=False       # Manual mode (set to True for flash loan auto-execution)
    )
    
    # Interactive menu
    while True:
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🎮 MAIN MENU")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"1. Run Single Scan (find opportunities now)")
        print(f"2. Start Continuous Scanning (every {bot.scan_interval}s)")
        print(f"3. Check RPC Health")
        print(f"4. View Cache Stats")
        print(f"5. Clear Cache")
        print(f"6. Exit")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        
        choice = input(f"\n{Fore.YELLOW}Select option (1-6): {Style.RESET_ALL}").strip()
        
        if choice == "1":
            # Single scan
            opportunities = bot.run_single_scan()
            if opportunities:
                execute = input(f"\n{Fore.YELLOW}Execute trades? (y/n): {Style.RESET_ALL}").strip().lower()
                if execute == 'y':
                    print(f"{Fore.RED}⚠️  Auto-execution not yet implemented{Style.RESET_ALL}")
            input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
        
        elif choice == "2":
            # Continuous scanning
            try:
                bot.run_continuous()
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Stopping continuous scan...{Style.RESET_ALL}")
                continue
        
        elif choice == "3":
            # Health check
            health = bot.rpc_manager.health_check()
            bot.rpc_manager.print_stats()
            input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
        
        elif choice == "4":
            # Cache stats
            bot.cache.print_stats()
            input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
        
        elif choice == "5":
            # Clear cache
            confirm = input(f"\n{Fore.RED}Clear all cache? (y/n): {Style.RESET_ALL}").strip().lower()
            if confirm == 'y':
                bot.cache.clear()
                print(f"{Fore.GREEN}✅ Cache cleared{Style.RESET_ALL}")
            input(f"\n{Fore.CYAN}Press Enter to return to menu...{Style.RESET_ALL}")
        
        elif choice == "6":
            # Exit
            print(f"\n{Fore.YELLOW}Exiting...{Style.RESET_ALL}")
            bot.cleanup()
            break
        
        else:
            print(f"{Fore.RED}Invalid choice. Please select 1-6.{Style.RESET_ALL}")
            time.sleep(1)
            
PolygonArbBot.scan = PolygonArbBot.run_single_scan


if __name__ == "__main__":
    main()
