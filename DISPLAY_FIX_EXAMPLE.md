# Display Fix - Before & After

## Problem Fixed

The pair names in the registry didn't always match the actual token order from the blockchain, causing confusion when reading the spread percentages.

---

## BEFORE (Confusing ❌)

```
Venue/Tier                | Pair         | CG-T0        | CG-T1        | DEX Price    | ...
QuickSwap_V2              | QUICK/WETH   | $   3,098.32 | $       0.02 | 118407.30... | ...
```

**What you see:**
- Pair name: "QUICK/WETH" → You'd expect T0=QUICK, T1=WETH
- But CG-T0 shows WETH price ($3,098) 🤔
- And CG-T1 shows QUICK price ($0.02) 🤔
- **Very confusing!**

**What's actually happening:**
- The blockchain pool has token0=WETH, token1=QUICK (opposite of pair name!)
- DEX Quote 118,407 means: 1 WETH → 118,407 QUICK
- But the display made it look backwards

---

## AFTER (Clear ✅)

```
Venue/Tier                | Pair (T0/T1) | CG Price T0  | CG Price T1  | DEX Quote    | ...
Note: 'DEX Quote' shows how much T1 you get for 1 T0 (e.g., WETH/QUICK: 1 WETH → X QUICK)
------------------------------------------------------------------------------------------------
QuickSwap_V2              | WETH/QUICK   | $   3,098.32 | $       0.02 |  118407.30.. | ...
```

**What you see now:**
- Pair name: "WETH/QUICK" → Matches actual blockchain order ✅
- CG Price T0: $3,098 (WETH price) ✅
- CG Price T1: $0.02 (QUICK price) ✅
- DEX Quote: 118,407 = 1 WETH gives you 118,407 QUICK ✅
- **Crystal clear!**

---

## Changes Made

### 1. Use Actual Token Order (ai_bridge.py:804-805)
```python
# OLD: Used registry pair name (might be wrong)
'pair': pair_name

# NEW: Use actual blockchain token order
actual_pair_name = f"{token0}/{token1}"
'pair': actual_pair_name
```

### 2. Clearer Column Headers (ai_bridge.py:826)
```python
# OLD:
header = "... | Pair | CG-T0 | CG-T1 | DEX Price | ..."

# NEW:
header = "... | Pair (T0/T1) | CG Price T0 | CG Price T1 | DEX Quote | ..."
# Plus explanatory note below header
```

### 3. Updated Formatting (ai_bridge.py:850-860)
- Adjusted column widths for better alignment
- Added comment explaining pair name shows actual order

---

## Impact

### Example Pools That Will Change Display:

**QUICK/WETH** → **WETH/QUICK** (pool has WETH as token0)
**UNI/WETH** → **WETH/UNI** (pool has WETH as token0)
**USDC/WETH** → **WETH/USDC** (most pools have WETH as token0)

### Spreads Will Make Sense Now

**Before:**
```
QUICK/WETH | CG: $3,098/$0.02 | DEX: 118,407 | Spread: -40%
```
You'd think: "QUICK is 40% cheaper?" But the math doesn't work!

**After:**
```
WETH/QUICK | CG: $3,098/$0.02 | DEX: 118,407 | Spread: -23%
```
Now it's clear: Expected 154,900 QUICK per WETH, getting 118,407 → QUICK is ~23% cheaper ✅

---

## Bottom Line

✅ **Pair names now match actual blockchain token order**
✅ **Column headers clearly explain what each price means**
✅ **Spreads are now easy to understand**
✅ **No more confusion about which token is T0 vs T1**
