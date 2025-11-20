# Quick Start - Graph Arbitrage Automation

**Simple 3-step setup - no sudo required!**

## TL;DR - Just Run It

```bash
# 1. Configure (one time only)
cp .env.example .env
# Edit .env: Add ALCHEMY_API_KEY, PRIVATE_KEY, CONTRACT_ADDRESS

# 2. Start automation (runs in background)
./start-automation.sh

# 3. Check status
./status-automation.sh

# 4. View logs
tail -f logs/automation-*.log

# 5. Stop it
./stop-automation.sh
```

## What It Does

**Automatically finds and executes arbitrage trades using:**
- ✅ **Graph pathfinding** - Multi-hop arbitrage paths (A→B→C→A)
- ✅ **Flash loans** - Zero capital risk (only gas costs)
- ✅ **Alchemy private bundles** - Prevents MEV attacks (automatic!)
- ✅ **Background execution** - Runs 24/7 (no sudo needed)

## Simple Configuration

Edit `.env` and set just these 4 things:

```bash
# Required
ALCHEMY_API_KEY=your_key_here        # Get from alchemy.com
PRIVATE_KEY=your_wallet_key_here     # Your wallet
CONTRACT_ADDRESS=your_contract_here  # Your flash loan contract

# Enable auto-execution?
AUTO_EXECUTE=true   # Set to "true" to auto-execute (or "false" to just watch)
```

**That's it!** Everything else has smart defaults.

## Does It Use Private Transactions?

**YES - Automatically!**

All transactions are sent via Alchemy's `eth_sendPrivateTransaction` by default. This prevents:
- Frontrunning
- Sandwich attacks
- MEV bots stealing your opportunities

No extra configuration needed - it just works!

## Will This Be Profitable?

**Honest answer:** Maybe not immediately. Here's why:

### Reality Check
- Arbitrage on Polygon is **highly competitive**
- Thousands of bots competing for same opportunities
- Profit margins are typically **0.1% - 0.5%**
- You need: Fast RPC, low latency, optimized code
- Gas costs eat into small profits

### What Makes This Bot Different
✅ **Graph method** - Finds multi-hop paths (A→B→C→A) others miss
✅ **Zero capital risk** - Flash loans mean you only spend gas
✅ **MEV protection** - Private transactions prevent frontrunning
✅ **Safety limits** - Won't drain your wallet on gas

### Recommended Approach

**Phase 1: Observe (1-2 days)**
```bash
AUTO_EXECUTE=false   # Just watch, don't execute
./start-automation.sh
tail -f logs/automation-*.log
```
Check the logs:
- Are opportunities showing up?
- What's the profit per opportunity?
- How often do they appear?

**Phase 2: Test Execute (2-3 days)**
```bash
AUTO_EXECUTE=true
MAX_GAS_SPENT_PER_HOUR=2.0   # Start low!
./start-automation.sh
```
Monitor:
- Success rate
- Actual profit vs expected
- Gas costs
- Net P&L

**Phase 3: Scale (if profitable)**
```bash
MAX_GAS_SPENT_PER_HOUR=5.0   # Increase gradually
MAX_TRADES_PER_MINUTE=10
```

### Expected Outcomes

**Realistic case:**
- Find 5-20 opportunities per day
- 10-30% success rate (competition is fierce)
- $0.50 - $5 profit per successful trade
- $10-50 per day IF conditions are good

**Pessimistic case:**
- Opportunities exist but too competitive
- High gas costs relative to profits
- Break even or small loss
- **Value is in learning the system**

**Optimistic case:**
- Graph method finds unique multi-hop paths
- Lower competition on 3+ hop trades
- $50-200 per day possible
- Requires optimization and monitoring

## Why Build This Then?

Even if not immediately profitable, you gain:
1. **Learning** - Understand MEV, arbitrage, graph theory
2. **Infrastructure** - Reusable code for other strategies
3. **Data** - Real market insights
4. **Foundation** - Basis for more advanced bots
5. **Zero risk** - Only losing gas, not capital

## Management Commands

```bash
./start-automation.sh    # Start in background
./stop-automation.sh     # Stop gracefully
./status-automation.sh   # Check if running
tail -f logs/*.log       # View logs
```

## Safety Features

Built-in protection:
- ✅ Kill switch after consecutive failures
- ✅ Maximum gas spending per hour
- ✅ Rate limiting (max trades per minute)
- ✅ Minimum profit requirements
- ✅ Cooldown between trades
- ✅ Flash loans auto-revert on failure

## Troubleshooting

**Not finding opportunities?**
- Lower `MIN_TVL_USD` to include more pools
- Adjust `BASE_TOKENS` for your market
- Increase `SCAN_INTERVAL_SECONDS` for thorough scanning

**Opportunities shown but execution fails?**
- Competition likely beat you to it
- Adjust `MAX_SLIPPAGE_PCT` if needed
- Consider faster RPC endpoint

**High gas costs?**
- Lower `MAX_TRADES_PER_MINUTE`
- Increase `MIN_PROFIT_AFTER_GAS`
- Decrease `MAX_GAS_SPENT_PER_HOUR`

## Advanced: Fine-Tuning

Once running, optimize by adjusting:

```bash
# Find more opportunities
BASE_TOKENS=USDC,WETH,WPOL,DAI,WMATIC,USDT
TEST_AMOUNTS=500,1000,5000,10000,20000
MIN_TVL_USD=2000

# Be more selective
MIN_PROFIT_AFTER_FEES=2.0
MIN_POOL_TVL=10000

# Trade more aggressively
MAX_TRADES_PER_MINUTE=20
OPTIMAL_TRADE_SIZE_USD=20000
```

## The Bottom Line

**Start with `AUTO_EXECUTE=false`** to observe first. If you see regular, profitable opportunities, enable auto-execution. Monitor closely for the first 48 hours.

This is a **learning tool and research platform** first, profitable bot second. The real value is understanding the system, not immediate profit.

Ready to try? Start with:
```bash
./start-automation.sh
```

Good luck! 🚀
