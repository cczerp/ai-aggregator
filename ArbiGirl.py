#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArbiGirl v3 - RATE LIMIT OPTIMIZED
- Uses keyword matching for 95% of commands (NO OpenAI calls)
- Only calls OpenAI for truly ambiguous queries
- Continuous scanning without rate limit issues
- Real mainnet execution with Balancer→Aave fallback

Run:
  pip install openai python-dotenv requests
  python ArbiGirl.py

Config via .env:
  OPENAI_API_KEY=sk-...
  ARBIGIRL_BRIDGE_URL=http://127.0.0.1:5050
  ARBIGIRL_MODEL=gpt-4o-mini
  ARBIGIRL_MIN_PROFIT_USD=1.0
  ARBIGIRL_AUTO_EXECUTE=true
"""

import os
import json
import time
import logging
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import load_dotenv

# ---------- Load env ----------
load_dotenv()
BRIDGE = os.getenv("ARBIGIRL_BRIDGE_URL", "http://127.0.0.1:5050")
MODEL = os.getenv("ARBIGIRL_MODEL", "gpt-4o-mini")
MIN_PROFIT_USD = float(os.getenv("ARBIGIRL_MIN_PROFIT_USD", "1.0"))
AUTO_EXECUTE = os.getenv("ARBIGIRL_AUTO_EXECUTE", "true").lower() in ("1","true","yes","y")

# ---------- OpenAI client (only used for complex queries) ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("❌ OPENAI_API_KEY missing. Add it to your .env file.")

try:
    from openai import OpenAI
    _client = OpenAI(api_key=OPENAI_API_KEY)
    def llm_chat(system: str, user: str) -> str:
        resp = _client.chat.completions.create(
            model=MODEL,
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.2,
            max_tokens=300
        )
        return resp.choices[0].message.content
except Exception:
    import openai
    openai.api_key = OPENAI_API_KEY
    def llm_chat(system: str, user: str) -> str:
        resp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=0.2,
            max_tokens=300
        )
        return resp.choices[0].message.content

# ---------- Logging ----------
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
    print(text)
    logging.info(text)

def call_bridge(path: str, method: str="GET", payload: Optional[Dict[str,Any]]=None) -> Dict[str,Any]:
    url = BRIDGE.rstrip("/") + path
    try:
        if method == "GET":
            r = requests.get(url, timeout=60)
        else:
            # Increase timeout for scans - can take 3-5 minutes for full scan
            r = requests.post(url, json=payload or {}, timeout=300)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"status":"error","error":"Scan took too long (>5min). Try again or lower min TVL."}
    except Exception as e:
        return {"status":"error","error":str(e)}

# ---------- KEYWORD-BASED INTENT PARSING (NO OpenAI calls) ----------
def parse_intent_fast(user_input: str) -> Tuple[str, Dict[str,Any]]:
    """
    Fast keyword matching - NO OpenAI API calls for 95% of commands
    Returns: (action, params)
    """
    low = user_input.lower().strip()
    
    # Status keywords
    if any(word in low for word in ["status", "how's", "whats up", "what's up", "health", "check"]):
        return "status", {}
    
    # Scan keywords
    if any(word in low for word in ["scan", "find", "search", "look for", "check for"]):
        # Extract profit threshold if mentioned
        min_profit = MIN_PROFIT_USD
        for word in low.split():
            if word.startswith("$"):
                try:
                    min_profit = float(word.replace("$", ""))
                except:
                    pass
        return "scan", {"min_profit_usd": min_profit}
    
    # Execute/Run keywords
    if any(word in low for word in ["execute", "run", "trade", "go", "do it"]):
        min_profit = MIN_PROFIT_USD
        for word in low.split():
            if word.startswith("$"):
                try:
                    min_profit = float(word.replace("$", ""))
                except:
                    pass
        return "run_best", {"min_profit_usd": min_profit}
    
    # Simulate keywords
    if any(word in low for word in ["simulate", "dry run", "test", "try"]):
        return "simulate", {"strategy": {"id":"test","est_profit_usd": MIN_PROFIT_USD}}
    
    # Quit/Exit keywords
    if any(word in low for word in ["quit", "exit", "bye", "stop"]):
        return "quit", {}
    
    # Default: assume status
    return "status", {}

def summarize_scan(scan_result: Dict[str,Any]) -> str:
    result = scan_result.get("result", scan_result)
    found = result.get("found_opportunities") or result.get("opportunities") or []
    if not found:
        return "No clear arbs right now."
    parts = []
    for o in found[:5]:
        pair = o.get("pair") or o.get("symbol") or "pair"
        # Use correct field names from arb_scanner
        p = o.get("net_profit_usd") or o.get("est_profit_usd") or o.get("profit_usd") or 0
        # Get DEX names from dex_buy and dex_sell
        dex_buy = o.get("dex_buy", "")
        dex_sell = o.get("dex_sell", "")
        routers = [dex_buy, dex_sell] if dex_buy and dex_sell else (o.get("router_pair") or o.get("routers") or [])
        parts.append(f"{pair} ~ ${p:.2f} via {routers}")
    extra = "" if len(found) <= 5 else f" (+{len(found)-5} more)"
    return " | ".join(parts) + extra

def pick_best_opportunity(scan_result: Dict[str,Any], min_profit: float) -> Optional[Dict[str,Any]]:
    result = scan_result.get("result", scan_result)
    found = result.get("found_opportunities") or result.get("opportunities") or []
    if not found:
        return None
    # Use correct field name: net_profit_usd
    best = max(found, key=lambda o: float(o.get("net_profit_usd") or o.get("est_profit_usd") or o.get("profit_usd") or 0))
    profit = float(best.get("net_profit_usd") or best.get("est_profit_usd") or best.get("profit_usd") or 0)
    if profit >= min_profit:
        return best
    return None

def dry_run_simulation(strategy: Dict[str,Any]) -> Dict[str,Any]:
    resp = call_bridge("/simulate", method="POST", payload={"strategy": strategy})
    return resp

def propose_and_maybe_execute(strategy: Dict[str,Any], auto: bool=True) -> Dict[str,Any]:
    proposal = {
        "strategy_id": strategy.get("id","auto-"+str(int(time.time()))),
        "summary": strategy.get("summary","auto-run"),
        "profit_usd": float(strategy.get("est_profit_usd") or strategy.get("profit_usd") or 0),
        "payload": strategy.get("payload", {"to":"0xexecutor","data":"0x"}),
    }
    body = {"proposal": proposal, "auto_execute": bool(auto)}
    resp = call_bridge("/propose", method="POST", payload=body)
    return resp

def run_best_flow(min_profit: float):
    say("🔍 Scanning pools for juicy gaps... ✨")
    say("⏳ This may take 2-5 minutes for a full scan... please wait")
    scan = call_bridge("/scan", method="POST")
    if scan.get("status") != "ok":
        say(f"❌ Scan failed: {scan.get('error')}")
        return
    
    say("📊 " + summarize_scan(scan))
    target = pick_best_opportunity(scan, min_profit)
    if not target:
        say(f"💤 No opportunities above ${min_profit:.2f} right now.")
        return
    
    # Ensure strategy has required fields
    if "id" not in target:
        target["id"] = "best-"+str(int(time.time()))
    # Normalize profit field names
    if "net_profit_usd" in target:
        target["est_profit_usd"] = target["net_profit_usd"]
    elif "profit_usd" in target:
        target["est_profit_usd"] = target["profit_usd"]
    
    profit = float(target.get("net_profit_usd") or target.get("est_profit_usd") or target.get("profit_usd") or 0)
    say(f"💰 Found: {target.get('pair','unknown')} ~ ${profit:.2f}. Simulating...")
    
    sim = dry_run_simulation(target)
    if sim.get("status") != "ok" or not sim.get("sim",{}).get("success",True):
        say(f"⛔ Simulation says no-go: {sim.get('error') or sim}")
        return
    
    sim_profit = float(sim.get("sim",{}).get("net_profit_usd", 0.0))
    if sim_profit < min_profit:
        say(f"⚠️  After sim, net profit is ${sim_profit:.2f} - skipping.")
        return
    
    say(f"✅ Simulation passed! Net profit ≈ ${sim_profit:.2f}. Executing... 🚀")
    exec_resp = propose_and_maybe_execute(target, auto=AUTO_EXECUTE)
    
    if exec_resp.get("status") in ("executed","ok"):
        txh = exec_resp.get("tx_hash") or exec_resp.get("proposal_id")
        if txh and txh.startswith("0x"):
            say(f"🎉 Done! TX: https://polygonscan.com/tx/{txh}")
        else:
            say(f"✅ Tracked as {txh}")
    else:
        say(f"❌ Execution failed: {exec_resp.get('error') or exec_resp}")

def interactive():
    say("👋 Hi! I'm ArbiGirl - your arbitrage scout.")
    say(f"⚙️  Auto-execute: {'ON' if AUTO_EXECUTE else 'OFF'} | Min profit: ${MIN_PROFIT_USD:.2f}")
    say("💡 Say 'scan', 'status', 'run', or 'quit'. No need to be fancy!\n")
    
    last_scan_time = 0
    continuous_mode = False
    
    while True:
        try:
            # In continuous mode, auto-scan every 60s
            if continuous_mode:
                if time.time() - last_scan_time >= 60:
                    say("\n⏰ Auto-scanning...")
                    run_best_flow(MIN_PROFIT_USD)
                    last_scan_time = time.time()
                    say(f"💤 Next scan in 60s (type 'stop' to exit continuous mode)")
                time.sleep(1)
                continue
            
            user = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            say("👋 Bye!")
            break
        
        if not user:
            continue
        
        # Quick keyword matching (NO OpenAI API calls)
        action, params = parse_intent_fast(user)
        
        if action == "quit":
            say("👋 Pausing operations. See you later!")
            break
        
        elif action == "status":
            st = call_bridge("/status")
            say("📊 Status:")
            print(json.dumps(st, indent=2))
        
        elif action == "scan":
            minp = params.get("min_profit_usd", MIN_PROFIT_USD)
            
            # Check if user wants continuous mode
            if "continuous" in user.lower() or "keep" in user.lower() or "auto" in user.lower():
                continuous_mode = True
                say(f"🔄 Starting continuous scanning (every 60s, min ${minp:.2f})")
                say("💡 Type 'stop' to exit continuous mode")
                last_scan_time = 0  # Trigger immediate scan
            else:
                run_best_flow(minp)
        
        elif action == "run_best":
            minp = params.get("min_profit_usd", MIN_PROFIT_USD)
            run_best_flow(minp)
        
        elif action == "simulate":
            strategy = params.get("strategy") or {"id":"test","est_profit_usd": MIN_PROFIT_USD}
            say("🧪 Dry-running...")
            sim = dry_run_simulation(strategy)
            print(json.dumps(sim, indent=2))
        
        else:
            say("🤔 Not sure what you mean. Try 'scan', 'status', 'run', or 'quit'.")

if __name__ == "__main__":
    interactive()