"""
Unit Tests for Arbitrage Math Calculations
Tests price calculations, slippage modeling, and profit calculations
"""

import unittest
from price_math import (
    calculate_v2_output_amount,
    calculate_v3_output_amount,
    get_price_from_v2_reserves,
    get_price_from_v3_sqrt_price
)
from arb_finder import ArbFinder


class TestV2Calculations(unittest.TestCase):
    """Test Uniswap V2 style constant product formula calculations"""

    def test_v2_output_basic(self):
        """Test basic V2 swap calculation"""
        # Pool: 1000 USDC / 1 WETH
        # Fee: 0.3% (30 bps)
        reserve_in = 1000 * 10**6  # 1000 USDC (6 decimals)
        reserve_out = 1 * 10**18   # 1 WETH (18 decimals)
        amount_in = 100 * 10**6    # 100 USDC
        fee_bps = 30

        amount_out = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, fee_bps)

        # With 100 USDC in, we should get approximately 0.09 WETH out
        # (less than 0.1 due to fees and slippage)
        expected_min = 0.08 * 10**18
        expected_max = 0.095 * 10**18

        self.assertGreater(amount_out, expected_min, "Output too low")
        self.assertLess(amount_out, expected_max, "Output too high")

    def test_v2_zero_amounts(self):
        """Test V2 with zero amounts"""
        self.assertEqual(calculate_v2_output_amount(0, 1000, 1000, 30), 0)
        self.assertEqual(calculate_v2_output_amount(100, 0, 1000, 30), 0)
        self.assertEqual(calculate_v2_output_amount(100, 1000, 0, 30), 0)

    def test_v2_fee_impact(self):
        """Test that higher fees reduce output"""
        reserve_in = 1000 * 10**6
        reserve_out = 1 * 10**18
        amount_in = 100 * 10**6

        # 0.3% fee
        output_low_fee = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, 30)

        # 1% fee
        output_high_fee = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, 100)

        self.assertGreater(output_low_fee, output_high_fee, "Lower fee should give more output")

    def test_v2_slippage_increases_with_size(self):
        """Test that larger trades have more slippage"""
        reserve_in = 1000 * 10**6  # 1000 USDC
        reserve_out = 1 * 10**18   # 1 WETH
        fee_bps = 30

        # Small trade: 10 USDC
        small_in = 10 * 10**6
        small_out = calculate_v2_output_amount(small_in, reserve_in, reserve_out, fee_bps)
        small_price = small_out / small_in

        # Large trade: 500 USDC
        large_in = 500 * 10**6
        large_out = calculate_v2_output_amount(large_in, reserve_in, reserve_out, fee_bps)
        large_price = large_out / large_in

        # Large trade should have worse price (more slippage)
        self.assertLess(large_price, small_price, "Larger trade should have worse price due to slippage")

    def test_v2_price_from_reserves(self):
        """Test price calculation from reserves"""
        # Pool: 1000 USDC / 1 WETH
        reserve0 = 1000 * 10**6  # USDC
        reserve1 = 1 * 10**18    # WETH
        decimals0 = 6
        decimals1 = 18

        price = get_price_from_v2_reserves(reserve0, reserve1, decimals0, decimals1)

        # Price of USDC in terms of WETH should be ~0.001
        # (1 USDC = 0.001 WETH, or 1000 USDC = 1 WETH)
        self.assertAlmostEqual(price, 0.001, places=6)


class TestV3Calculations(unittest.TestCase):
    """Test Uniswap V3 calculations"""

    def test_v3_price_from_sqrt_price(self):
        """Test V3 price calculation from sqrtPriceX96"""
        # For a USDC/WETH pool where 1 WETH = 2000 USDC
        # sqrtPrice = sqrt(price) * 2^96
        # price = (token1/token0) after decimal adjustment

        import math
        # Simple 1:1 pool to avoid decimal confusion
        price = 1.0
        sqrt_price_x96 = int(math.sqrt(price) * (2 ** 96))

        decimals0 = 18
        decimals1 = 18

        calculated_price = get_price_from_v3_sqrt_price(sqrt_price_x96, decimals0, decimals1)

        # Should be close to 1.0 for 1:1 pool
        self.assertAlmostEqual(calculated_price, price, places=6)

    def test_v3_zero_sqrt_price(self):
        """Test V3 with zero sqrt price"""
        self.assertEqual(get_price_from_v3_sqrt_price(0, 18, 18), 0.0)


class TestSlippageCalculations(unittest.TestCase):
    """Test slippage and price impact calculations"""

    def test_slippage_increases_with_trade_size(self):
        """Test that slippage increases with trade size in V2 pools"""
        # Create a mock V2 pool
        reserve_usdc = 100000 * 10**6  # 100k USDC
        reserve_weth = 50 * 10**18     # 50 WETH
        fee_bps = 30

        # Calculate slippage for different sizes
        sizes = [1000, 5000, 10000, 20000]  # USD amounts
        slippages = []

        for size_usd in sizes:
            amount_in = size_usd * 10**6  # Convert to USDC wei
            amount_out = calculate_v2_output_amount(amount_in, reserve_usdc, reserve_weth, fee_bps)

            # Expected output without slippage (using reserve ratio)
            expected_out = (amount_in / reserve_usdc) * reserve_weth

            # Slippage
            slippage = ((expected_out - amount_out) / expected_out) * 100
            slippages.append(slippage)

        # Each subsequent trade should have more slippage
        for i in range(len(slippages) - 1):
            self.assertGreater(slippages[i + 1], slippages[i],
                             f"Slippage should increase with trade size: {slippages}")


class TestArbitrageFinder(unittest.TestCase):
    """Test arbitrage finding logic"""

    def setUp(self):
        """Set up test fixtures"""
        self.finder = ArbFinder(min_profit_usd=1.0)

    def test_arb_finder_initialization(self):
        """Test that ArbFinder initializes correctly"""
        self.assertEqual(self.finder.min_profit_usd, 1.0)
        self.assertIsNotNone(self.finder.test_amounts_usd)
        self.assertIsNotNone(self.finder.dex_fees)

    def test_calculate_swap_output_with_mock_data(self):
        """Test swap calculation with mock pool data"""
        # Create mock V2 pool data
        mock_pool = {
            'pair_prices': {
                'type': 'v2',
                'token0': 'USDC',
                'token1': 'WETH',
                'decimals0': 6,
                'decimals1': 18,
                'quote_0to1': 500000000000000,  # 0.0005 WETH for 1 USDC
                'quote_1to0': 2000000000,       # 2000 USDC for 1 WETH
                'dex': 'quickswap_v2'
            },
            'tvl_data': {
                'reserve0': 100000 * 10**6,  # 100k USDC
                'reserve1': 50 * 10**18,     # 50 WETH
                'price0_usd': 1.0,           # 1 USDC = $1
                'price1_usd': 2000.0,        # 1 WETH = $2000
                'tvl_usd': 200000
            }
        }

        # Calculate swap: 1000 USD of USDC -> WETH
        result = self.finder.calculate_swap_output_with_slippage(
            mock_pool, 'USDC', 'WETH', 1000.0
        )

        self.assertIsNotNone(result, "Swap calculation should succeed")
        self.assertIn('amount_out_usd', result)
        self.assertIn('slippage_pct', result)

        # Output should be less than input due to fees and slippage
        self.assertLess(result['amount_out_usd'], 1000.0,
                       "Output should be less than input due to fees/slippage")

        # But not too much less (sanity check)
        # With 0.3% fee + slippage on 1% of pool, expect ~1-2% total loss
        self.assertGreater(result['amount_out_usd'], 980.0,
                          "Output shouldn't be drastically less for this trade size")

    def test_arbitrage_calculation_requires_two_pools(self):
        """Test that arbitrage requires at least 2 pools"""
        result = self.finder.calculate_arbitrage("USDC/WETH", [], 1000.0)
        self.assertIsNone(result, "Should return None with no pools")

        result = self.finder.calculate_arbitrage("USDC/WETH", [{'dex': 'test', 'pool_data': {}}], 1000.0)
        self.assertIsNone(result, "Should return None with only 1 pool")

    def test_get_pool_price_with_quotes(self):
        """Test pool price calculation using stored quotes"""
        mock_pool = {
            'pair_prices': {
                'quote_0to1': 2000 * 10**6,   # 1 WETH = 2000 USDC (in USDC decimals)
                'quote_1to0': 500000000000000,  # 1 USDC = 0.0005 WETH (in WETH decimals)
                'decimals0': 18,  # WETH
                'decimals1': 6,   # USDC
            }
        }

        price = self.finder.get_pool_price(mock_pool)
        self.assertIsNotNone(price, "Should calculate price from quotes")
        # Price should be reasonable (not 0, not extreme)
        self.assertGreater(price, 0)


class TestConstantProductFormula(unittest.TestCase):
    """Test the constant product formula x * y = k"""

    def test_constant_product_maintained(self):
        """Test that k = x * y is maintained after swap"""
        reserve_in = 1000 * 10**18
        reserve_out = 1000 * 10**18
        amount_in = 100 * 10**18
        fee_bps = 30

        # Calculate k before
        k_before = reserve_in * reserve_out

        # Calculate swap
        amount_out = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, fee_bps)

        # Calculate k after
        reserve_in_after = reserve_in + amount_in
        reserve_out_after = reserve_out - amount_out
        k_after = reserve_in_after * reserve_out_after

        # k should increase slightly due to fees staying in pool
        self.assertGreaterEqual(k_after, k_before,
                               "Constant product k should be maintained or increase (due to fees)")

    def test_multiple_swaps_increase_k(self):
        """Test that multiple swaps increase k due to accumulated fees"""
        reserve_in = 1000 * 10**18
        reserve_out = 1000 * 10**18
        fee_bps = 30

        k_initial = reserve_in * reserve_out

        # Perform multiple swaps
        for _ in range(10):
            amount_in = 10 * 10**18
            amount_out = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, fee_bps)
            reserve_in += amount_in
            reserve_out -= amount_out

        k_final = reserve_in * reserve_out

        # k should be higher after fees accumulate
        self.assertGreater(k_final, k_initial,
                          "k should increase from accumulated fees")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling"""

    def test_very_large_trade_relative_to_pool(self):
        """Test behavior with trade larger than pool liquidity"""
        reserve_in = 1000 * 10**6
        reserve_out = 1 * 10**18
        # Try to trade 10x the pool reserves
        amount_in = 10000 * 10**6
        fee_bps = 30

        amount_out = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, fee_bps)

        # Should still return a value (won't revert), but with massive slippage
        self.assertGreater(amount_out, 0)
        # Should be much less than reserve_out (massive slippage)
        self.assertLess(amount_out, reserve_out)

    def test_very_small_trade(self):
        """Test behavior with very small trade amounts"""
        reserve_in = 1000 * 10**18
        reserve_out = 1000 * 10**18
        amount_in = 1  # 1 wei
        fee_bps = 30

        amount_out = calculate_v2_output_amount(amount_in, reserve_in, reserve_out, fee_bps)

        # Should return 0 due to rounding (1 wei is too small)
        self.assertEqual(amount_out, 0)


def run_tests():
    """Run all tests and print results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestV2Calculations))
    suite.addTests(loader.loadTestsFromTestCase(TestV3Calculations))
    suite.addTests(loader.loadTestsFromTestCase(TestSlippageCalculations))
    suite.addTests(loader.loadTestsFromTestCase(TestArbitrageFinder))
    suite.addTests(loader.loadTestsFromTestCase(TestConstantProductFormula))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
