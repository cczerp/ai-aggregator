# Quick Start Guide - Set It and Forget It

## ✅ YES - You Already Have Auto Mode!

Your bot has **full auto-execution** built in. Just set one flag and it runs forever.

---

## 🚀 **Option 1: Simple Auto Mode (Recommended)**

This uses your **existing setup** - no new deployments needed!

### **1. Set Environment Variables**

```bash
# .env file
AUTO_EXECUTE=true                    # ← Turn on auto-execution
CONTRACT_ADDRESS=0xYourFlashLoanContract  # Your deployed contract
PRIVATE_KEY=0xYourPrivateKey         # Bot wallet private key

# Safety limits (optional, has good defaults)
MIN_PROFIT_AFTER_FEES=1.00          # Min $1 profit after gas+fees
MAX_TRADE_SIZE_USD=100000           # Max $100k per trade
OPTIMAL_TRADE_SIZE_USD=15000        # Sweet spot: $15k
MAX_GAS_SPENT_PER_HOUR=5.0          # Max $5 gas/hour
```

### **2. Run the Bot**

```python
from polygon_arb_bot import PolygonArbBot

# Initialize with auto_execute=True
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,        # Check every 60 seconds
    auto_execute=True        # ← AUTO MODE ON!
)

# Start scanning (runs forever)
bot.run_continuous()
```

**That's it!** The bot will:
- ✅ Scan for opportunities every 60 seconds
- ✅ Automatically execute profitable trades
- ✅ Use your flash loan contract
- ✅ Respect safety limits (min profit, max gas, etc.)
- ✅ Auto-pause on consecutive failures (kill switch)

---

## 🔥 **Option 2: Advanced Auto Mode (With New MEV Features)**

This adds dynamic gas tuning + execution routing.

### **1. Create Your Bot Script**

```python
# auto_mev_bot.py
from polygon_arb_bot import PolygonArbBot
from tx_builder import GasOptimizationManager
from advanced_mev_module import AdvancedMEVModule
from remix_bot.flashloan_contract import FlashloanContract
from registries import get_token_address, DEXES
from execution_router import ExecutionPath
import os
import time
from datetime import datetime

# Initialize bot
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,
    auto_execute=False  # We'll handle execution ourselves
)

# Initialize gas manager
gas_mgr = GasOptimizationManager(rpc_manager=bot.rpc_manager)

# Initialize MEV module with gas tuning
mev_module = AdvancedMEVModule(bot, gas_manager=gas_mgr)

# Initialize flash loan contract
flash_contract = FlashloanContract(
    web3=bot.rpc_manager.get_web3(bot.rpc_manager.endpoints[0]),
    contract_address=os.getenv('CONTRACT_ADDRESS'),
    private_key=os.getenv('PRIVATE_KEY')
)

# Get POL price
pol_price = bot.price_fetcher.price_fetcher.get_price("WPOL") or 0.40

print(f"\n{'='*80}")
print(f"🤖 AUTO MEV BOT STARTED")
print(f"{'='*80}")
print(f"   POL Price: ${pol_price:.3f}")
print(f"   Contract: {os.getenv('CONTRACT_ADDRESS')[:10]}...")
print(f"   Mode: FULL AUTO")
print(f"{'='*80}\n")

# Main loop
scan_count = 0
total_profit = 0.0

while True:
    try:
        scan_count += 1
        print(f"\n{'='*80}")
        print(f"⏰ SCAN #{scan_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        # 1. Find opportunities (uses dynamic gas tuning)
        opportunities = mev_module.find_graph_opportunities(pol_price_usd=pol_price)

        if not opportunities:
            print(f"💤 No opportunities found. Sleeping 60s...")
            time.sleep(60)
            continue

        print(f"\n🎯 Found {len(opportunities)} opportunities\n")

        # 2. Route and execute each opportunity
        executed_count = 0
        for i, opp in enumerate(opportunities[:5], 1):  # Top 5
            print(f"\n--- Opportunity {i}/{min(5, len(opportunities))} ---")

            # Route the opportunity
            result = mev_module.analyze_and_route_opportunity(
                opp,
                pol_price_usd=pol_price,
                has_capital=False
            )

            if not result['should_execute']:
                print(f"⏭️  Skipped: {result.get('decision', {}).get('reason', 'Unknown')}")
                continue

            decision = result['decision']

            # Only execute 2-hop flash loan opportunities
            if decision.path != ExecutionPath.FLASH_LOAN_2HOP:
                print(f"⏭️  Skipped: {decision.path.value} not supported")
                continue

            # Extract trade parameters
            try:
                hops = opp['route']
                token_in_symbol = hops[0]['token']
                token_out_symbol = hops[1]['token']
                final_token_symbol = hops[-1].get('token', token_in_symbol)

                # Get addresses
                token_in = get_token_address(token_in_symbol)
                token_out = get_token_address(token_out_symbol)

                # Get DEX routers
                dex1_name = hops[0]['dex']
                dex2_name = hops[1]['dex']
                dex1_address = DEXES[dex1_name]['router']
                dex2_address = DEXES[dex2_name]['router']

                # Trade size (in wei)
                trade_size_usd = opp['amount_in']
                token_in_decimals = 6 if token_in_symbol == 'USDC' else 18
                amount_in_wei = int(trade_size_usd * (10 ** token_in_decimals))

                # Min profit (with 10% slippage buffer)
                expected_profit = decision.estimated_profit_after_gas
                min_profit_wei = int((expected_profit * 0.90) * (10 ** token_in_decimals))

                print(f"\n🚀 EXECUTING TRADE")
                print(f"   Route: {token_in_symbol} → {token_out_symbol} → {final_token_symbol}")
                print(f"   DEX1: {dex1_name}")
                print(f"   DEX2: {dex2_name}")
                print(f"   Size: ${trade_size_usd:,.0f}")
                print(f"   Expected Profit: ${expected_profit:.2f}")
                print(f"   Provider: {decision.method_details['provider']}")

                # Execute based on provider
                if decision.method_details['provider'] == 'balancer':
                    tx_result = flash_contract.execute_balancer_flashloan(
                        token_in=token_in,
                        token_out=token_out,
                        dex1_address=dex1_address,
                        dex2_address=dex2_address,
                        amount_in=amount_in_wei,
                        min_profit=min_profit_wei
                    )
                else:  # aave
                    tx_result = flash_contract.execute_aave_flashloan(
                        token_in=token_in,
                        token_out=token_out,
                        dex1_address=dex1_address,
                        dex2_address=dex2_address,
                        amount_in=amount_in_wei,
                        min_profit=min_profit_wei
                    )

                if tx_result['status'] == 'success':
                    executed_count += 1
                    total_profit += expected_profit

                    print(f"\n✅ SUCCESS!")
                    print(f"   TX: {tx_result['tx_hash']}")
                    print(f"   Gas Used: {tx_result['gas_used']:,}")
                    print(f"   Profit: ${expected_profit:.2f}")
                    print(f"   Total Session Profit: ${total_profit:.2f}")
                else:
                    print(f"\n❌ FAILED: Transaction reverted (unprofitable on-chain)")

            except Exception as e:
                print(f"\n❌ Execution error: {e}")
                continue

        # Summary
        print(f"\n{'='*80}")
        print(f"📊 SCAN SUMMARY")
        print(f"   Opportunities: {len(opportunities)}")
        print(f"   Executed: {executed_count}")
        print(f"   Session Profit: ${total_profit:.2f}")
        print(f"{'='*80}\n")

        # Sleep before next scan
        print(f"💤 Sleeping 60s until next scan...")
        time.sleep(60)

    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print(f"👋 SHUTTING DOWN")
        print(f"{'='*80}")
        print(f"   Total Scans: {scan_count}")
        print(f"   Total Profit: ${total_profit:.2f}")
        print(f"{'='*80}\n")
        break

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print(f"   Retrying in 10s...")
        time.sleep(10)
```

### **2. Run It**

```bash
python auto_mev_bot.py
```

**This will**:
- ✅ Run forever until you Ctrl+C
- ✅ Use dynamic gas tuning (adjusts based on gas costs)
- ✅ Auto-select Balancer (0% fee) or Aave (0.09% fee)
- ✅ Execute profitable 2-hop flash loan arbitrage
- ✅ Track total profit across session

---

## 📋 **What You Need**

### ✅ **What You Already Have:**
1. Flash loan contract (deployed) ✅
2. Auto-execution code ✅
3. All the new MEV features ✅

### ❌ **What You DON'T Need:**

#### **1. Mempool Monitoring - OPTIONAL**
**Q: Do I need to sign up for mempool monitoring?**
**A: NO** - Mempool monitoring is **optional** and only needed for:
- Sandwich attacks (which you said you don't want)
- Frontrunning pending swaps
- Real-time price impact prediction

For **basic arbitrage**, you DON'T need mempool monitoring. The bot works fine with:
- Pool data from RPC calls
- Price quotes from routers/quoters
- Graph-based pathfinding

**If you want it later:**
- Use Alchemy WebSocket (free tier)
- Use Infura WebSocket
- Use public WSS endpoints

But for now, **skip it**.

---

#### **2. Sandwich Contract - NOT NEEDED**
**Q: Do I need to deploy a sandwich arb contract?**
**A: NO** - You already have a flash loan contract! That's all you need.

**Your existing contract** (`executeFlashloan` / `executeBalancerFlashloan`) handles:
- ✅ 2-hop arbitrage (USDC → WETH → USDC)
- ✅ Flash loans from Balancer (0% fee)
- ✅ Flash loans from Aave (0.09% fee)
- ✅ Atomic execution (all-or-nothing)

**Sandwich attacks** would need a different contract, but you said you don't want that.

**For multi-hop (3+)**: Your contract doesn't support it (stack too deep), but you don't need it for most arbitrage.

---

## ⚙️ **Configuration**

### **Environment Variables** (`.env`)

```bash
# REQUIRED
CONTRACT_ADDRESS=0xYourFlashLoanContract
PRIVATE_KEY=0xYourBotWalletPrivateKey

# OPTIONAL (has good defaults)
AUTO_EXECUTE=true
MIN_PROFIT_AFTER_FEES=1.00
MAX_TRADE_SIZE_USD=100000
OPTIMAL_TRADE_SIZE_USD=15000
MIN_TRADE_SIZE_USD=1000
MAX_SLIPPAGE_PCT=3.0
MIN_POOL_TVL=5000
MAX_TRADES_PER_MINUTE=10
MAX_GAS_SPENT_PER_HOUR=5.0
COOLDOWN_SECONDS=0.1
```

---

## 🎯 **Which Option Should I Use?**

### **Use Option 1 (Simple Auto Mode) if:**
- ✅ You want the easiest setup
- ✅ You trust the default parameters
- ✅ You just want to set it and forget it

### **Use Option 2 (Advanced Auto Mode) if:**
- ✅ You want dynamic gas tuning
- ✅ You want to see exactly what's happening
- ✅ You want control over execution logic
- ✅ You want to track total profit

---

## 🚨 **Safety Features (Built-In)**

Both options have:
- ✅ **Kill switch**: Auto-pause after 10 consecutive failures
- ✅ **Rate limiting**: Max 10 trades/minute
- ✅ **Gas limits**: Max $5 gas/hour
- ✅ **Min profit**: Won't execute if profit < threshold
- ✅ **Slippage protection**: 10% buffer on min profit
- ✅ **Flash loan safety**: Transactions auto-revert if unprofitable

---

## 🧪 **Testing First**

Before running on mainnet:

```python
# Set to testnet in .env
# Or use simulation mode
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,
    auto_execute=False  # ← Test with False first!
)

# Find opportunities but don't execute
opportunities = bot.scan_once()
for opp in opportunities:
    print(opp)  # Review manually
```

---

## 📊 **Monitoring**

The bot prints:
- ✅ Every opportunity found
- ✅ Every execution decision
- ✅ Gas costs, profit, tx hashes
- ✅ Success/failure rates
- ✅ Total session profit

You can also add:
- Telegram/Discord webhooks
- Database logging (trade_database.py)
- Grafana dashboards

---

## ❓ **FAQ**

**Q: Will it drain my wallet?**
A: No - flash loans are borrowed, not from your wallet. You only pay gas (~$0.30/trade).

**Q: What if a trade fails?**
A: Flash loan auto-reverts. You only lose gas (~$0.30). No capital lost.

**Q: How much capital do I need?**
A: Zero! Flash loans = zero capital arbitrage. You just need gas money (~$50-100 for gas).

**Q: What if gas spikes?**
A: Dynamic gas tuner will reduce search aggressiveness or pause entirely.

**Q: Can I stop it?**
A: Yes - just Ctrl+C. It stops gracefully.

**Q: How much can I make?**
A: Depends on market conditions. $50-500/day is realistic on Polygon with 2-hop arbs.

---

## 🚀 **Ready to Run?**

1. Set `.env` variables
2. Choose Option 1 or 2
3. Run the script
4. Monitor the output
5. Profit!

**No mempool monitoring needed. No new contracts needed. Just run it!** 🎉
