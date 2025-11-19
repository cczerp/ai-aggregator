# Large Spread Analysis Report

## Summary of Findings

I investigated the 3 pools with suspiciously large spreads between CoinGecko prices and DEX quotes.

---

## 1. WBTC/WETH: -25.27% Spread ⚠️  REAL ISSUE

### The Numbers:
- **CoinGecko Expected:** 1 WBTC = 29.75 WETH
  (Based on BTC=$92,178 / ETH=$3,098)
- **Polygon DEX Actual:** 1 WBTC = 22.23 WETH
- **Difference:** 7.52 WETH (~$23,297 USD)

### What This Means:
**The DEX is valuing WBTC 25% CHEAPER than expected!**

**Possible Explanations:**
1. **CoinGecko using wrong token prices**
   - CoinGecko ID "bitcoin" refers to native BTC (not WBTC)
   - WBTC on Polygon might trade at discount vs mainnet WBTC
   - **Should use**: `"WBTC": "wrapped-bitcoin"` instead of `"bitcoin"`

2. **Pool is imbalanced**
   - TVL is $548k (decent liquidity)
   - But pool might have too much WBTC, too little WETH
   - Causing WBTC to be "cheap" in that specific pool

3. **Bridge risk premium**
   - WBTC on Polygon = bridged asset
   - Might trade at 1-3% discount (NOT 25%!)

### Recommendation:
**Change CoinGecko mapping** from `"bitcoin"` to `"wrapped-bitcoin"` for better price accuracy.

---

## 2. QUICK/WETH: -40.62% Spread 🔴 DISPLAY BUG

### The Numbers (from your output):
- **Pair Name:** QUICK/WETH
- **CG-T0:** $3,098.32 (WETH price!)
- **CG-T1:** $0.02 (QUICK price!)
- **DEX Quote:** 118,407.308104

### The Problem:
**Token ordering mismatch!**

The pair name is `QUICK/WETH` but the actual pool has:
- **token0** = WETH (not QUICK!)
- **token1** = QUICK (not WETH!)

So the DEX quote means: **1 WETH = 118,407 QUICK** (not the other way around!)

### Why The Spread Shows Wrong:
The display is comparing:
- "QUICK/WETH" in the Pair column
- But showing WETH price in CG-T0 and QUICK price in CG-T1
- This confuses the user (makes it look inverted)

### Is There Really A Spread?
Let me calculate properly:
- Expected: $3,098 / $0.02 = 154,900 QUICK per WETH
- DEX Actual: 118,407 QUICK per WETH
- Real spread: **-23.5%** (QUICK is cheaper on DEX than CoinGecko thinks)

**This could be real!** QUICK is a low-volume token that might have stale CoinGecko prices.

---

## 3. UNI/WETH: -22.94% Spread 🔴 SAME ISSUE

### Same token ordering problem!
- Pair name says "UNI/WETH"
- But pool is actually WETH/UNI (token0=WETH, token1=UNI)
- DEX quote: 1 WETH = 324.39 UNI

### Real Spread Calculation:
- Expected: $3,098 / $7.36 = 420.9 UNI per WETH
- DEX Actual: 324.39 UNI per WETH
- Real spread: **-22.9%** (UNI is cheaper on DEX)

**Possible reasons:**
- CoinGecko price is stale
- Polygon UNI trades at discount vs mainnet
- Pool is imbalanced (unlikely with decent TVL)

---

## Root Causes Identified:

### 1. Wrong CoinGecko IDs ❌
```python
# Current (WRONG):
"WBTC": "bitcoin"  # This is native BTC, not wrapped BTC!

# Should be:
"WBTC": "wrapped-bitcoin"  # Correct WBTC token
```

### 2. Confusing Display Format ⚠️
The table shows:
```
QUICK/WETH | CG-T0: $3,098 | CG-T1: $0.02
```

But users expect:
- "QUICK/WETH" → T0=QUICK, T1=WETH
- Reality: T0=WETH, T1=QUICK (backwards!)

**Recommendation:** Either:
- A) Rename pairs to match actual token order (WETH/QUICK instead of QUICK/WETH)
- B) Add headers: "Token0/Token1" instead of assuming from pair name
- C) Always show token symbols in the table rows explicitly

### 3. CoinGecko Prices May Be Stale 📉
- QUICK, UNI prices might be from Ethereum mainnet
- Polygon versions might trade at different prices
- 5-minute cache might be too long for volatile tokens

---

## Recommendations:

### High Priority:
1. **Fix WBTC CoinGecko ID** → Use "wrapped-bitcoin" instead of "bitcoin"
2. **Standardize pair names** → Match registry names to actual token0/token1 order
3. **Add token symbols to display** → Show "1 WETH = X QUICK" instead of relying on pair name

### Medium Priority:
4. **Investigate if spreads are real arb opportunities** → 20-25% spreads could be profitable!
5. **Add pool balance ratio check** → Alert if pool is heavily imbalanced
6. **Consider using chain-specific CoinGecko prices** → "weth" on polygon vs "ethereum"

---

## Bottom Line:

✅ **Your on-chain data is accurate** - DEX quotes are real
⚠️ **CoinGecko mapping needs fixes** - Wrong IDs for wrapped tokens
❌ **Display is confusing** - Pair names don't match token order
🤔 **Some spreads might be real** - Worth investigating if 20-25% discounts are exploitable

The bot **won't accidentally take bad trades** because it uses on-chain quotes for execution, not CoinGecko prices. The spreads are just **display issues** that make it hard to assess opportunities visually.
