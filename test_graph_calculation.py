#!/usr/bin/env python3
"""
Diagnostic test for TVL filter and graph calculation fixes

This shows what the REAL issue is with graph profit calculation
"""

def test_broken_graph_calc():
    """Current BROKEN graph calculation"""
    print("\n" + "="*80)
    print("❌ CURRENT BROKEN GRAPH CALCULATION")
    print("="*80)

    # Path: USDC → WETH → WPOL → USDC
    # Real prices: USDC=$1, WETH=$2000, WPOL=$0.40

    amount_usd = 1000.0

    # Hop 1: USDC → WETH
    # Quote says: 1 USDC = 0.0005 WETH (normalized)
    exchange_rate_1 = 0.0005 * 0.997  # After 0.3% fee
    amount_usd *= exchange_rate_1
    print(f"Hop 1: USDC → WETH")
    print(f"  Exchange rate: {exchange_rate_1:.8f} WETH per USDC")
    print(f"  Amount: ${amount_usd:.2f}")
    print(f"  🔥 BUG: We're treating WETH amount (0.4985) as USD!")

    # Hop 2: WETH → WPOL
    # Quote says: 1 WETH = 5000 WPOL (normalized)
    exchange_rate_2 = 5000 * 0.997
    amount_usd *= exchange_rate_2
    print(f"\nHop 2: WETH → WPOL")
    print(f"  Exchange rate: {exchange_rate_2:.2f} WPOL per WETH")
    print(f"  Amount: ${amount_usd:.2f}")
    print(f"  🔥 BUG: We multiplied WPOL/WETH by USD - nonsense!")

    # Hop 3: WPOL → USDC
    # Quote says: 1 WPOL = 0.40 USDC (normalized)
    exchange_rate_3 = 0.40 * 0.997
    amount_usd *= exchange_rate_3
    print(f"\nHop 3: WPOL → USDC")
    print(f"  Exchange rate: {exchange_rate_3:.6f} USDC per WPOL")
    print(f"  Amount: ${amount_usd:.2f}")

    profit = amount_usd - 1000.0
    print(f"\n❌ Final: ${amount_usd:.2f} | Profit: ${profit:.2f}")
    print(f"🔥 This is WRONG because we mixed USD and token amounts!")


def test_fixed_graph_calc():
    """FIXED graph calculation - convert USD ↔ tokens at each hop"""
    print("\n" + "="*80)
    print("✅ FIXED GRAPH CALCULATION")
    print("="*80)

    # Path: USDC → WETH → WPOL → USDC
    # Real prices: USDC=$1, WETH=$2000, WPOL=$0.40

    prices = {
        "USDC": 1.0,
        "WETH": 2000.0,
        "WPOL": 0.40
    }

    amount_usd = 1000.0

    # Hop 1: USDC → WETH
    print(f"Hop 1: USDC → WETH")
    # Convert USD to USDC amount
    amount_usdc = amount_usd / prices["USDC"]
    print(f"  Start: ${amount_usd:.2f} = {amount_usdc:.2f} USDC")

    # Quote: 1 USDC = 0.0005 WETH
    exchange_rate = 0.0005 * 0.997  # After fee
    amount_weth = amount_usdc * exchange_rate
    print(f"  Exchange: 1 USDC = {exchange_rate:.8f} WETH")
    print(f"  Get: {amount_weth:.8f} WETH")

    # Convert WETH back to USD
    amount_usd = amount_weth * prices["WETH"]
    print(f"  End: {amount_weth:.8f} WETH = ${amount_usd:.2f}")

    # Hop 2: WETH → WPOL
    print(f"\nHop 2: WETH → WPOL")
    amount_weth_in = amount_usd / prices["WETH"]
    print(f"  Start: ${amount_usd:.2f} = {amount_weth_in:.8f} WETH")

    # Quote: 1 WETH = 5000 WPOL
    exchange_rate = 5000 * 0.997
    amount_wpol = amount_weth_in * exchange_rate
    print(f"  Exchange: 1 WETH = {exchange_rate:.2f} WPOL")
    print(f"  Get: {amount_wpol:.2f} WPOL")

    amount_usd = amount_wpol * prices["WPOL"]
    print(f"  End: {amount_wpol:.2f} WPOL = ${amount_usd:.2f}")

    # Hop 3: WPOL → USDC
    print(f"\nHop 3: WPOL → USDC")
    amount_wpol_in = amount_usd / prices["WPOL"]
    print(f"  Start: ${amount_usd:.2f} = {amount_wpol_in:.2f} WPOL")

    # Quote: 1 WPOL = 0.40 USDC
    exchange_rate = 0.40 * 0.997
    amount_usdc_out = amount_wpol_in * exchange_rate
    print(f"  Exchange: 1 WPOL = {exchange_rate:.6f} USDC")
    print(f"  Get: {amount_usdc_out:.2f} USDC")

    amount_usd = amount_usdc_out * prices["USDC"]
    print(f"  End: {amount_usdc_out:.2f} USDC = ${amount_usd:.2f}")

    profit = amount_usd - 1000.0
    roi = (profit / 1000.0) * 100
    print(f"\n✅ Final: ${amount_usd:.2f} | Profit: ${profit:.2f} ({roi:.2f}% ROI)")
    print(f"🎉 This correctly tracks token amounts and USD value!")


if __name__ == "__main__":
    test_broken_graph_calc()
    test_fixed_graph_calc()

    print("\n" + "="*80)
    print("💡 SOLUTION")
    print("="*80)
    print("""
The graph profit calculation needs to:
1. Store token prices in the graph (from derived_prices)
2. At each hop:
   a. Convert current USD → token_in amount
   b. Apply exchange rate to get token_out amount
   c. Convert token_out amount → USD
3. This properly tracks both token quantities AND USD value

Without proper USD conversion, all paths will show near-zero profit.
""")
