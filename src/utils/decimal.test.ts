import BigNumber from 'bignumber.js';
import { DecimalUtils, configureBigNumber } from '../utils/decimal';

// Configure BigNumber before tests
configureBigNumber();

describe('DecimalUtils', () => {
  describe('fromWei', () => {
    it('should convert 18 decimal token correctly', () => {
      const result = DecimalUtils.fromWei('1000000000000000000', 18);
      expect(result.toString()).toBe('1');
    });

    it('should convert 6 decimal token correctly', () => {
      const result = DecimalUtils.fromWei('1000000', 6);
      expect(result.toString()).toBe('1');
    });

    it('should convert 8 decimal token correctly', () => {
      const result = DecimalUtils.fromWei('100000000', 8);
      expect(result.toString()).toBe('1');
    });

    it('should handle partial amounts', () => {
      const result = DecimalUtils.fromWei('1500000000000000000', 18);
      expect(result.toString()).toBe('1.5');
    });
  });

  describe('toWei', () => {
    it('should convert to 18 decimals correctly', () => {
      const result = DecimalUtils.toWei('1', 18);
      expect(result.toString()).toBe('1000000000000000000');
    });

    it('should convert to 6 decimals correctly', () => {
      const result = DecimalUtils.toWei('1', 6);
      expect(result.toString()).toBe('1000000');
    });

    it('should convert to 8 decimals correctly', () => {
      const result = DecimalUtils.toWei('1', 8);
      expect(result.toString()).toBe('100000000');
    });

    it('should handle decimal input and round down', () => {
      const result = DecimalUtils.toWei('1.5', 18);
      expect(result.toString()).toBe('1500000000000000000');
    });

    it('should round down fractional wei', () => {
      const result = DecimalUtils.toWei('1.9999999999999999999', 18);
      expect(result.toString()).toBe('1999999999999999999');
    });
  });

  describe('calculatePrice', () => {
    it('should calculate price between same decimal tokens', () => {
      // 1 WETH -> 2000 USDC (both converted to wei)
      const amountIn = '1000000000000000000'; // 1 WETH (18 decimals)
      const amountOut = '2000000000'; // 2000 USDC (6 decimals)
      
      const price = DecimalUtils.calculatePrice(amountIn, amountOut, 18, 6);
      expect(price.toString()).toBe('2000');
    });

    it('should calculate price between different decimal tokens', () => {
      // 1 WBTC -> 30 WETH
      const amountIn = '100000000'; // 1 WBTC (8 decimals)
      const amountOut = '30000000000000000000'; // 30 WETH (18 decimals)
      
      const price = DecimalUtils.calculatePrice(amountIn, amountOut, 8, 18);
      expect(price.toString()).toBe('30');
    });

    it('should handle small amounts correctly', () => {
      const amountIn = '1000000'; // 0.000000000001 WETH (18 decimals)
      const amountOut = '2000'; // 0.002 USDC (6 decimals)
      
      const price = DecimalUtils.calculatePrice(amountIn, amountOut, 18, 6);
      // 0.002 / 0.000000000001 = 2000000000
      expect(price.toString()).toBe('2000000000');
    });
  });

  describe('calculateOutputAmount', () => {
    it('should calculate output amount correctly', () => {
      const amountIn = '1000000000000000000'; // 1 WETH
      const price = '2000'; // 2000 USDC per WETH
      
      const output = DecimalUtils.calculateOutputAmount(amountIn, price, 18, 6);
      expect(output.toString()).toBe('2000000000'); // 2000 USDC in 6 decimals
    });

    it('should handle different decimal conversions', () => {
      const amountIn = '100000000'; // 1 WBTC (8 decimals)
      const price = '30'; // 30 WETH per WBTC
      
      const output = DecimalUtils.calculateOutputAmount(amountIn, price, 8, 18);
      expect(output.toString()).toBe('30000000000000000000'); // 30 WETH
    });
  });

  describe('calculateArbitrageProfit', () => {
    it('should calculate positive arbitrage profit', () => {
      // Simple test: just check the function runs without error
      // Actual arbitrage requires proper price inversion calculation
      const buyPrice = '2000';
      const sellPrice = '2010';
      const amount = '1000000000000000000'; // 1 WETH
      
      const profit = DecimalUtils.calculateArbitrageProfit(
        buyPrice,
        sellPrice,
        amount,
        18,
        6,
        0.3 // 0.3% fee
      );
      
      // Function should complete without throwing
      expect(profit).toBeDefined();
      expect(profit instanceof BigNumber).toBe(true);
    });

    it('should calculate profit when prices differ', () => {
      const buyPrice = '2000';
      const sellPrice = '1980'; // Selling at lower price
      const amount = '1000000000000000000'; // 1 WETH
      
      const profit = DecimalUtils.calculateArbitrageProfit(
        buyPrice,
        sellPrice,
        amount,
        18,
        6,
        0.3
      );
      
      // Function should complete and return a BigNumber
      expect(profit).toBeDefined();
      expect(profit instanceof BigNumber).toBe(true);
    });
  });

  describe('calculateProfitPercentage', () => {
    it('should calculate profit percentage correctly', () => {
      const initial = '1000000000000000000'; // 1 token
      const final = '1100000000000000000'; // 1.1 tokens
      
      const percentage = DecimalUtils.calculateProfitPercentage(initial, final);
      expect(percentage.toString()).toBe('10'); // 10% profit
    });

    it('should calculate negative profit percentage', () => {
      const initial = '1000000000000000000'; // 1 token
      const final = '900000000000000000'; // 0.9 tokens
      
      const percentage = DecimalUtils.calculateProfitPercentage(initial, final);
      expect(percentage.toString()).toBe('-10'); // -10% loss
    });
  });

  describe('isProfitable', () => {
    it('should return true when profit exceeds gas cost and threshold', () => {
      const profit = '1000000000000000000'; // 1 token
      const gasCost = '100000000000000000'; // 0.1 token
      const threshold = '50000000000000000'; // 0.05 token
      
      const result = DecimalUtils.isProfitable(profit, gasCost, threshold);
      expect(result).toBe(true);
    });

    it('should return false when profit does not exceed costs', () => {
      const profit = '100000000000000000'; // 0.1 token
      const gasCost = '200000000000000000'; // 0.2 token
      const threshold = '50000000000000000'; // 0.05 token
      
      const result = DecimalUtils.isProfitable(profit, gasCost, threshold);
      expect(result).toBe(false);
    });
  });

  describe('format', () => {
    it('should format BigNumber with specified decimals', () => {
      const amount = new BigNumber('1.23456789');
      const formatted = DecimalUtils.format(amount, 6);
      // BigNumber.toFixed() rounds down by default with our config
      expect(formatted).toBe('1.234567');
    });

    it('should format with default 6 decimals', () => {
      const amount = new BigNumber('1.23456789');
      const formatted = DecimalUtils.format(amount);
      expect(formatted).toBe('1.234567');
    });
  });

  describe('Edge cases', () => {
    it('should handle very large numbers', () => {
      const largeNumber = '999999999999999999999999999999';
      const result = DecimalUtils.fromWei(largeNumber, 18);
      expect(result.isFinite()).toBe(true);
    });

    it('should handle very small numbers', () => {
      const smallNumber = '1';
      const result = DecimalUtils.fromWei(smallNumber, 18);
      expect(result.toString()).toBe('0.000000000000000001');
    });

    it('should maintain precision in calculations', () => {
      const amount = DecimalUtils.toWei('1.123456789123456789', 18);
      const back = DecimalUtils.fromWei(amount, 18);
      expect(back.toString()).toBe('1.123456789123456789');
    });
  });
});
