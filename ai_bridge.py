#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Bridge - All-in-One MEV Bot
Single file that starts API server + AI CLI

Architecture:
1. Starts FastAPI server in background thread
2. Loads pools from pool_registry.json
3. Gets QUOTES from actual DEX contracts (not reserves!)
4. Shows calculations on screen
5. AI-powered CLI interface

Run:
  python ai_bridge.py
AI Bridge (ArbiGirl) - Updated to use PolygonArbBot with 300+ pools
"""

import json
import time
import os
import sys
import threading
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path

import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from web3 import Web3

# FastAPI imports
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import PolygonArbBot which has 300+ pools and ArbiGirl compatibility
from polygon_arb_bot import PolygonArbBot

init(autoreset=True)
load_dotenv()

# Configuration
API_PORT = int(os.getenv("API_PORT", "5050"))
API_HOST = os.getenv("API_HOST", "127.0.0.1")
MIN_PROFIT_USD = float(os.getenv("ARBIGIRL_MIN_PROFIT_USD", "1.0"))
AUTO_EXECUTE = os.getenv("ARBIGIRL_AUTO_EXECUTE", "false").lower() in ("1", "true", "yes", "y")

# Logging
LOG_PATH = os.getenv("ARBIGIRL_LOG", "arbigirl.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_PATH, encoding="utf-8")
    ],
)
logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI SERVER SETUP
# ============================================================================

app = FastAPI(title="MEV Bot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class ScanRequest(BaseModel):
    min_profit_usd: Optional[float] = 1.0
    min_tvl: Optional[float] = 10000.0
    max_opportunities: Optional[int] = 10

class SimulateRequest(BaseModel):
    strategy: Dict[str, Any]

class ProposalPayload(BaseModel):
    strategy_id: str
    summary: str
    profit_usd: float
    payload: Dict[str, Any]

class ProposeRequest(BaseModel):
    proposal: ProposalPayload
    auto_execute: bool = False

# Global state
_bot_stats = {
    "start_time": time.time(),
    "total_scans": 0,
    "total_opportunities_found": 0,
    "total_trades_executed": 0,
    "total_profit_usd": 0.0,
    "last_scan_time": None,
    "last_scan_duration": 0.0,
    "last_opportunities": [],
    "errors": []
}

# ============================================================================
# QUOTE-BASED ARBITRAGE SCANNER (NO RESERVES!)
# ============================================================================

class QuoteBasedScanner:
    """
    Scans for arbitrage using ACTUAL QUOTES from DEX routers
    NOT reserve calculations!
    """

    def __init__(self, web3: Web3, pool_registry_path: str = "pool_registry.json"):
        self.web3 = web3
        self.pool_registry = self._load_pool_registry(pool_registry_path)
        self.price_calc = PriceCalculator(web3)
        self.trade_db = get_database()

        # Test amounts to quote (in base units, will convert)
        self.test_amounts_usd = [1000, 10000, 100000]

        logger.info(f"QuoteBasedScanner initialized with {len(self._count_pools())} pools")

    def _load_pool_registry(self, path: str) -> Dict:
        """Load pool registry from JSON file"""
        try:
            with open(path, 'r') as f:
                registry = json.load(f)
            logger.info(f"Loaded pool registry from {path}")
            return registry
        except Exception as e:
            logger.error(f"Failed to load pool registry: {e}")
            return {}

    def _count_pools(self) -> int:
        """Count total pools in registry"""
        count = 0
        for dex_name, pairs in self.pool_registry.items():
            count += len(pairs)
        return count

    def _get_token_info(self, address: str) -> Dict:
        """Get token info from registry"""
        address = Web3.to_checksum_address(address)
        for symbol, info in TOKEN_REGISTRY.items():
            if info["address"].lower() == address.lower():
                return {"symbol": symbol, **info}
        return {"symbol": "UNKNOWN", "decimals": 18, "address": address}

    def _group_pools_by_pair(self) -> Dict[str, List[Dict]]:
        """
        Group all pools by token pair
        Returns: {pair: [pool1, pool2, ...]}
        """
        pair_pools = {}

        for dex_name, pairs in self.pool_registry.items():
            for pair_name, pool_data in pairs.items():
                # Normalize pair name (sort tokens)
                tokens = pair_name.split('/')
                if len(tokens) != 2:
                    continue

                # Create normalized pair key
                pair_key = '/'.join(sorted(tokens))

                if pair_key not in pair_pools:
                    pair_pools[pair_key] = []

                pair_pools[pair_key].append({
                    "dex": dex_name,
                    "pair": pair_name,
                    "pool_address": pool_data["pool"],
                    "token0": pool_data["token0"],
                    "token1": pool_data["token1"],
                    "type": pool_data.get("type", "v2")
                })

        return pair_pools

    def _get_quote_from_pool(
        self,
        pool: Dict,
        token_in: str,
        token_out: str,
        amount_in: int
    ) -> Optional[float]:
        """
        Get ACTUAL QUOTE from pool using router/quoter contracts

        Args:
            pool: Pool data dict
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount in (in wei)

        Returns:
            Amount out (in wei) or None if failed
        """
        try:
            # Use price_math.py's quote methods
            if pool["type"] == "v3":
                # Uniswap V3 - use quoter
                amount_out = self.price_calc.get_v3_quote(
                    pool["pool_address"],
                    token_in,
                    token_out,
                    amount_in
                )
            else:
                # V2 - use router getAmountsOut
                dex = pool["dex"]
                router_address = DEX_ROUTERS.get(dex.lower().replace('_v2', ''))

                if router_address:
                    amount_out = self.price_calc.get_v2_quote(
                        router_address,
                        token_in,
                        token_out,
                        amount_in
                    )
                else:
                    logger.warning(f"No router found for {dex}")
                    return None

            return amount_out

        except Exception as e:
            logger.debug(f"Quote failed for {pool['dex']} {pool['pair']}: {e}")
            return None

    def _calculate_arbitrage_for_pair(
        self,
        pair: str,
        pools: List[Dict],
        amount_usd: float
    ) -> Optional[Dict]:
        """
        Calculate arbitrage for a specific pair and amount

        Process:
        1. Get quotes from ALL pools for this pair
        2. Find best buy (lowest output = cheapest)
        3. Find best sell (highest output = most expensive)
        4. Calculate profit

        Args:
            pair: Token pair (e.g., "USDC/WMATIC")
            pools: List of pools trading this pair
            amount_usd: Input amount in USD

        Returns:
            Arbitrage opportunity dict or None
        """
        if len(pools) < 2:
            return None  # Need at least 2 pools to arbitrage

        # Get token addresses (use first pool as reference)
        tokens = pair.split('/')
        if len(tokens) != 2:
            return None

        # Find token info
        token0_info = None
        token1_info = None
        for symbol, info in TOKEN_REGISTRY.items():
            if symbol == tokens[0]:
                token0_info = info
            if symbol == tokens[1]:
                token1_info = info

        if not token0_info or not token1_info:
            return None

        token0_address = token0_info["address"]
        token1_address = token1_info["address"]

        # Convert USD amount to token amount (assume USDC-like = 6 decimals)
        # This is simplified - in production, use actual USD price
        amount_in = int(amount_usd * (10 ** 6))  # Assume USDC

        # Get quotes from all pools
        quotes = []
        print(f"\n{Fore.CYAN}{'='*70}")
        print(f"Scanning pair: {Fore.YELLOW}{pair}{Fore.CYAN} with ${amount_usd:,.0f}")
        print(f"{'='*70}{Style.RESET_ALL}\n")

        for pool in pools:
            # Try both directions
            for direction in ["forward", "reverse"]:
                if direction == "forward":
                    t_in, t_out = token0_address, token1_address
                    direction_str = f"{tokens[0]} → {tokens[1]}"
                else:
                    t_in, t_out = token1_address, token0_address
                    direction_str = f"{tokens[1]} → {tokens[0]}"

                quote = self._get_quote_from_pool(pool, t_in, t_out, amount_in)

                if quote and quote > 0:
                    # Calculate rate
                    rate = quote / amount_in

                    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {pool['dex']:20} | {direction_str:20} | "
                          f"In: {amount_in / 1e6:,.2f} | Out: {quote / 1e18:,.2f} | "
                          f"Rate: {rate:.6f}")

                    quotes.append({
                        "pool": pool,
                        "token_in": t_in,
                        "token_out": t_out,
                        "amount_in": amount_in,
                        "amount_out": quote,
                        "rate": rate,
                        "direction": direction_str
                    })
                else:
                    print(f"  {Fore.RED}✗{Style.RESET_ALL} {pool['dex']:20} | {direction_str:20} | "
                          f"Quote failed")

        if len(quotes) < 2:
            print(f"\n{Fore.YELLOW}Insufficient quotes for arbitrage{Style.RESET_ALL}\n")
            return None

        # Find best buy and sell
        # Best buy = lowest rate (pay less to get output token)
        # Best sell = highest rate (get more when selling output token)
        best_buy = min(quotes, key=lambda x: x["rate"])
        best_sell = max(quotes, key=lambda x: x["rate"])

        # Calculate profit
        # If we can buy cheap and sell expensive, there's profit
        if best_sell["rate"] > best_buy["rate"]:
            profit_rate = best_sell["rate"] - best_buy["rate"]
            profit_pct = (profit_rate / best_buy["rate"]) * 100

            # Estimate profit in USD (simplified)
            profit_usd = profit_rate * amount_usd

            print(f"\n{Fore.GREEN}{'='*70}")
            print(f"  💰 ARBITRAGE OPPORTUNITY FOUND!")
            print(f"{'='*70}{Style.RESET_ALL}")
            print(f"  Buy from:  {Fore.YELLOW}{best_buy['pool']['dex']}{Style.RESET_ALL} @ rate {best_buy['rate']:.6f}")
            print(f"  Sell to:   {Fore.YELLOW}{best_sell['pool']['dex']}{Style.RESET_ALL} @ rate {best_sell['rate']:.6f}")
            print(f"  Profit:    {Fore.GREEN}${profit_usd:.2f} ({profit_pct:.2f}%){Style.RESET_ALL}\n")

            return {
                "pair": pair,
                "amount_usd": amount_usd,
                "dex_buy": best_buy["pool"]["dex"],
                "dex_sell": best_sell["pool"]["dex"],
                "buy_rate": best_buy["rate"],
                "sell_rate": best_sell["rate"],
                "net_profit_usd": profit_usd,
                "roi_percent": profit_pct,
                "amount_in": amount_in,
                "direction_buy": best_buy["direction"],
                "direction_sell": best_sell["direction"]
            }

        print(f"\n{Fore.YELLOW}No profitable arbitrage (best sell rate <= best buy rate){Style.RESET_ALL}\n")
        return None

    def scan_all_pairs(self, min_profit_usd: float = 1.0) -> List[Dict]:
        """
        Scan ALL pairs for arbitrage opportunities

        Process:
        1. Group pools by pair
        2. For each pair with 2+ pools:
           - Test with 3 different amounts (1000, 10000, 100000 USD)
           - Get quotes from all pools
           - Find arbitrage opportunities

        Returns:
            List of opportunities sorted by profit
        """
        logger.info("Starting quote-based arbitrage scan...")
        print(f"\n{Fore.MAGENTA}{'='*70}")
        print(f"  🔍 STARTING ARBITRAGE SCAN")
        print(f"  Using ACTUAL QUOTES from DEX contracts (no reserves!)")
        print(f"{'='*70}{Style.RESET_ALL}\n")

        pair_pools = self._group_pools_by_pair()
        opportunities = []

        # Filter to pairs with 2+ pools
        tradeable_pairs = {pair: pools for pair, pools in pair_pools.items() if len(pools) >= 2}

        print(f"Found {len(tradeable_pairs)} pairs with multiple pools\n")

        for i, (pair, pools) in enumerate(tradeable_pairs.items(), 1):
            print(f"\n{Fore.CYAN}[{i}/{len(tradeable_pairs)}] Pair: {pair} ({len(pools)} pools){Style.RESET_ALL}")

            # Test with different amounts
            for amount_usd in self.test_amounts_usd:
                opp = self._calculate_arbitrage_for_pair(pair, pools, amount_usd)

                if opp and opp["net_profit_usd"] >= min_profit_usd:
                    opportunities.append(opp)

                    # Log to database
                    try:
                        self.trade_db.log_opportunity(
                            pair=opp["pair"],
                            dex_buy=opp["dex_buy"],
                            dex_sell=opp["dex_sell"],
                            profit_usd=opp["net_profit_usd"],
                            roi_percent=opp["roi_percent"],
                            executed=False
                        )
                    except Exception as e:
                        logger.error(f"Failed to log opportunity: {e}")

        # Sort by profit
        opportunities.sort(key=lambda x: x["net_profit_usd"], reverse=True)

        print(f"\n{Fore.MAGENTA}{'='*70}")
        print(f"  ✅ SCAN COMPLETE")
        print(f"  Found {len(opportunities)} profitable opportunities")
        print(f"{'='*70}{Style.RESET_ALL}\n")

        return opportunities


# ============================================================================
# FASTAPI ENDPOINTS
# ============================================================================

_scanner: Optional[QuoteBasedScanner] = None

def get_scanner() -> QuoteBasedScanner:
    """Get or create scanner instance"""
    global _scanner
    if _scanner is None:
        try:
            rpc = RPCManager()
            _scanner = QuoteBasedScanner(rpc.get_web3())
        except Exception as e:
            logger.error(f"Failed to initialize scanner: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    return _scanner

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "ok",
        "service": "MEV Bot API",
        "version": "1.0.0",
        "uptime_seconds": time.time() - _bot_stats["start_time"]
    }

@app.get("/status")
async def get_status():
    """Get bot status"""
    uptime = time.time() - _bot_stats["start_time"]
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "uptime_formatted": f"{int(uptime//3600)}h {int((uptime%3600)//60)}m",
        "statistics": {
            "total_scans": _bot_stats["total_scans"],
            "total_opportunities_found": _bot_stats["total_opportunities_found"],
            "total_trades_executed": _bot_stats["total_trades_executed"],
            "total_profit_usd": _bot_stats["total_profit_usd"],
        },
        "last_scan": {
            "timestamp": _bot_stats["last_scan_time"],
            "duration_seconds": _bot_stats["last_scan_duration"],
            "opportunities_found": len(_bot_stats["last_opportunities"])
        } if _bot_stats["last_scan_time"] else None
    }

@app.post("/scan")
async def scan_opportunities(request: Optional[ScanRequest] = None):
    """Scan for arbitrage opportunities"""
    start_time = time.time()

    try:
        scanner = get_scanner()
        min_profit = request.min_profit_usd if request else MIN_PROFIT_USD

        logger.info(f"Starting scan with min_profit=${min_profit}")
        opportunities = scanner.scan_all_pairs(min_profit_usd=min_profit)

        scan_duration = time.time() - start_time
        _bot_stats["total_scans"] += 1
        _bot_stats["total_opportunities_found"] += len(opportunities)
        _bot_stats["last_scan_time"] = datetime.now().isoformat()
        _bot_stats["last_scan_duration"] = scan_duration
        _bot_stats["last_opportunities"] = opportunities

        # Log metrics
        trade_db = get_database()
        trade_db.log_metric("scan_duration", scan_duration)
        trade_db.log_metric("opportunities_found", len(opportunities))

        max_opps = request.max_opportunities if request else 10
        return {
            "status": "ok",
            "found_opportunities": opportunities[:max_opps],
            "total_found": len(opportunities),
            "scan_duration_seconds": scan_duration,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        error_msg = f"Scan failed: {str(e)}"
        logger.error(error_msg)
        _bot_stats["errors"].append({
            "timestamp": datetime.now().isoformat(),
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/simulate")
async def simulate_strategy(request: SimulateRequest):
    """Simulate strategy execution"""
    try:
        strategy = request.strategy
        net_profit = float(strategy.get("net_profit_usd", 0))
        gas_cost_usd = 0.5  # Polygon is cheap

        net_after_gas = net_profit - gas_cost_usd
        success = net_after_gas > 0

        return {
            "status": "ok",
            "sim": {
                "success": success,
                "pair": strategy.get("pair"),
                "gross_profit_usd": net_profit,
                "gas_cost_usd": gas_cost_usd,
                "net_profit_usd": net_after_gas,
                "reason": "Profitable" if success else "Not profitable after gas"
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "sim": {"success": False}
        }

@app.post("/propose")
async def propose_execution(request: ProposeRequest):
    """Propose/execute trade"""
    try:
        proposal = request.proposal
        proposal_id = f"prop_{int(time.time())}_{proposal.strategy_id}"

        if not request.auto_execute:
            return {
                "status": "proposed",
                "proposal_id": proposal_id,
                "message": "Proposal created (not executed)"
            }

        # Mock execution for now
        tx_hash = f"0x{'0'*64}"
        logger.warning("Mock execution - implement flashloan integration!")

        _bot_stats["total_trades_executed"] += 1
        _bot_stats["total_profit_usd"] += proposal.profit_usd

        # Log trade
        trade_db = get_database()
        trade_db.log_trade(
            pair=proposal.payload.get("pair", "unknown"),
            dex_buy=proposal.payload.get("dex_buy", ""),
            dex_sell=proposal.payload.get("dex_sell", ""),
            amount_in=float(proposal.payload.get("amount_usd", 0)),
            profit_usd=proposal.profit_usd,
            tx_hash=tx_hash,
            status="pending",
            metadata={"proposal_id": proposal_id}
        )

        return {
            "status": "executed",
            "proposal_id": proposal_id,
            "tx_hash": tx_hash,
            "profit_usd": proposal.profit_usd
        }

    except Exception as e:
        error_msg = f"Execution failed: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


# ============================================================================
# API SERVER THREAD
# ============================================================================

def start_api_server():
    """Start FastAPI server in background"""
    logger.info(f"Starting API server on {API_HOST}:{API_PORT}")
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level="error",  # Reduce noise
        access_log=False
    )


# ============================================================================
# CLI INTERFACE
# ============================================================================

def say(text: str):
    """Print and log"""
    print(text)
    logging.info(text)

def parse_intent(user_input: str) -> Tuple[str, Dict]:
    """Parse user intent"""
    low = user_input.lower().strip()

    if any(w in low for w in ["status", "stats", "health"]):
        return "status", {}

    if any(w in low for w in ["scan", "find", "search"]):
        continuous = any(w in low for w in ["continuous", "auto", "loop"])
        return "scan", {"continuous": continuous}

    if any(w in low for w in ["stop", "pause"]):
        return "stop", {}

    if any(w in low for w in ["help", "?"]):
        return "help", {}

    if any(w in low for w in ["quit", "exit", "bye"]):
        return "quit", {}

    return "status", {}

class CLInterface:
    """CLI Interface"""

class ArbiGirl:
    """AI-powered arbitrage bot with 300+ pool scanner"""

    def __init__(self):
        """Initialize ArbiGirl with PolygonArbBot (300+ pools)"""
        print(f"\n{Fore.MAGENTA}{'='*60}")
        print(f"         🤖 ArbiGirl MEV Bot v3.0")
        print(f"         Now with 300+ pools from pool_registry!")
        print(f"{'='*60}{Style.RESET_ALL}\n")

        # Initialize PolygonArbBot (has 300+ pools + ArbiGirl compatibility)
        self.bot = PolygonArbBot(
            min_tvl=10000,
            scan_interval=60,
            cache_duration_hours=6,
            auto_execute=False
        )

        # Command queue for async operations
        self.command_queue = queue.Queue()

        # State
        self.auto_scan = False
        self.api_url = f"http://{API_HOST}:{API_PORT}"
        self.last_opportunities = []

        print(f"{Fore.GREEN}✓ ArbiGirl initialized successfully!{Style.RESET_ALL}")
        print(f"  • Ready to scan 300+ pools from pool_registry.json")
        print(f"  • Cache duration: 6 hours for DEX prices")
        self._show_help()

    def _show_help(self):
        """Show available commands"""
        print(f"\n{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}scan{Style.RESET_ALL}       - Run one arbitrage scan (300+ pools)")
        print(f"  {Fore.YELLOW}auto{Style.RESET_ALL}       - Start/stop automatic scanning")
        print(f"  {Fore.YELLOW}status{Style.RESET_ALL}     - Show current status and statistics")
        print(f"  {Fore.YELLOW}pools{Style.RESET_ALL}      - Show pool registry info")
        print(f"  {Fore.YELLOW}clear{Style.RESET_ALL}      - Clear the screen")
        print(f"  {Fore.YELLOW}help{Style.RESET_ALL}       - Show this help")
        print(f"  {Fore.YELLOW}exit{Style.RESET_ALL}       - Exit ArbiGirl")
    
    def handle_scan(self):
        """Run a single scan"""
        print(f"\n{Fore.CYAN}🔍 Running arbitrage scan (300+ pools)...{Style.RESET_ALL}")

        start_time = time.time()
        opportunities = self.bot.run_single_scan()
        scan_time = time.time() - start_time

        self.last_opportunities = opportunities

        if opportunities:
            print(f"\n{Fore.GREEN}✨ Found {len(opportunities)} opportunities!{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}No opportunities found this scan.{Style.RESET_ALL}")

        print(f"\n{Fore.BLUE}Scan completed in {scan_time:.2f}s{Style.RESET_ALL}")
    
    def handle_auto(self):
        """Toggle automatic scanning"""
        self.auto_scan = not self.auto_scan
        
        if self.auto_scan:
            print(f"\n{Fore.GREEN}🔄 Automatic scanning ENABLED{Style.RESET_ALL}")
            print(f"  Scanning every 5 seconds...")
            print(f"  Type 'auto' again to stop")
            
            # Start auto scan in background
            thread = threading.Thread(target=self._auto_scan_loop)
            thread.daemon = True
            thread.start()
            return

        say(f"\n{Fore.CYAN}🔍 Starting arbitrage scan...{Style.RESET_ALL}")

        try:
            resp = requests.post(
                f"{self.api_url}/scan",
                json={"min_profit_usd": MIN_PROFIT_USD},
                timeout=300
            )

            if resp.status_code == 200:
                data = resp.json()
                opps = data.get("found_opportunities", [])
                self.last_opportunities = opps

                if opps:
                    say(f"\n{Fore.GREEN}✨ Found {len(opps)} opportunities!{Style.RESET_ALL}\n")
                    for i, opp in enumerate(opps[:5], 1):
                        say(f"  {i}. {opp['pair']}: ${opp['net_profit_usd']:.2f} "
                            f"({opp['roi_percent']:.2f}%)")
                        say(f"     Buy: {opp['dex_buy']} | Sell: {opp['dex_sell']}")
                else:
                    say(f"\n{Fore.YELLOW}No opportunities found{Style.RESET_ALL}")

                say(f"\n⏱️ Scan took {data['scan_duration_seconds']:.2f}s")
            else:
                say(f"{Fore.RED}Scan failed: {resp.text}{Style.RESET_ALL}")

        except Exception as e:
            say(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")

    def _auto_scan_loop(self):
        while self.auto_scan:
            self.handle_scan()
            time.sleep(5)
    
    def handle_debug(self, args):
        """Toggle debug mode (not applicable with PolygonArbBot)"""
        print(f"\n{Fore.YELLOW}Debug mode not available with PolygonArbBot scanner{Style.RESET_ALL}")
        print(f"  PolygonArbBot uses optimized pool scanning")
        print(f"  Check bot logs for detailed information")
    
    def handle_status(self):
        """Show current status"""
        print(f"\n{Fore.CYAN}{'='*40}")
        print(f"         System Status")
        print(f"{'='*40}{Style.RESET_ALL}")

        print(f"  • Scanner: PolygonArbBot (300+ pools)")
        print(f"  • Auto-scan: {'ON' if self.auto_scan else 'OFF'}")
        print(f"  • Cache duration: {self.bot.cache.cache_duration / 3600:.0f}h")
        print(f"  • Min TVL: ${self.bot.min_tvl:,}")
        print(f"  • Last scan: {len(self.last_opportunities)} opportunities")
        print(f"  • Total scans: {self.bot.total_scans}")
        print(f"  • Total opportunities: {self.bot.total_opportunities}")

        # Show module info
        print(f"\n{Fore.CYAN}Modules:{Style.RESET_ALL}")
        print(f"  • polygon_arb_bot.py (main bot)")
        print(f"  • pool_scanner.py (300+ pools)")
        print(f"  • cache.py (6h cache)")

        # Check if files exist
        if os.path.exists('pool_registry.json'):
            print(f"  {Fore.GREEN}✓ pool_registry.json found{Style.RESET_ALL}")
        else:
            print(f"  {Fore.RED}✗ pool_registry.json NOT FOUND!{Style.RESET_ALL}")
    
    def handle_pools(self):
        """List loaded pools from pool_registry"""
        print(f"\n{Fore.CYAN}Pool Registry Summary:{Style.RESET_ALL}")

        # Trigger a pool scan to show stats
        print(f"\n  Scanning pool_registry.json for available pools...")
        print(f"  (This will use cache if available)\n")

        # Show cache stats
        self.bot.cache.print_stats()

        print(f"\n  To see full pool details, check pool_registry.json")
        print(f"  Run a scan to see which pools have >$10k TVL")
    
    def handle_clear(self):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        self._show_help()
    
    def run(self):
        say(f"{Fore.GREEN}Ready! Type commands or ask naturally.{Style.RESET_ALL}\n")

        while True:
            try:
                user_input = input(f"{Fore.MAGENTA}You> {Style.RESET_ALL}").strip()

                if not user_input:
                    continue

                action, params = parse_intent(user_input)

                if action == "quit":
                    say(f"\n{Fore.MAGENTA}👋 Goodbye!{Style.RESET_ALL}")
                    break
                elif action == "scan":
                    self.handle_scan(continuous=params.get("continuous", False))
                elif action == "status":
                    self.handle_status()
                elif action == "stop":
                    self.handle_stop()
                elif action == "help":
                    self._show_help()
                else:
                    say(f"{Fore.YELLOW}Unknown command. Type 'help'{Style.RESET_ALL}")

            except KeyboardInterrupt:
                say(f"\n{Fore.YELLOW}Use 'quit' to exit{Style.RESET_ALL}")
            except Exception as e:
                say(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point - starts API server + CLI"""
    try:
        # Check for required files
        required_files = ['polygon_arb_bot.py', 'pool_scanner.py', 'pool_registry.json', 'cache.py', 'rpc_mgr.py']
        missing = []

        for file in required_files:
            if not os.path.exists(file):
                missing.append(file)

        if missing:
            print(f"{Fore.RED}Missing required files:{Style.RESET_ALL}")
            for file in missing:
                print(f"  • {file}")
            print(f"\n{Fore.YELLOW}Please make sure all files are in the same directory!{Style.RESET_ALL}")
            print(f"Required: polygon_arb_bot.py, pool_scanner.py, pool_registry.json, cache.py, rpc_mgr.py")
            return

        # Start ArbiGirl
        bot = ArbiGirl()
        bot.run()

    except Exception as e:
        print(f"{Fore.RED}Failed to start ArbiGirl: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Make sure you have:{Style.RESET_ALL}")
        print(f"  1. polygon_arb_bot.py (main bot)")
        print(f"  2. pool_scanner.py (pool scanning)")
        print(f"  3. pool_registry.json (300+ pools)")
        print(f"  4. cache.py (caching)")
        print(f"  5. rpc_mgr.py (RPC management)")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
