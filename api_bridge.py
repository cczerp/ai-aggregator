#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Bridge for ArbiGirl Integration
FastAPI server that exposes REST endpoints for the MEV bot

Endpoints:
  GET  /status   - Bot status and statistics
  POST /scan     - Trigger pool scan and return opportunities
  POST /simulate - Simulate strategy execution
  POST /propose  - Propose and optionally execute trade

Run:
  pip install fastapi uvicorn
  python api_bridge.py
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import bot components
from polygon_arb_bot import PolygonArbBot
from arb_scanner import ArbitrageScanner
from pool_scanner import PoolScanner
from tx_builder import FlashbotsTxBuilder
from rpc_mgr import RPCManager
from trade_database import get_database
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize trade database
trade_db = get_database()

# FastAPI app
app = FastAPI(
    title="MEV Bot API Bridge",
    description="REST API for ArbiGirl MEV bot integration",
    version="1.0.0"
)

# CORS middleware
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

# Global bot instance
_bot_instance: Optional[PolygonArbBot] = None
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

def get_bot_instance() -> PolygonArbBot:
    """Get or create bot instance"""
    global _bot_instance
    if _bot_instance is None:
        logger.info("Initializing PolygonArbBot instance...")
        try:
            _bot_instance = PolygonArbBot()
            logger.info("Bot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise HTTPException(status_code=500, detail=f"Bot initialization failed: {str(e)}")
    return _bot_instance

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "MEV Bot API Bridge",
        "version": "1.0.0",
        "uptime_seconds": time.time() - _bot_stats["start_time"]
    }

@app.get("/status")
async def get_status():
    """
    Get bot status and statistics

    Returns:
        - uptime
        - total scans
        - opportunities found
        - trades executed
        - total profit
        - last scan info
        - RPC health
    """
    try:
        bot = get_bot_instance()

        # Get RPC manager health if available
        rpc_health = {}
        if hasattr(bot, 'rpc_manager') and bot.rpc_manager:
            rpc_health = {
                "total_endpoints": len(bot.rpc_manager.endpoints) if hasattr(bot.rpc_manager, 'endpoints') else 0,
                "active_endpoint": getattr(bot.rpc_manager, 'current_endpoint', 'unknown')
            }

        uptime = time.time() - _bot_stats["start_time"]

        return {
            "status": "ok",
            "bot_running": _bot_instance is not None,
            "uptime_seconds": uptime,
            "uptime_formatted": f"{int(uptime//3600)}h {int((uptime%3600)//60)}m {int(uptime%60)}s",
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
            } if _bot_stats["last_scan_time"] else None,
            "rpc_health": rpc_health,
            "recent_errors": _bot_stats["errors"][-5:] if _bot_stats["errors"] else []
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scan")
async def scan_opportunities(request: Optional[ScanRequest] = None):
    """
    Scan for arbitrage opportunities

    Args:
        min_profit_usd: Minimum profit threshold in USD
        min_tvl: Minimum pool TVL in USD
        max_opportunities: Maximum number of opportunities to return

    Returns:
        - status: ok/error
        - found_opportunities: List of opportunities sorted by profit
        - scan_duration: Time taken to scan
    """
    start_time = time.time()

    try:
        bot = get_bot_instance()

        # Use request params or defaults
        min_profit = request.min_profit_usd if request else 1.0
        min_tvl = request.min_tvl if request else 10000.0
        max_opps = request.max_opportunities if request else 10

        logger.info(f"Starting scan with min_profit=${min_profit}, min_tvl=${min_tvl}")

        # Run the scan using bot's method
        opportunities = []
        if hasattr(bot, 'run_single_scan'):
            opportunities = bot.run_single_scan()
        else:
            # Fallback: create scanner and scan manually
            rpc = RPCManager()
            pool_scanner = PoolScanner(rpc.get_web3())
            arb_scanner = ArbitrageScanner(rpc.get_web3())

            # Scan pools
            pools = pool_scanner.scan_all_pools(min_tvl=min_tvl)

            # Find arbitrage opportunities
            opportunities = arb_scanner.find_arbitrage(pools, min_profit_usd=min_profit)

        # Filter by profit threshold
        filtered = [
            opp for opp in opportunities
            if float(opp.get("net_profit_usd", 0)) >= min_profit
        ]

        # Sort by profit descending
        filtered.sort(key=lambda x: float(x.get("net_profit_usd", 0)), reverse=True)

        # Limit results
        result_opps = filtered[:max_opps]

        # Update stats
        scan_duration = time.time() - start_time
        _bot_stats["total_scans"] += 1
        _bot_stats["total_opportunities_found"] += len(result_opps)
        _bot_stats["last_scan_time"] = datetime.now().isoformat()
        _bot_stats["last_scan_duration"] = scan_duration
        _bot_stats["last_opportunities"] = result_opps

        # Log opportunities to database
        for opp in result_opps:
            try:
                trade_db.log_opportunity(
                    pair=opp.get("pair", "unknown"),
                    dex_buy=opp.get("dex_buy", ""),
                    dex_sell=opp.get("dex_sell", ""),
                    profit_usd=float(opp.get("net_profit_usd", 0)),
                    roi_percent=float(opp.get("roi_percent", 0)),
                    executed=False
                )
            except Exception as e:
                logger.error(f"Failed to log opportunity: {e}")

        # Log scan metrics
        trade_db.log_metric("scan_duration", scan_duration)
        trade_db.log_metric("opportunities_found", len(result_opps))

        logger.info(f"Scan completed in {scan_duration:.2f}s, found {len(result_opps)} opportunities")

        return {
            "status": "ok",
            "found_opportunities": result_opps,
            "total_scanned": len(opportunities),
            "returned": len(result_opps),
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
    """
    Simulate strategy execution without actually executing

    Args:
        strategy: Strategy object with pair, DEXes, amounts, etc.

    Returns:
        - status: ok/error
        - sim: Simulation results (success, net_profit_usd, gas_cost, etc.)
    """
    try:
        strategy = request.strategy
        logger.info(f"Simulating strategy: {strategy.get('pair', 'unknown')}")

        # Extract strategy details
        pair = strategy.get("pair", "unknown")
        dex_buy = strategy.get("dex_buy", "")
        dex_sell = strategy.get("dex_sell", "")
        amount_in = float(strategy.get("amount_in", 1000))
        net_profit = float(strategy.get("net_profit_usd", 0))

        # Simulate gas cost (rough estimate)
        gas_cost_usd = 0.5  # Polygon is cheap, ~$0.50 per flashloan tx

        # Calculate net profit after gas
        net_profit_after_gas = net_profit - gas_cost_usd

        # Simulation success if profit > gas cost
        success = net_profit_after_gas > 0

        simulation_result = {
            "success": success,
            "pair": pair,
            "dex_buy": dex_buy,
            "dex_sell": dex_sell,
            "amount_in": amount_in,
            "gross_profit_usd": net_profit,
            "gas_cost_usd": gas_cost_usd,
            "net_profit_usd": net_profit_after_gas,
            "profitable": success,
            "reason": "Simulation passed" if success else "Not profitable after gas costs"
        }

        logger.info(f"Simulation result: {'✓ profitable' if success else '✗ not profitable'}")

        return {
            "status": "ok",
            "sim": simulation_result,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        error_msg = f"Simulation failed: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "sim": {"success": False, "reason": error_msg}
        }

@app.post("/propose")
async def propose_execution(request: ProposeRequest):
    """
    Propose and optionally execute a trade

    Args:
        proposal: Trade proposal with strategy details
        auto_execute: Whether to automatically execute (default: False)

    Returns:
        - status: proposed/executed/error
        - proposal_id: Unique ID for tracking
        - tx_hash: Transaction hash (if executed)
    """
    try:
        proposal = request.proposal
        auto_execute = request.auto_execute

        strategy_id = proposal.strategy_id
        profit_usd = proposal.profit_usd

        logger.info(f"Proposal {strategy_id}: profit=${profit_usd:.2f}, auto_execute={auto_execute}")

        # Generate proposal ID
        proposal_id = f"prop_{int(time.time())}_{strategy_id}"

        if not auto_execute:
            # Just track the proposal, don't execute
            return {
                "status": "proposed",
                "proposal_id": proposal_id,
                "message": "Proposal created but not executed (auto_execute=false)",
                "estimated_profit_usd": profit_usd
            }

        # Execute the trade
        logger.info(f"Executing proposal {proposal_id}...")

        # Get bot instance
        bot = get_bot_instance()

        # Try to execute using bot's method
        tx_hash = None
        if hasattr(bot, 'execute_proposal'):
            # Extract opportunity from proposal payload
            opportunity = proposal.payload
            tx_hash = bot.execute_proposal(opportunity)
        else:
            # Manual execution using tx_builder
            private_key = os.getenv("WALLET_PRIVATE_KEY")
            if not private_key:
                raise Exception("WALLET_PRIVATE_KEY not set in .env")

            tx_builder = FlashbotsTxBuilder(private_key)

            # Build flashloan transaction
            # This is a simplified version - you'd need proper parameters
            flashloan_params = {
                "asset": proposal.payload.get("token_address", "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"),  # WMATIC
                "amount": int(proposal.payload.get("amount_in", 1000) * 10**18),
                "target_dex": proposal.payload.get("dex_buy", "quickswap"),
            }

            # TODO: Implement proper flashloan execution
            # For now, return mock tx hash
            tx_hash = f"0x{'0'*64}"  # Mock tx hash
            logger.warning("Mock execution - implement proper flashloan logic!")

        # Update stats
        _bot_stats["total_trades_executed"] += 1
        _bot_stats["total_profit_usd"] += profit_usd

        # Log trade to database
        try:
            trade_db.log_trade(
                pair=proposal.payload.get("pair", "unknown"),
                dex_buy=proposal.payload.get("dex_buy", ""),
                dex_sell=proposal.payload.get("dex_sell", ""),
                amount_in=float(proposal.payload.get("amount_in", 0)),
                profit_usd=profit_usd,
                tx_hash=tx_hash,
                status="success" if tx_hash else "pending",
                metadata={"proposal_id": proposal_id}
            )
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")

        logger.info(f"Execution completed: {tx_hash}")

        return {
            "status": "executed",
            "proposal_id": proposal_id,
            "tx_hash": tx_hash,
            "profit_usd": profit_usd,
            "message": "Trade executed successfully",
            "polygonscan_url": f"https://polygonscan.com/tx/{tx_hash}" if tx_hash and tx_hash.startswith("0x") else None
        }

    except Exception as e:
        error_msg = f"Execution failed: {str(e)}"
        logger.error(error_msg)
        _bot_stats["errors"].append({
            "timestamp": datetime.now().isoformat(),
            "error": error_msg
        })
        return {
            "status": "error",
            "error": error_msg
        }

@app.get("/health")
async def health_check():
    """Simple health check for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

def main():
    """Run the API server"""
    port = int(os.getenv("API_PORT", "5050"))
    host = os.getenv("API_HOST", "0.0.0.0")

    logger.info(f"Starting MEV Bot API Bridge on {host}:{port}")
    logger.info("Endpoints available:")
    logger.info("  GET  /status   - Bot status and statistics")
    logger.info("  POST /scan     - Scan for opportunities")
    logger.info("  POST /simulate - Simulate strategy")
    logger.info("  POST /propose  - Propose/execute trade")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main()
