# Simple Arbitrage System

Two focused files that work together:

## 1. pool_data_fetcher.py
**Purpose:** Fetches pool data and caches it
**Caches:** Pair prices (1hr), TVL data (3hr)
**Uses:** abis.py for all contract ABIs

```python
from pool_data_fetcher import PoolDataFetcher

fetcher = PoolDataFetcher(rpc_manager, cache, min_tvl_usd=10000)
pools = fetcher.fetch_all_pools()
```

## 2. arb_finder.py
**Purpose:** Finds arbitrage from cached data
**Speed:** Instant (no blockchain calls)
**Repeatable:** Yes - scan as many times as you want

```python
from arb_finder import ArbFinder

finder = ArbFinder(min_profit_usd=1.0)
opportunities = finder.find_opportunities(pools)
finder.display_opportunities(opportunities)
```

## Usage with ArbiGirl

```bash
python ai_bridge.py
```

### Commands:
- **fetch** - Fetch pool data (caches 1hr/3hr)
- **scan** - Find arbs from cache (instant)
- **full** - Run both (fetch + scan)
- **auto** - Auto-scan with cache expiration handling
- **cache** - Check cache status
- **status** - Show system status

## Workflow

### 1. Fetch Pools (run once)
```bash
You> fetch
```
→ Fetches prices → Caches **pair prices for 1hr** and **TVL for 3hr**

### 2. Find Arbitrage (instant, repeatable)
```bash
You> scan  # Instant
You> scan  # Instant again
You> scan  # As many times as you want
```
→ Reads cache → Does math → Finds arbs (< 1 second)

### 3. Cache Expiration
After 1hr (pair prices) or 3hr (TVL):
```
⚠️  CACHE WARNING:
❌ PAIR_PRICES: EXPIRED (duration: 1h)

Fetch fresh data? (y/n):
```

### 4. Auto-Scan
```bash
You> auto
Auto-fetch on cache expiry? (y/n): y
```
→ Scans every 5 seconds
→ Auto-fetches when cache expires
→ Seamless operation

## Rules

1. **Pair prices**: Always cached for **1 hour**
2. **TVL data**: Always cached for **3 hours**
3. **Fetch**: Only when cache expires
4. **Scan**: Instant, repeatable, uses cache
5. **ABIs**: All in abis.py

## Files

- `pool_data_fetcher.py` - Fetches and caches pool data
- `arb_finder.py` - Finds arbitrage from cache
- `ai_bridge.py` - ArbiGirl CLI (updated to use above)
- `cache.py` - Cache manager (1hr/3hr durations)
- `abis.py` - All contract ABIs

## Example Session

```bash
$ python ai_bridge.py

         🤖 ArbiGirl MEV Bot v5.0
         Run any component independently!

✓ ArbiGirl initialized successfully!
  • Pool Fetcher ready (caches: pair 1hr, TVL 3hr)
  • Arb Finder ready (instant scanning)

Available Commands:
  fetch      - Fetch pool data (caches 1hr/3hr)
  scan       - Find arbs from cache (instant)
  full       - Run full scan (fetch + find arbs)
  auto       - Start/stop automatic scanning
  cache      - Check cache status
  status     - Show current status
  clear      - Clear the screen
  help       - Show this help
  exit       - Exit ArbiGirl

You> full
📡 Fetching pool data...
[...]
✅ Fetch complete!
  • Pools fetched: 156
  • Time: 12.34s
  • Cached: Pair prices (1hr), TVL (3hr)

💰 Scanning for arbitrage (instant - using cached data)
[...]
✅ SCAN COMPLETE
   Pairs checked: 78
   Opportunities found: 3

💰 TOP ARBITRAGE OPPORTUNITIES

1. USDC/WETH
   Buy:  quickswap_v2 @ 0.00049800 (TVL: $2,500,000)
   Sell: sushiswap @ 0.00050100 (TVL: $1,800,000)
   Profit: $15.23 | ROI: 1.52% | Size: $10,000

[...]

Full scan completed in 13.2s

You> scan  # Instant - uses cache
💰 Scanning for arbitrage (using cache)...
[...]
Scan completed in 0.8s (instant - using cache)

You> scan  # Instant again
[...]
Scan completed in 0.7s (instant - using cache)

You> cache
💾 CACHE STATUS
  ✅ FRESH PAIR_PRICES
     Entries: 156 | Duration: 1h
     Time left: 0h 58m | Freshness: 96.7%

  ✅ FRESH TVL_DATA
     Entries: 156 | Duration: 3h
     Time left: 2h 58m | Freshness: 98.9%
```

## AI Integration (Separate)

AI monitoring is a separate concern. For AI integration, you can wrap these components with monitoring hooks to track operations.

## Benefits

✅ **Simple** - Two focused files, clear responsibilities
✅ **Fast** - Fetch once (~15s), scan infinite times (instant)
✅ **Clear Rules** - 1hr pair cache, 3hr TVL cache
✅ **Independent** - Run fetch separately, scan separately, or together
✅ **Repeatable** - Scan as many times as you want
✅ **Organized** - All ABIs in abis.py

## Performance

- **Fetch**: 10-15 seconds (300+ pools)
- **Scan**: <1 second (instant, using cache)
- **Full**: 10-15 seconds (fetch + scan)
- **Repeat scans**: <1 second each (uses cache)
