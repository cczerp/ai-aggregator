#!/usr/bin/env python3
"""
Test script to demonstrate the TVL filter and price derivation fixes
Shows before/after behavior with mock pool data
"""

def test_old_tvl_logic():
    """OLD BROKEN LOGIC - TVL=0 pools pass through"""
    print("\n" + "="*80)
    print("❌ OLD BROKEN LOGIC")
    print("="*80)

    # Simulate a WPOL/USDC pool where WPOL has no CoinGecko price
    price0 = None  # WPOL price missing from CoinGecko
    price1 = 1.0   # USDC = $1

    reserve0 = 1000000 * (10**18)  # 1M WPOL
    reserve1 = 400000 * (10**6)    # 400K USDC
    decimals0 = 18
    decimals1 = 6
    min_tvl = 3000

    # OLD LOGIC:
    if not price0 or not price1:
        print(f"⚠️  No CoinGecko price for WPOL - setting TVL to $0")
        tvl_usd = 0
        # BUG: No TVL check here!
    else:
        amount0 = reserve0 / (10 ** decimals0)
        amount1 = reserve1 / (10 ** decimals1)
        tvl_usd = (amount0 * price0) + (amount1 * price1)

        if tvl_usd < min_tvl:
            print(f"❌ Pool rejected - TVL ${tvl_usd:,.0f} < ${min_tvl:,.0f}")
            return None

    print(f"✅ Pool ACCEPTED with TVL: ${tvl_usd:,.0f}")
    print(f"🔥 BUG: Pool with $0 TVL was accepted because check was in else block!")
    return {"tvl_usd": tvl_usd}


def test_new_tvl_logic():
    """NEW FIXED LOGIC - Derives price and always checks TVL"""
    print("\n" + "="*80)
    print("✅ NEW FIXED LOGIC")
    print("="*80)

    # Same pool: WPOL/USDC where WPOL has no CoinGecko price
    price0 = None  # WPOL price missing from CoinGecko
    price1 = 1.0   # USDC = $1

    reserve0 = 1000000 * (10**18)  # 1M WPOL
    reserve1 = 400000 * (10**6)    # 400K USDC
    decimals0 = 18
    decimals1 = 6
    min_tvl = 3000

    # Simulate on-chain quote: 1 WPOL → 0.40 USDC
    quote_0to1 = 400000  # 0.4 USDC in wei (6 decimals)
    quote_1to0 = 2500000000000000000  # 2.5 WPOL in wei (18 decimals)

    # NEW LOGIC - Step 1: Try to derive missing prices
    if not price0 and price1:
        # Derive WPOL price from quote
        price0 = (quote_0to1 / (10 ** decimals1)) * price1
        print(f"💡 Derived WPOL price from on-chain quote: ${price0:.6f}")
        print(f"   Formula: (quote / 10^decimals1) * price1")
        print(f"   = ({quote_0to1} / 10^{decimals1}) * ${price1}")
        print(f"   = {quote_0to1 / (10**decimals1)} * ${price1} = ${price0:.6f}")

    # NEW LOGIC - Step 2: Calculate TVL
    if price0 and price1:
        amount0 = reserve0 / (10 ** decimals0)
        amount1 = reserve1 / (10 ** decimals1)
        tvl_usd = (amount0 * price0) + (amount1 * price1)
        print(f"\n📊 TVL Calculation:")
        print(f"   Amount0: {amount0:,.0f} WPOL × ${price0:.6f} = ${amount0 * price0:,.0f}")
        print(f"   Amount1: {amount1:,.0f} USDC × ${price1:.6f} = ${amount1 * price1:,.0f}")
        print(f"   Total TVL: ${tvl_usd:,.0f}")
    else:
        print(f"❌ Cannot calculate TVL - missing prices")
        return None

    # NEW LOGIC - Step 3: ALWAYS check threshold
    if tvl_usd < min_tvl:
        print(f"\n❌ Pool rejected - TVL ${tvl_usd:,.0f} < ${min_tvl:,.0f}")
        return None

    print(f"\n✅ Pool ACCEPTED with TVL: ${tvl_usd:,.0f}")
    print(f"🎉 FIX: Price derived from on-chain quote, TVL calculated correctly!")
    return {"tvl_usd": tvl_usd}


def test_graph_profit_calculation():
    """Test graph profit calculation with actual quotes"""
    print("\n" + "="*80)
    print("🔺 GRAPH PROFIT CALCULATION TEST")
    print("="*80)

    # Path: USDC → WETH → WPOL → USDC
    # Starting amount: $1000

    print("\n--- OLD BROKEN LOGIC (just multiply by (1 - fee)) ---")
    amount = 1000.0
    fee = 0.003

    # Hop 1: USDC → WETH
    amount *= (1 - fee)
    print(f"Hop 1: USDC → WETH: ${amount:.2f} (just applied fee)")

    # Hop 2: WETH → WPOL
    amount *= (1 - fee)
    print(f"Hop 2: WETH → WPOL: ${amount:.2f} (just applied fee)")

    # Hop 3: WPOL → USDC
    amount *= (1 - fee)
    print(f"Hop 3: WPOL → USDC: ${amount:.2f} (just applied fee)")

    profit_old = amount - 1000.0
    print(f"\n❌ Final: ${amount:.2f} | Profit: ${profit_old:.2f}")
    print(f"🔥 BUG: Ignores actual exchange rates, always loses (1-fee)^3 ≈ 0.9%")

    print("\n--- NEW FIXED LOGIC (use actual quotes with decimals) ---")
    amount = 1000.0

    # Hop 1: USDC → WETH
    # Quote: 1 USDC (6 decimals) → 0.0005 WETH (18 decimals)
    quote1 = 500000000000000  # 0.0005 WETH in wei
    decimals_out1 = 18
    exchange_rate1 = (quote1 / (10 ** decimals_out1)) * (1 - fee)
    amount *= exchange_rate1
    print(f"Hop 1: USDC → WETH")
    print(f"  Quote: 1 USDC = {quote1 / (10**decimals_out1)} WETH")
    print(f"  Exchange rate (after fees): {exchange_rate1:.8f}")
    print(f"  Amount: ${amount:.2f}")

    # Hop 2: WETH → WPOL
    # Quote: 1 WETH (18 decimals) → 5000 WPOL (18 decimals)
    quote2 = 5000 * (10**18)  # 5000 WPOL in wei
    decimals_out2 = 18
    exchange_rate2 = (quote2 / (10 ** decimals_out2)) * (1 - fee)
    amount *= exchange_rate2
    print(f"\nHop 2: WETH → WPOL")
    print(f"  Quote: 1 WETH = {quote2 / (10**decimals_out2):.0f} WPOL")
    print(f"  Exchange rate (after fees): {exchange_rate2:.2f}")
    print(f"  Amount: ${amount:.2f}")

    # Hop 3: WPOL → USDC
    # Quote: 1 WPOL (18 decimals) → 0.40 USDC (6 decimals)
    quote3 = 400000  # 0.4 USDC in wei
    decimals_out3 = 6
    exchange_rate3 = (quote3 / (10 ** decimals_out3)) * (1 - fee)
    amount *= exchange_rate3
    print(f"\nHop 3: WPOL → USDC")
    print(f"  Quote: 1 WPOL = {quote3 / (10**decimals_out3):.2f} USDC")
    print(f"  Exchange rate (after fees): {exchange_rate3:.6f}")
    print(f"  Amount: ${amount:.2f}")

    profit_new = amount - 1000.0
    print(f"\n✅ Final: ${amount:.2f} | Profit: ${profit_new:.2f}")
    print(f"🎉 FIX: Uses actual quotes, can detect real arbitrage opportunities!")


def main():
    print("\n" + "="*80)
    print("🔬 TESTING TVL FILTER AND GRAPH CALCULATION FIXES")
    print("="*80)

    # Test 1: TVL filtering
    test_old_tvl_logic()
    test_new_tvl_logic()

    # Test 2: Graph profit calculation
    test_graph_profit_calculation()

    print("\n" + "="*80)
    print("📋 SUMMARY")
    print("="*80)
    print("""
✅ FIX #1: TVL Filter
   - BEFORE: Pools with missing CoinGecko prices got TVL=$0 and passed through
   - AFTER: Prices derived from on-chain quotes, TVL checked always

✅ FIX #2: WPOL Price Derivation
   - BEFORE: WPOL pools had no price → TVL=$0 → all rejected
   - AFTER: WPOL price derived from WPOL/USDC quote → valid TVL

✅ FIX #3: Graph Profit Calculation
   - BEFORE: Just multiplied by (1-fee), ignored actual exchange rates
   - AFTER: Uses actual quotes with decimal normalization

Expected Results on Real Data:
   - 10x more pools accepted (WPOL pools now have valid TVL)
   - Graph builds with 10x more edges
   - Cycles can actually detect profitable paths
""")


if __name__ == "__main__":
    main()
