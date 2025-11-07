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

# Import the two core modules
from price_data_fetcher import PriceDataFetcher
from arb_finder import ArbFinder
from rpc_mgr import RPCManager
from cache import Cache
import subprocess

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
    """AI-powered arbitrage bot - runs components independently or together"""

    def __init__(self):
        """Initialize ArbiGirl with pool fetcher and arb finder"""
        print(f"\n{Fore.MAGENTA}{'='*60}")
        print(f"         🤖 ArbiGirl MEV Bot v5.0")
        print(f"         Run any component independently!")
        print(f"{'='*60}{Style.RESET_ALL}\n")

        # Initialize components
        self.rpc_manager = RPCManager()
        self.cache = Cache()
        self.price_fetcher = PriceDataFetcher(
            self.rpc_manager,
            self.cache,
            min_tvl_usd=10000
        )
        self.arb_finder = ArbFinder(min_profit_usd=1.0)

        # State
        self.auto_scan = False
        self.auto_fetch_on_expire = False
        self.last_opportunities = []
        self.last_pools = None

        # AI Monitoring (built-in to ArbiGirl)
        self.events = []
        self.max_history = 10000
        self.stats = {
            'total_fetches': 0,
            'total_calculations': 0,
            'total_arb_checks': 0,
            'total_opportunities': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }

        print(f"\n{Fore.GREEN}✓ ArbiGirl initialized successfully!{Style.RESET_ALL}")
        print(f"  • Price Data Fetcher ready (pair 1hr, TVL 3hr, prices 5min)")
        print(f"  • Arb Finder ready (instant scanning)")
        print(f"  • AI Monitoring active (tracking all operations)")
        self._show_help()

    def log_event(self, event_type: str, details: Dict[str, Any]):
        """Log an event for AI monitoring"""
        event = {
            'timestamp': time.time(),
            'datetime': datetime.now().isoformat(),
            'type': event_type,
            'details': details
        }
        self.events.append(event)

        # Keep only recent events
        if len(self.events) > self.max_history:
            self.events = self.events[-self.max_history:]

        # Update stats
        if event_type == 'fetch':
            self.stats['total_fetches'] += 1
        elif event_type == 'calculation':
            self.stats['total_calculations'] += 1
        elif event_type == 'arb_check':
            self.stats['total_arb_checks'] += 1
        elif event_type == 'opportunity':
            self.stats['total_opportunities'] += 1
        elif event_type == 'cache_hit':
            self.stats['cache_hits'] += 1
        elif event_type == 'cache_miss':
            self.stats['cache_misses'] += 1

    def _query_ai(self, question: str) -> str:
        """Answer questions about operations"""
        q_lower = question.lower()

        # Stats query
        if 'stats' in q_lower or 'statistics' in q_lower:
            total_cache = self.stats['cache_hits'] + self.stats['cache_misses']
            hit_rate = (self.stats['cache_hits'] / total_cache * 100) if total_cache > 0 else 0

            return f"""System Statistics:
  • Total fetches: {self.stats['total_fetches']:,}
  • Total calculations: {self.stats['total_calculations']:,}
  • Total arb checks: {self.stats['total_arb_checks']:,}
  • Total opportunities: {self.stats['total_opportunities']:,}
  • Cache hits: {self.stats['cache_hits']:,}
  • Cache misses: {self.stats['cache_misses']:,}
  • Cache hit rate: {hit_rate:.1f}%
  • Events in memory: {len(self.events):,}"""

        # Coins/tokens query
        if 'coins' in q_lower or 'tokens' in q_lower or 'which coins' in q_lower:
            tokens = set()
            for event in self.events:
                details = event['details']
                if 'token0' in details:
                    tokens.add(details['token0'])
                if 'token1' in details:
                    tokens.add(details['token1'])
                if 'pair' in details:
                    pair_tokens = details['pair'].split('/')
                    tokens.update(pair_tokens)

            if tokens:
                return f"Tokens checked: {', '.join(sorted(tokens))}"
            return "No token data available yet"

        # DEX query
        if 'dex' in q_lower or 'exchange' in q_lower:
            dexes = set()
            for event in self.events:
                details = event['details']
                if 'dex' in details:
                    dexes.add(details['dex'])
                if 'dex_buy' in details:
                    dexes.add(details['dex_buy'])
                if 'dex_sell' in details:
                    dexes.add(details['dex_sell'])

            if dexes:
                return f"DEXes used: {', '.join(sorted(dexes))}"
            return "No DEX data available yet"

        # Latest opportunities
        if 'opportunities' in q_lower or 'arb' in q_lower:
            if self.last_opportunities:
                result = f"Latest opportunities ({len(self.last_opportunities)} found):\n"
                for i, opp in enumerate(self.last_opportunities[:5], 1):
                    result += f"\n{i}. {opp.get('pair')} - ${opp.get('profit_usd', 0):.2f} profit ({opp.get('roi_percent', 0):.2f}% ROI)\n"
                    result += f"   Buy: {opp.get('dex_buy')} @ {opp.get('buy_price', 0):.8f}\n"
                    result += f"   Sell: {opp.get('dex_sell')} @ {opp.get('sell_price', 0):.8f}\n"
                return result
            return "No opportunities found yet"

        # How many pools
        if 'how many pools' in q_lower or 'pool count' in q_lower:
            if self.last_pools:
                pool_count = sum(len(pairs) for pairs in self.last_pools.values())
                return f"Currently tracking {pool_count} pools across {len(self.last_pools)} DEXes"
            return "No pools loaded yet"

        # Cache info
        if 'cache' in q_lower:
            cache_events = [e for e in self.events if e['type'] in ['cache_hit', 'cache_miss']][-10:]
            if cache_events:
                result = "Recent cache activity:\n"
                for event in cache_events:
                    event_type = "HIT" if event['type'] == 'cache_hit' else "MISS"
                    details = event['details']
                    result += f"\n• {event_type}: {details.get('dex', 'N/A')} / {details.get('pool', 'N/A')}\n"
                return result
            return "No cache activity recorded yet"

        # Default
        return f"""I track all operations! Ask me:
  • "show stats" - System statistics
  • "what coins were checked?" - List of tokens
  • "what dexes were used?" - List of DEXes
  • "show opportunities" - Latest arbitrage opportunities
  • "how many pools?" - Pool count
  • "show cache activity" - Cache hits/misses"""

    def _show_help(self):
        """Show available commands"""
        print(f"\n{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}fetch{Style.RESET_ALL}      - Fetch pool data (caches 1hr/3hr)")
        print(f"  {Fore.YELLOW}scan{Style.RESET_ALL}       - Find arbs from cache (instant)")
        print(f"  {Fore.YELLOW}full{Style.RESET_ALL}       - Run full scan (fetch + find arbs)")
        print(f"  {Fore.YELLOW}auto{Style.RESET_ALL}       - Start/stop automatic scanning")
        print(f"  {Fore.YELLOW}cache{Style.RESET_ALL}      - Check cache status")
        print(f"  {Fore.YELLOW}status{Style.RESET_ALL}     - Show current status")
        print(f"\n{Fore.CYAN}Show Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}show pairs{Style.RESET_ALL}         - Show all pair prices")
        print(f"  {Fore.YELLOW}show pools{Style.RESET_ALL}         - Show all pools with details")
        print(f"  {Fore.YELLOW}show tvl{Style.RESET_ALL}           - Show pools by TVL")
        print(f"  {Fore.YELLOW}show dexes{Style.RESET_ALL}         - Show breakdown by DEX")
        print(f"  {Fore.YELLOW}show tokens{Style.RESET_ALL}        - Show all tokens found")
        print(f"  {Fore.YELLOW}show opportunities{Style.RESET_ALL} - Show latest opportunities")
        print(f"\n{Fore.CYAN}Other Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}ask <question>{Style.RESET_ALL} - Ask me about operations")
        print(f"  {Fore.YELLOW}run <file.py>{Style.RESET_ALL} - Run a Python file and diagnose")
        print(f"  {Fore.YELLOW}clear{Style.RESET_ALL}      - Clear the screen")
        print(f"  {Fore.YELLOW}help{Style.RESET_ALL}       - Show this help")
        print(f"  {Fore.YELLOW}exit{Style.RESET_ALL}       - Exit ArbiGirl")

    def handle_show(self, what: str):
        """Show various data based on what user wants to see"""
        if not what:
            print(f"{Fore.YELLOW}Usage: show <what>{Style.RESET_ALL}")
            print(f"\nOptions: pairs, pools, tvl, dexes, tokens, opportunities")
            return

        what_lower = what.lower()

        # Show pairs/pair prices
        if 'pair' in what_lower:
            if not self.last_pools:
                print(f"{Fore.YELLOW}No pools loaded. Run 'fetch' first.{Style.RESET_ALL}")
                return

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"💰 ALL PAIR PRICES")
            print(f"{'='*80}{Style.RESET_ALL}\n")

            total_pairs = 0
            for dex, pairs in self.last_pools.items():
                if pairs:
                    print(f"{Fore.GREEN}📊 {dex}{Style.RESET_ALL}")
                    for pair_name, pool_data in pairs.items():
                        pair_prices = pool_data.get('pair_prices', {})
                        tvl_data = pool_data.get('tvl_data', {})

                        token0 = pair_prices.get('token0', 'N/A')
                        token1 = pair_prices.get('token1', 'N/A')
                        price = pair_prices.get('price', 0)
                        tvl = tvl_data.get('tvl_usd', 0)

                        print(f"   {pair_name:20} | Price: {price:.8f} | TVL: ${tvl:>12,.2f}")
                        total_pairs += 1
                    print()

            print(f"{Fore.CYAN}Total pairs: {total_pairs}{Style.RESET_ALL}\n")

        # Show pools with details
        elif 'pool' in what_lower:
            if not self.last_pools:
                print(f"{Fore.YELLOW}No pools loaded. Run 'fetch' first.{Style.RESET_ALL}")
                return

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"🏊 ALL POOLS WITH DETAILS")
            print(f"{'='*80}{Style.RESET_ALL}\n")

            total_pools = 0
            for dex, pairs in self.last_pools.items():
                if pairs:
                    print(f"{Fore.GREEN}📊 {dex}{Style.RESET_ALL}")
                    for pair_name, pool_data in pairs.items():
                        pair_prices = pool_data.get('pair_prices', {})
                        tvl_data = pool_data.get('tvl_data', {})

                        print(f"\n   {Fore.YELLOW}{pair_name}{Style.RESET_ALL}")
                        print(f"   Pool: {pair_prices.get('pool_address', 'N/A')}")
                        print(f"   Type: {pair_prices.get('type', 'N/A')}")
                        print(f"   Token0: {pair_prices.get('token0', 'N/A')}")
                        print(f"   Token1: {pair_prices.get('token1', 'N/A')}")
                        print(f"   Price: {pair_prices.get('price', 0):.8f}")
                        print(f"   TVL: ${tvl_data.get('tvl_usd', 0):,.2f}")

                        if pair_prices.get('type') == 'v2':
                            print(f"   Reserve0: {pair_prices.get('reserve0', 0):,}")
                            print(f"   Reserve1: {pair_prices.get('reserve1', 0):,}")

                        total_pools += 1
                    print()

            print(f"{Fore.CYAN}Total pools: {total_pools}{Style.RESET_ALL}\n")

        # Show TVL sorted
        elif 'tvl' in what_lower:
            if not self.last_pools:
                print(f"{Fore.YELLOW}No pools loaded. Run 'fetch' first.{Style.RESET_ALL}")
                return

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"💎 POOLS BY TVL (Highest to Lowest)")
            print(f"{'='*80}{Style.RESET_ALL}\n")

            # Collect all pools with TVL
            all_pools = []
            for dex, pairs in self.last_pools.items():
                for pair_name, pool_data in pairs.items():
                    tvl_data = pool_data.get('tvl_data', {})
                    tvl = tvl_data.get('tvl_usd', 0)
                    all_pools.append({
                        'dex': dex,
                        'pair': pair_name,
                        'tvl': tvl,
                        'data': pool_data
                    })

            # Sort by TVL descending
            all_pools.sort(key=lambda x: x['tvl'], reverse=True)

            for i, pool in enumerate(all_pools, 1):
                pair_prices = pool['data'].get('pair_prices', {})
                price = pair_prices.get('price', 0)
                print(f"{i:3}. {pool['dex']:20} | {pool['pair']:20} | "
                      f"TVL: ${pool['tvl']:>12,.2f} | Price: {price:.8f}")

            total_tvl = sum(p['tvl'] for p in all_pools)
            print(f"\n{Fore.CYAN}Total TVL: ${total_tvl:,.2f}{Style.RESET_ALL}\n")

        # Show breakdown by DEX
        elif 'dex' in what_lower:
            if not self.last_pools:
                print(f"{Fore.YELLOW}No pools loaded. Run 'fetch' first.{Style.RESET_ALL}")
                return

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"📊 BREAKDOWN BY DEX")
            print(f"{'='*80}{Style.RESET_ALL}\n")

            for dex, pairs in self.last_pools.items():
                if pairs:
                    total_tvl = 0
                    for pair_name, pool_data in pairs.items():
                        tvl_data = pool_data.get('tvl_data', {})
                        total_tvl += tvl_data.get('tvl_usd', 0)

                    print(f"{Fore.GREEN}{dex:20}{Style.RESET_ALL} | "
                          f"Pairs: {len(pairs):3} | Total TVL: ${total_tvl:>12,.2f}")

            print()

        # Show tokens
        elif 'token' in what_lower or 'coin' in what_lower:
            if not self.last_pools:
                print(f"{Fore.YELLOW}No pools loaded. Run 'fetch' first.{Style.RESET_ALL}")
                return

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"🪙 ALL TOKENS FOUND")
            print(f"{'='*80}{Style.RESET_ALL}\n")

            tokens = set()
            for dex, pairs in self.last_pools.items():
                for pair_name, pool_data in pairs.items():
                    pair_prices = pool_data.get('pair_prices', {})
                    token0 = pair_prices.get('token0')
                    token1 = pair_prices.get('token1')
                    if token0:
                        tokens.add(token0)
                    if token1:
                        tokens.add(token1)

            for i, token in enumerate(sorted(tokens), 1):
                print(f"{i:3}. {token}")

            print(f"\n{Fore.CYAN}Total unique tokens: {len(tokens)}{Style.RESET_ALL}\n")

        # Show opportunities
        elif 'opp' in what_lower or 'arb' in what_lower:
            if not self.last_opportunities:
                print(f"{Fore.YELLOW}No opportunities found yet. Run 'scan' first.{Style.RESET_ALL}")
                return

            print(f"\n{Fore.CYAN}{'='*80}")
            print(f"💰 LATEST ARBITRAGE OPPORTUNITIES")
            print(f"{'='*80}{Style.RESET_ALL}\n")

            for i, opp in enumerate(self.last_opportunities, 1):
                print(f"{Fore.GREEN}{i}. {opp.get('pair')}{Style.RESET_ALL}")
                print(f"   Buy from:  {opp.get('dex_buy')} @ {opp.get('buy_price', 0):.8f}")
                print(f"   Sell to:   {opp.get('dex_sell')} @ {opp.get('sell_price', 0):.8f}")
                print(f"   Profit:    ${opp.get('profit_usd', 0):.2f} ({opp.get('roi_percent', 0):.2f}% ROI)")
                print(f"   Amount:    ${opp.get('amount_usd', 0):,.0f}")
                print()

            print(f"{Fore.CYAN}Total opportunities: {len(self.last_opportunities)}{Style.RESET_ALL}\n")

        else:
            print(f"{Fore.YELLOW}Unknown option: {what}{Style.RESET_ALL}")
            print(f"Available: pairs, pools, tvl, dexes, tokens, opportunities")

    def handle_fetch(self):
        """Fetch pool data"""
        print(f"\n{Fore.CYAN}📡 Fetching pool data...{Style.RESET_ALL}")

        start_time = time.time()
        self.last_pools = self.price_fetcher.fetch_all_pools()
        fetch_time = time.time() - start_time

        pool_count = sum(len(pairs) for pairs in self.last_pools.values())

        # Log fetch event
        self.log_event('fetch', {
            'pool_count': pool_count,
            'dex_count': len(self.last_pools),
            'duration': fetch_time
        })

        print(f"\n{Fore.GREEN}✅ Fetch complete!{Style.RESET_ALL}")
        print(f"  • Pools fetched: {pool_count}")
        print(f"  • Time: {fetch_time:.2f}s")
        print(f"  • Cached: Pair prices (1hr), TVL (3hr)")

    def handle_scan(self):
        """Find arbitrage from cached data"""
        print(f"\n{Fore.CYAN}💰 Scanning for arbitrage (using cache)...{Style.RESET_ALL}")

        # Check if pools were fetched
        if not self.last_pools:
            print(f"\n{Fore.YELLOW}No pools in memory. Fetching first...{Style.RESET_ALL}")
            self.handle_fetch()

        # Check cache expiration
        warning = self.cache.get_expiration_warning()
        if warning:
            print(f"\n{Fore.YELLOW}⚠️  CACHE WARNING:{Style.RESET_ALL}")
            print(warning)

            if not self.auto_fetch_on_expire:
                response = input(f"\n{Fore.YELLOW}Fetch fresh data? (y/n): {Style.RESET_ALL}").strip().lower()
                if response == 'y':
                    self.handle_fetch()

        start_time = time.time()
        opportunities = self.arb_finder.find_opportunities(self.last_pools)
        scan_time = time.time() - start_time

        self.last_opportunities = opportunities

        # Log scan event and opportunities
        self.log_event('arb_check', {
            'opportunities_found': len(opportunities),
            'duration': scan_time
        })

        for opp in opportunities:
            self.log_event('opportunity', opp)

        if opportunities:
            self.arb_finder.display_opportunities(opportunities, limit=5)
        else:
            print(f"\n{Fore.YELLOW}No opportunities found.{Style.RESET_ALL}")

        print(f"\n{Fore.BLUE}Scan completed in {scan_time:.2f}s (instant - using cache){Style.RESET_ALL}")

    def handle_full(self):
        """Run full scan (fetch + find arbs)"""
        print(f"\n{Fore.CYAN}🔄 Running full scan...{Style.RESET_ALL}")

        start_time = time.time()

        # Step 1: Fetch pools
        self.handle_fetch()

        # Step 2: Find arbitrage
        opportunities = self.arb_finder.find_opportunities(self.last_pools)
        self.last_opportunities = opportunities

        # Log opportunities
        for opp in opportunities:
            self.log_event('opportunity', opp)

        full_time = time.time() - start_time

        if opportunities:
            self.arb_finder.display_opportunities(opportunities, limit=5)
        else:
            print(f"\n{Fore.YELLOW}No opportunities found.{Style.RESET_ALL}")

        print(f"\n{Fore.BLUE}Full scan completed in {full_time:.2f}s{Style.RESET_ALL}")
    
    def handle_auto(self):
        """Toggle automatic scanning"""
        self.auto_scan = not self.auto_scan

        if self.auto_scan:
            print(f"\n{Fore.GREEN}🔄 Automatic scanning ENABLED{Style.RESET_ALL}")
            print(f"  Scanning every 5 seconds...")
            print(f"  Type 'auto' again to stop")

            # Ask about auto-fetch on expire
            response = input(f"\n{Fore.YELLOW}Auto-fetch on cache expiry? (y/n): {Style.RESET_ALL}").strip().lower()
            self.auto_fetch_on_expire = (response == 'y')

            if self.auto_fetch_on_expire:
                print(f"{Fore.GREEN}✓ Will auto-fetch when cache expires{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠️  Will prompt before fetching{Style.RESET_ALL}")

            # Start auto scan in background
            thread = threading.Thread(target=self._auto_scan_loop, daemon=True)
            thread.start()
            return

        else:
            print(f"\n{Fore.YELLOW}🛑 Automatic scanning DISABLED{Style.RESET_ALL}")

    def _auto_scan_loop(self):
        """Background loop for automatic scanning"""
        while self.auto_scan:
            try:
                # Check cache expiration
                warning = self.cache.get_expiration_warning()
                if warning and self.auto_fetch_on_expire:
                    print(f"\n{Fore.YELLOW}⚠️  Cache expired, auto-fetching...{Style.RESET_ALL}")
                    self.handle_fetch()

                # Run scan
                self.handle_scan()
                time.sleep(5)
            except Exception as e:
                print(f"\n{Fore.RED}Auto-scan error: {e}{Style.RESET_ALL}")
                time.sleep(5)
    
    def handle_cache(self):
        """Check cache status"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"💾 CACHE STATUS")
        print(f"{'='*60}{Style.RESET_ALL}\n")

        status = self.cache.check_expiration_status()

        for cache_type, cache_status in status.items():
            if cache_status['entry_count'] == 0:
                continue

            expired = cache_status['expired']
            time_left = cache_status['time_remaining']
            percentage = cache_status['percentage_fresh']
            count = cache_status['entry_count']
            duration = cache_status['duration'] / 3600

            if expired:
                status_icon = f"{Fore.RED}❌ EXPIRED"
            elif time_left < 300:
                status_icon = f"{Fore.YELLOW}⚠️  EXPIRING SOON"
            else:
                status_icon = f"{Fore.GREEN}✅ FRESH"

            print(f"  {status_icon} {cache_type.upper()}{Style.RESET_ALL}")
            print(f"     Entries: {count} | Duration: {duration:.0f}h")

            if not expired:
                hours_left = time_left / 3600
                mins_left = (time_left % 3600) / 60
                print(f"     Time left: {hours_left:.0f}h {mins_left:.0f}m | Freshness: {percentage:.1f}%")

            print()

        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    def handle_status(self):
        """Show current status"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"         System Status")
        print(f"{'='*60}{Style.RESET_ALL}")

        print(f"  • Components: pool_data_fetcher + arb_finder")
        print(f"  • Auto-scan: {'ON' if self.auto_scan else 'OFF'}")
        print(f"  • Auto-fetch on expire: {'ON' if self.auto_fetch_on_expire else 'OFF'}")
        print(f"  • Last opportunities: {len(self.last_opportunities)}")
        print(f"  • Min TVL: $10,000")
        print(f"  • Min Profit: $1.00")

        # Cache status summary
        status = self.cache.check_expiration_status()
        pair_status = status.get('pair_prices', {})
        tvl_status = status.get('tvl_data', {})

        print(f"\n  {Fore.CYAN}Cache:{Style.RESET_ALL}")

        if pair_status.get('expired'):
            print(f"    • Pair prices: {Fore.RED}EXPIRED{Style.RESET_ALL}")
        else:
            time_left = pair_status.get('time_remaining', 0) / 60
            print(f"    • Pair prices: {Fore.GREEN}FRESH{Style.RESET_ALL} ({time_left:.0f}m left)")

        if tvl_status.get('expired'):
            print(f"    • TVL data: {Fore.RED}EXPIRED{Style.RESET_ALL}")
        else:
            time_left = tvl_status.get('time_remaining', 0) / 60
            print(f"    • TVL data: {Fore.GREEN}FRESH{Style.RESET_ALL} ({time_left:.0f}m left)")

        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    
    def handle_clear(self):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"\n{Fore.MAGENTA}{'='*60}")
        print(f"         🤖 ArbiGirl MEV Bot v5.0")
        print(f"{'='*60}{Style.RESET_ALL}\n")
        self._show_help()

    def handle_ask(self, question: str):
        """Ask ArbiGirl about operations"""
        if not question:
            print(f"{Fore.YELLOW}Usage: ask <question>{Style.RESET_ALL}")
            print(f"\nExamples:")
            print(f"  • ask what coins have been scanned?")
            print(f"  • ask what dexes have you checked?")
            print(f"  • ask show me the stats")
            print(f"  • ask how many opportunities found?")
            print(f"  • ask show cache activity")
            return

        print(f"\n{Fore.CYAN}🤖 ArbiGirl:{Style.RESET_ALL}")
        answer = self._query_ai(question)
        print(f"{answer}\n")

    def handle_run(self, filename: str):
        """Run a Python file and diagnose any errors"""
        if not filename:
            print(f"{Fore.YELLOW}Usage: run <file.py>{Style.RESET_ALL}")
            return

        if not filename.endswith('.py'):
            print(f"{Fore.YELLOW}File must be a Python file (.py){Style.RESET_ALL}")
            return

        import os
        if not os.path.exists(filename):
            print(f"{Fore.RED}File not found: {filename}{Style.RESET_ALL}")
            return

        print(f"\n{Fore.CYAN}🏃 Running {filename}...{Style.RESET_ALL}\n")

        try:
            result = subprocess.run(
                ['python', filename],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Show output
            if result.stdout:
                print(f"{Fore.GREEN}Output:{Style.RESET_ALL}")
                print(result.stdout)

            # Analyze errors
            if result.returncode != 0:
                print(f"\n{Fore.RED}❌ Error detected (exit code: {result.returncode}){Style.RESET_ALL}\n")

                if result.stderr:
                    print(f"{Fore.YELLOW}Error output:{Style.RESET_ALL}")
                    print(result.stderr)

                    # Diagnose common errors
                    stderr_lower = result.stderr.lower()

                    if 'modulenotfounderror' in stderr_lower or 'no module named' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Missing Python package{Style.RESET_ALL}")
                        print("   Fix: Install the missing package with pip install <package_name>")

                    elif 'syntaxerror' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Python syntax error{Style.RESET_ALL}")
                        print("   Fix: Check the line number in the error and correct the syntax")
                        # Extract line number if possible
                        import re
                        match = re.search(r'line (\d+)', result.stderr)
                        if match:
                            line_num = match.group(1)
                            print(f"   Error is on line {line_num}")

                    elif 'indentationerror' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Indentation error{Style.RESET_ALL}")
                        print("   Fix: Check that your indentation is consistent (use 4 spaces)")

                    elif 'importerror' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Import error{Style.RESET_ALL}")
                        print("   Fix: Check that the module exists and is in the correct location")

                    elif 'filenotfounderror' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Missing file{Style.RESET_ALL}")
                        print("   Fix: Check that all required files exist in the correct location")

                    elif 'keyerror' in stderr_lower or 'attributeerror' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Data access error{Style.RESET_ALL}")
                        print("   Fix: Check that you're accessing the correct keys/attributes")

                    elif 'typeerror' in stderr_lower:
                        print(f"\n{Fore.CYAN}💡 Diagnosis: Type mismatch{Style.RESET_ALL}")
                        print("   Fix: Check that you're using the correct data types")

                    else:
                        print(f"\n{Fore.CYAN}💡 General diagnosis:{Style.RESET_ALL}")
                        print("   Review the error message above for details")

            else:
                print(f"\n{Fore.GREEN}✅ File executed successfully!{Style.RESET_ALL}")

        except subprocess.TimeoutExpired:
            print(f"\n{Fore.RED}❌ Execution timeout (>30 seconds){Style.RESET_ALL}")
            print(f"{Fore.CYAN}💡 Diagnosis: Script is taking too long{Style.RESET_ALL}")
            print("   Fix: Check for infinite loops or long-running operations")

        except Exception as e:
            print(f"\n{Fore.RED}❌ Failed to run file: {e}{Style.RESET_ALL}")

    def run(self):
        say(f"{Fore.GREEN}Ready! Type commands or ask naturally.{Style.RESET_ALL}\n")

        while True:
            try:
                user_input = input(f"{Fore.MAGENTA}You> {Style.RESET_ALL}").strip()

                if not user_input:
                    continue

                action, params = parse_intent(user_input)

                command = user_input.lower().strip()

                if command in ['exit', 'quit', 'bye']:
                    print(f"\n{Fore.MAGENTA}👋 Goodbye!{Style.RESET_ALL}\n")
                    break
                elif command == 'fetch':
                    self.handle_fetch()
                elif command == 'scan':
                    self.handle_scan()
                elif command == 'full':
                    self.handle_full()
                elif command == 'auto':
                    self.handle_auto()
                elif command == 'cache':
                    self.handle_cache()
                elif command == 'status':
                    self.handle_status()
                elif command == 'clear':
                    self.handle_clear()
                elif command == 'help':
                    self._show_help()
                elif command.startswith('show '):
                    what = user_input[5:].strip()
                    self.handle_show(what)
                elif command == 'show':
                    self.handle_show('')
                elif command.startswith('ask '):
                    question = user_input[4:].strip()
                    self.handle_ask(question)
                elif command == 'ask':
                    self.handle_ask('')
                elif command.startswith('run '):
                    filename = user_input[4:].strip()
                    self.handle_run(filename)
                elif command == 'run':
                    self.handle_run('')
                else:
                    print(f"{Fore.YELLOW}Unknown command. Type 'help'{Style.RESET_ALL}")

            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Use 'exit' to quit{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
                import traceback
                traceback.print_exc()


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point"""
    try:
        # Check for required files
        required_files = ['price_data_fetcher.py', 'arb_finder.py', 'pool_registry.json', 'cache.py', 'rpc_mgr.py']
        missing = [f for f in required_files if not os.path.exists(f)]

        if missing:
            print(f"{Fore.RED}Missing required files:{Style.RESET_ALL}")
            for file in missing:
                print(f"  • {file}")
            print(f"\n{Fore.YELLOW}Please make sure all files are in the same directory!{Style.RESET_ALL}")
            return

        # Start ArbiGirl
        bot = ArbiGirl()
        bot.run()

    except Exception as e:
        print(f"{Fore.RED}Failed to start ArbiGirl: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
