# Consolidated Arbitrage System

## Overview

The new consolidated arbitrage system brings together the best parts of `arb_scanner`, `pool_scanner`, and `optimized_price_engine` into a streamlined, AI-monitored architecture with clear separation of concerns.

## Architecture

### Core Components

1. **DataFetcher** (`arb_core.py`)
   - Fetches pool data from blockchain
   - Caches **pair prices** for **1 hour**
   - Caches **TVL data** for **3 hours**
   - Uses cache first, only fetches when expired

2. **ArbEngine** (`arb_core.py`)
   - Finds arbitrage opportunities from cached data
   - **Instant** - no blockchain calls, pure math
   - Repeatable - can scan as often as you want

3. **AIMonitor** (`arb_core.py`)
   - Tracks every call, calculation, and decision
   - Queryable by ArbiGirl
   - Stores operation history

4. **CacheManager** (`cache.py`)
   - Multi-duration cache system
   - Expiration warnings
   - Auto-fetch option

### Cache Durations

```python
'pair_prices': 1 hour    # Price data from pools
'tvl_data': 3 hours      # TVL/liquidity data
'pool_registry': 3 hours # Pool registry (TVL)
'oracle': 1 hour         # Oracle price feeds
```

## Workflow

### Standard Operation

1. **pool_data_fetcher** runs → fetches prices → caches:
   - Pair prices for **1 hour**
   - TVL prices for **3 hours**

2. **arb_scanner** runs → reads cache → does math → finds arbs
   - **Instant** (no blockchain calls)
   - Can repeat as often as you want

3. After 1hr/3hrs, caches expire:
   - System shows **expiration warning**
   - Option to **auto-fetch new data**
   - Or manually run `fetch` command

## Usage

### Using ArbiGirl CLI (Recommended)

```bash
python ai_bridge_v2.py
```

#### Available Commands

```
fetch        - Fetch fresh pool data (caches for 1hr/3hr)
scan         - Find arbitrage from cached data (instant)
full         - Run full scan (fetch + find arbs)
auto         - Toggle automatic scanning every 5s
ask <question> - Ask ArbiGirl about any operation
cache        - Check cache status and expiration
stats        - Show AI monitor statistics
status       - Show current status
help         - Show help
exit         - Exit ArbiGirl
```

#### Example Session

```bash
You> full
# Runs fetch + scan

You> scan
# Instant scan using cached data

You> scan
# Instant scan again (no fetch needed)

You> ask what coins were checked?
ArbiGirl: Tokens checked: USDC, WETH, WMATIC, ...

You> ask show me the latest opportunities
ArbiGirl: Latest opportunities:
1. USDC/WETH - $12.50 profit
   Buy: quickswap | Sell: sushiswap
...

You> cache
# Shows cache expiration status

You> auto
# Starts automatic scanning
Auto-fetch on cache expiry? (y/n): y
# Will automatically fetch fresh data when cache expires
```

### Using Programmatically

```python
from arb_core import ConsolidatedArbSystem

# Initialize
system = ConsolidatedArbSystem(
    min_tvl_usd=10000,
    min_profit_usd=1.0
)

# Option 1: Full scan (fetch + find arbs)
opportunities = system.run_full_scan()

# Option 2: Independent components
pools = system.fetch_pools()           # Caches for 1hr/3hr
opportunities = system.find_arbitrage(pools)  # Instant

# Option 3: Repeat instant scans
opportunities1 = system.find_arbitrage(pools)  # Instant
opportunities2 = system.find_arbitrage(pools)  # Instant (uses cache)

# Ask AI Monitor questions
answer = system.ask_arbigirl("what coins were checked?")
print(answer)

# Check cache status
status = system.check_cache_status()
print(status)

# Get AI stats
stats = system.get_ai_stats()
print(stats)
```

## AI Monitoring

### What Gets Tracked

- Every pool fetch (blockchain call)
- Every price calculation
- Every arbitrage check
- Every opportunity found
- All token and DEX interactions

### Queryable Information

Ask ArbiGirl natural language questions:

```python
"what was the last fetch?"
"how many opportunities found?"
"what coins/tokens were checked?"
"what dexes were used?"
"show me the latest opportunities"
"show stats"
```

## Cache Expiration Handling

### Automatic Warning

When cache expires, ArbiGirl will warn you:

```
⚠️  CACHE EXPIRATION WARNING
❌ PAIR_PRICES: EXPIRED (duration: 1h)
❌ TVL_DATA: EXPIRED (duration: 3h)

Data may be stale. Consider fetching fresh data.
```

### Auto-Fetch Option

Enable auto-fetch to automatically refresh data on expiry:

```bash
You> auto
Auto-fetch on cache expiry? (y/n): y
✓ Will auto-fetch fresh data when cache expires
```

### Manual Refresh

```bash
You> fetch
📡 Fetching fresh pool data...
✅ Fetch complete!
  • Pools fetched: 156
  • Time: 12.34s
  • Cached: Pair prices (1hr), TVL (3hr)
```

## Benefits of Consolidated System

### 1. Clear Rules
- Pair prices: 1 hour
- TVL data: 3 hours
- Always check cache first
- Warn on expiration

### 2. Independent Components
- Run fetch separately
- Run scan separately
- Run full scan together
- Any combination works

### 3. AI Monitoring
- Every operation is tracked
- Ask questions about anything
- Full transparency

### 4. Performance
- Fetch: ~10-15s (only when cache expired)
- Scan: **Instant** (pure math, no blockchain calls)
- Can scan hundreds of times without hitting RPCs

## Migration from Old System

### Old Way
```python
# arb_scanner.py
scanner = ArbScanner()
opportunities = scanner.scan_opportunities()  # Slow, fetches every time
```

### New Way
```python
# arb_core.py
system = ConsolidatedArbSystem()

# First run: fetch + scan (~15s)
opportunities = system.run_full_scan()

# Subsequent runs: instant
opportunities = system.find_arbitrage(pools)  # <1s
```

## File Structure

```
arb_core.py           # New consolidated core (USE THIS)
ai_bridge_v2.py       # New ArbiGirl CLI (USE THIS)
cache.py              # Updated with 1hr/3hr durations

# Legacy files (still functional but use new system instead)
arb_scanner.py        # Old scanner
pool_scanner.py       # Old pool scanner
optimized_price_engine.py  # Old price engine
ai_bridge.py          # Old ArbiGirl
```

## Configuration

### Minimum TVL
```python
system = ConsolidatedArbSystem(min_tvl_usd=10000)
```

### Minimum Profit
```python
system = ConsolidatedArbSystem(min_profit_usd=1.0)
```

### Cache Durations (in cache.py)
```python
'pair_prices': 1 * 3600,   # 1 hour
'tvl_data': 3 * 3600,      # 3 hours
```

## Troubleshooting

### Cache never expires?
Check system time and cache timestamps:
```python
status = system.check_cache_status()
print(status)
```

### No opportunities found?
1. Check if pools were fetched:
   ```bash
   You> fetch
   ```
2. Check cache status:
   ```bash
   You> cache
   ```
3. Ask AI:
   ```bash
   You> ask show stats
   ```

### RPCs failing?
ArbiGirl uses RPC manager with automatic failover. Check:
```python
from rpc_mgr import RPCManager
mgr = RPCManager()
health = mgr.health_check()
print(health)
```

## Performance Metrics

Typical performance on Polygon:

- **Fetch pools**: 10-15 seconds (300+ pools)
- **Find arbs**: <1 second (instant, using cache)
- **Full scan**: 10-15 seconds (fetch + arb)
- **Repeat scans**: <1 second each (uses cache)

## Best Practices

1. **Run fetch once**, scan many times:
   ```python
   pools = system.fetch_pools()  # Once
   for i in range(100):
       opportunities = system.find_arbitrage(pools)  # Instant
   ```

2. **Enable auto-fetch** for continuous operation:
   ```bash
   You> auto
   Auto-fetch on cache expiry? (y/n): y
   ```

3. **Ask AI** when you need information:
   ```bash
   You> ask what coins were checked?
   You> ask show me the latest opportunities
   ```

4. **Check cache status** regularly:
   ```bash
   You> cache
   ```

## Support

For issues or questions:
1. Check cache status: `cache` command
2. Check AI stats: `stats` command
3. Ask ArbiGirl: `ask <your question>`
4. Review logs in `arbigirl.log`
