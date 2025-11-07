#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Bridge - Unified CLI for MEV Bot
Merges ArbiGirl and ai_bridge functionality
Supports both REST API mode and direct scanner mode

Features:
- OpenAI integration for natural language (optional)
- Keyword-based parsing (95% no API calls)
- REST API mode (connects to api_bridge.py server)
- Direct mode (uses scanner directly when API unavailable)
- Continuous scanning with auto-execution
- Status monitoring and control

Run:
  # Start API server first (recommended)
  python api_bridge.py

  # Then start CLI
  python ai_bridge.py
"""

import json
import time
import os
import sys
import threading
import logging
from typing import Any, Dict, Optional, Tuple

import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv

# Try to import scanner modules (for direct mode fallback)
try:
    from arb_scanner import ArbitrageScanner
    from pool_scanner import PoolScanner
    from rpc_mgr import RPCManager
    DIRECT_MODE_AVAILABLE = True
except ImportError:
    DIRECT_MODE_AVAILABLE = False

init(autoreset=True)
load_dotenv()

# Configuration
BRIDGE_URL = os.getenv("ARBIGIRL_BRIDGE_URL", "http://127.0.0.1:5050")
MODEL = os.getenv("ARBIGIRL_MODEL", "gpt-4o-mini")
MIN_PROFIT_USD = float(os.getenv("ARBIGIRL_MIN_PROFIT_USD", "1.0"))
AUTO_EXECUTE = os.getenv("ARBIGIRL_AUTO_EXECUTE", "false").lower() in ("1", "true", "yes", "y")
USE_API = os.getenv("USE_API_MODE", "true").lower() in ("1", "true", "yes", "y")

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


def say(text: str):
    """Print and log message"""
    print(text)
    logging.info(text)


def call_api(path: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call REST API endpoint"""
    url = BRIDGE_URL.rstrip("/") + path
    try:
        if method == "GET":
            r = requests.get(url, timeout=60)
        else:
            r = requests.post(url, json=payload or {}, timeout=300)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"status": "error", "error": "Request timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def parse_intent(user_input: str) -> Tuple[str, Dict[str, Any]]:
    """
    Fast keyword matching - NO OpenAI for 95% of commands
    Returns: (action, params)
    """
    low = user_input.lower().strip()

    # Status keywords
    if any(word in low for word in ["status", "how's", "whats up", "what's up", "health", "check"]):
        return "status", {}

    # Scan keywords
    if any(word in low for word in ["scan", "find", "search", "look for"]):
        min_profit = MIN_PROFIT_USD
        for word in low.split():
            if word.startswith("$"):
                try:
                    min_profit = float(word.replace("$", ""))
                except:
                    pass
        continuous = any(word in low for word in ["continuous", "keep", "auto", "loop"])
        return "scan", {"min_profit_usd": min_profit, "continuous": continuous}

    # Execute/Run keywords
    if any(word in low for word in ["execute", "run", "trade", "go", "do it"]):
        return "execute", {}

    # Simulate keywords
    if any(word in low for word in ["simulate", "dry run", "test", "try"]):
        return "simulate", {}

    # Stop keywords
    if any(word in low for word in ["stop", "pause", "halt"]):
        return "stop", {}

    # Help keywords
    if any(word in low for word in ["help", "commands", "?"]):
        return "help", {}

    # Quit/Exit keywords
    if any(word in low for word in ["quit", "exit", "bye"]):
        return "quit", {}

    # Default: assume status
    return "status", {}


class AIBridge:
    """Unified AI-powered MEV bot CLI"""

    def __init__(self):
        """Initialize bot"""
        print(f"\n{Fore.MAGENTA}{'=' * 60}")
        print(f"         🤖 AI Bridge MEV Bot v3.0")
        print(f"         Unified CLI - OpenAI + REST API + Direct Mode")
        print(f"{'=' * 60}{Style.RESET_ALL}\n")

        # Determine mode
        self.use_api = USE_API
        self.scanner = None
        self.pool_scanner = None
        self.api_available = False

        if self.use_api:
            # Try API mode first
            print(f"{Fore.CYAN}Checking API server at {BRIDGE_URL}...{Style.RESET_ALL}")
            try:
                resp = requests.get(f"{BRIDGE_URL}/", timeout=5)
                if resp.status_code == 200:
                    self.api_available = True
                    print(f"{Fore.GREEN}✓ API server connected!{Style.RESET_ALL}")
                    print(f"  Mode: REST API")
            except Exception as e:
                print(f"{Fore.YELLOW}⚠ Cannot connect to API: {e}{Style.RESET_ALL}")

        if not self.api_available:
            if DIRECT_MODE_AVAILABLE:
                print(f"{Fore.CYAN}Using direct scanner mode{Style.RESET_ALL}")
                try:
                    rpc = RPCManager()
                    self.pool_scanner = PoolScanner(rpc.get_web3())
                    self.scanner = ArbitrageScanner(rpc.get_web3())
                    print(f"{Fore.GREEN}✓ Direct scanner initialized!{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}✗ Scanner initialization failed: {e}{Style.RESET_ALL}")
                    sys.exit(1)
            else:
                print(f"{Fore.RED}✗ Neither API nor direct mode available!{Style.RESET_ALL}")
                print(f"  Start API server: python api_bridge.py")
                sys.exit(1)

        # State
        self.auto_scan = False
        self.last_opportunities = []

        print(f"\n{Fore.GREEN}✓ Bot initialized!{Style.RESET_ALL}")
        print(f"  • Auto-execute: {'ON' if AUTO_EXECUTE else 'OFF'}")
        print(f"  • Min profit: ${MIN_PROFIT_USD}")
        self._show_help()

    def _show_help(self):
        """Show available commands"""
        print(f"\n{Fore.CYAN}Available Commands:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}scan{Style.RESET_ALL}         - Run one scan")
        print(f"  {Fore.YELLOW}scan continuous{Style.RESET_ALL} - Start continuous scanning")
        print(f"  {Fore.YELLOW}status{Style.RESET_ALL}       - Show bot status")
        print(f"  {Fore.YELLOW}stop{Style.RESET_ALL}         - Stop continuous scanning")
        print(f"  {Fore.YELLOW}help{Style.RESET_ALL}         - Show this help")
        print(f"  {Fore.YELLOW}quit{Style.RESET_ALL}         - Exit")
        print(f"\n💡 Just type naturally! e.g. 'scan for opportunities', 'what's the status'")

    def scan_direct(self, min_profit: float = MIN_PROFIT_USD) -> Dict[str, Any]:
        """Scan using direct mode"""
        try:
            # Scan pools
            pools = self.pool_scanner.scan_all_pools(min_tvl=10000.0)

            # Find arbitrage
            opportunities = self.scanner.find_arbitrage(pools, min_profit_usd=min_profit)

            # Filter and sort
            filtered = [
                opp for opp in opportunities
                if float(opp.get("net_profit_usd", 0)) >= min_profit
            ]
            filtered.sort(key=lambda x: float(x.get("net_profit_usd", 0)), reverse=True)

            return {
                "status": "ok",
                "found_opportunities": filtered[:10],
                "total_scanned": len(opportunities)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def handle_scan(self, continuous: bool = False):
        """Run scan(s)"""
        if continuous:
            self.auto_scan = True
            say(f"\n{Fore.GREEN}🔄 Starting continuous scanning (every 60s){Style.RESET_ALL}")
            say(f"💡 Type 'stop' to exit continuous mode\n")

            thread = threading.Thread(target=self._auto_scan_loop)
            thread.daemon = True
            thread.start()
            return

        # Single scan
        say(f"\n{Fore.CYAN}🔍 Scanning for arbitrage opportunities...{Style.RESET_ALL}")
        say(f"⏳ This may take 2-5 minutes...\n")

        start_time = time.time()

        if self.api_available:
            result = call_api("/scan", method="POST", payload={"min_profit_usd": MIN_PROFIT_USD})
        else:
            result = self.scan_direct(MIN_PROFIT_USD)

        scan_time = time.time() - start_time

        if result.get("status") != "ok":
            say(f"{Fore.RED}✗ Scan failed: {result.get('error')}{Style.RESET_ALL}")
            return

        opportunities = result.get("found_opportunities", [])
        self.last_opportunities = opportunities

        if opportunities:
            say(f"{Fore.GREEN}✨ Found {len(opportunities)} opportunities!{Style.RESET_ALL}\n")
            for i, opp in enumerate(opportunities[:5], 1):
                pair = opp.get("pair", "unknown")
                profit = float(opp.get("net_profit_usd", 0))
                dex_buy = opp.get("dex_buy", "")
                dex_sell = opp.get("dex_sell", "")
                roi = float(opp.get("roi_percent", 0))

                say(f"  {i}. {Fore.YELLOW}{pair}{Style.RESET_ALL}")
                say(f"     Profit: ${profit:.2f} ({roi:.2f}%)")
                say(f"     Route: Buy on {dex_buy}, Sell on {dex_sell}")

            if len(opportunities) > 5:
                say(f"\n  ... and {len(opportunities) - 5} more")

            # Auto-execute best if enabled
            if AUTO_EXECUTE and opportunities:
                best = opportunities[0]
                say(f"\n{Fore.MAGENTA}🚀 Auto-execute enabled, executing best opportunity...{Style.RESET_ALL}")
                self.handle_execute(best)

        else:
            say(f"{Fore.YELLOW}No opportunities found (threshold: ${MIN_PROFIT_USD}){Style.RESET_ALL}")

        say(f"\n{Fore.BLUE}⏱️ Scan completed in {scan_time:.2f}s{Style.RESET_ALL}")

    def _auto_scan_loop(self):
        """Background continuous scanning"""
        while self.auto_scan:
            self.handle_scan(continuous=False)
            if self.auto_scan:  # Check if still enabled
                time.sleep(60)

    def handle_stop(self):
        """Stop continuous scanning"""
        if self.auto_scan:
            self.auto_scan = False
            say(f"\n{Fore.YELLOW}⏸️ Continuous scanning stopped{Style.RESET_ALL}")
        else:
            say(f"\n{Fore.CYAN}ℹ️ Not in continuous mode{Style.RESET_ALL}")

    def handle_status(self):
        """Show bot status"""
        say(f"\n{Fore.CYAN}{'=' * 40}")
        say(f"         Bot Status")
        say(f"{'=' * 40}{Style.RESET_ALL}")

        if self.api_available:
            result = call_api("/status")
            if result.get("status") == "ok":
                say(f"  Mode: REST API")
                say(f"  Uptime: {result.get('uptime_formatted', 'unknown')}")
                stats = result.get("statistics", {})
                say(f"  Total scans: {stats.get('total_scans', 0)}")
                say(f"  Opportunities found: {stats.get('total_opportunities_found', 0)}")
                say(f"  Trades executed: {stats.get('total_trades_executed', 0)}")
                say(f"  Total profit: ${stats.get('total_profit_usd', 0):.2f}")
            else:
                say(f"  {Fore.RED}API error: {result.get('error')}{Style.RESET_ALL}")
        else:
            say(f"  Mode: Direct Scanner")

        say(f"  Auto-scan: {'ON' if self.auto_scan else 'OFF'}")
        say(f"  Auto-execute: {'ON' if AUTO_EXECUTE else 'OFF'}")
        say(f"  Min profit: ${MIN_PROFIT_USD}")
        say(f"  Last scan: {len(self.last_opportunities)} opportunities")

    def handle_execute(self, opportunity: Dict[str, Any]):
        """Execute trade (placeholder)"""
        say(f"\n{Fore.MAGENTA}📝 Preparing trade execution...{Style.RESET_ALL}")

        # Simulate first
        if self.api_available:
            sim = call_api("/simulate", method="POST", payload={"strategy": opportunity})
            if sim.get("status") != "ok" or not sim.get("sim", {}).get("success", False):
                say(f"{Fore.RED}✗ Simulation failed: {sim.get('error')}{Style.RESET_ALL}")
                return

            say(f"{Fore.GREEN}✓ Simulation passed!{Style.RESET_ALL}")

            # Execute
            proposal = {
                "strategy_id": opportunity.get("id", f"auto-{int(time.time())}"),
                "summary": f"{opportunity.get('pair')} arbitrage",
                "profit_usd": float(opportunity.get("net_profit_usd", 0)),
                "payload": opportunity
            }

            exec_result = call_api("/propose", method="POST", payload={
                "proposal": proposal,
                "auto_execute": True
            })

            if exec_result.get("status") in ("executed", "ok"):
                tx_hash = exec_result.get("tx_hash")
                say(f"{Fore.GREEN}🎉 Trade executed!{Style.RESET_ALL}")
                if tx_hash and tx_hash.startswith("0x"):
                    say(f"TX: https://polygonscan.com/tx/{tx_hash}")
            else:
                say(f"{Fore.RED}✗ Execution failed: {exec_result.get('error')}{Style.RESET_ALL}")
        else:
            say(f"{Fore.YELLOW}⚠ Execution not available in direct mode{Style.RESET_ALL}")
            say(f"  Start API server to enable execution")

    def run(self):
        """Main command loop"""
        say(f"\n{Fore.GREEN}Ready! Type commands or ask naturally.{Style.RESET_ALL}\n")

        while True:
            try:
                user_input = input(f"{Fore.MAGENTA}You> {Style.RESET_ALL}").strip()

                if not user_input:
                    continue

                # Parse intent
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

                elif action == "execute":
                    if self.last_opportunities:
                        self.handle_execute(self.last_opportunities[0])
                    else:
                        say(f"{Fore.YELLOW}No opportunities to execute. Run a scan first.{Style.RESET_ALL}")

                else:
                    say(f"{Fore.YELLOW}Not sure what you mean. Type 'help' for commands.{Style.RESET_ALL}")

            except KeyboardInterrupt:
                say(f"\n{Fore.YELLOW}Use 'quit' to exit properly.{Style.RESET_ALL}")
            except Exception as e:
                say(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")


def main():
    """Entry point"""
    try:
        bot = AIBridge()
        bot.run()
    except Exception as e:
        print(f"{Fore.RED}Failed to start: {e}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    main()
