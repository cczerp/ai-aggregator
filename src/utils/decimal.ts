import BigNumber from 'bignumber.js';

/**
 * Utility class for handling decimal conversions and arithmetic operations
 * with proper precision for token amounts and prices.
 */
export class DecimalUtils {
  /**
   * Convert a raw token amount (in smallest unit) to human-readable format
   * @param amount - Raw amount in smallest unit (e.g., wei for ETH)
   * @param decimals - Number of decimals for the token
   * @returns Human-readable amount as BigNumber
   */
  static fromWei(amount: string | number | BigNumber, decimals: number): BigNumber {
    const bn = new BigNumber(amount);
    return bn.dividedBy(new BigNumber(10).pow(decimals));
  }

  /**
   * Convert a human-readable amount to raw token amount (smallest unit)
   * @param amount - Human-readable amount
   * @param decimals - Number of decimals for the token
   * @returns Raw amount in smallest unit as BigNumber
   */
  static toWei(amount: string | number | BigNumber, decimals: number): BigNumber {
    const bn = new BigNumber(amount);
    return bn.multipliedBy(new BigNumber(10).pow(decimals)).integerValue(BigNumber.ROUND_DOWN);
  }

  /**
   * Calculate price with proper decimal adjustment
   * @param amountIn - Input amount (raw)
   * @param amountOut - Output amount (raw)
   * @param decimalsIn - Decimals of input token
   * @param decimalsOut - Decimals of output token
   * @returns Price as BigNumber (how much output per 1 unit of input)
   */
  static calculatePrice(
    amountIn: string | number | BigNumber,
    amountOut: string | number | BigNumber,
    decimalsIn: number,
    decimalsOut: number
  ): BigNumber {
    const readableIn = this.fromWei(amountIn, decimalsIn);
    const readableOut = this.fromWei(amountOut, decimalsOut);
    
    if (readableIn.isZero()) {
      throw new Error('Input amount cannot be zero');
    }
    
    return readableOut.dividedBy(readableIn);
  }

  /**
   * Calculate output amount given input amount and price
   * @param amountIn - Input amount (raw)
   * @param price - Price (output per unit input)
   * @param decimalsIn - Decimals of input token
   * @param decimalsOut - Decimals of output token
   * @returns Output amount (raw) as BigNumber
   */
  static calculateOutputAmount(
    amountIn: string | number | BigNumber,
    price: string | number | BigNumber,
    decimalsIn: number,
    decimalsOut: number
  ): BigNumber {
    const readableIn = this.fromWei(amountIn, decimalsIn);
    const pricebn = new BigNumber(price);
    const readableOut = readableIn.multipliedBy(pricebn);
    
    return this.toWei(readableOut, decimalsOut);
  }

  /**
   * Calculate arbitrage profit considering decimal differences
   * @param buyPrice - Price at which we buy (DEX1)
   * @param sellPrice - Price at which we sell (DEX2)
   * @param amount - Amount to trade (in input token, raw)
   * @param decimalsIn - Decimals of input token
   * @param decimalsOut - Decimals of output token
   * @param feePercentage - Trading fee as percentage (e.g., 0.3 for 0.3%)
   * @returns Profit in output token (raw) as BigNumber
   */
  static calculateArbitrageProfit(
    buyPrice: string | number | BigNumber,
    sellPrice: string | number | BigNumber,
    amount: string | number | BigNumber,
    decimalsIn: number,
    decimalsOut: number,
    feePercentage: number = 0.3
  ): BigNumber {
    const fee = new BigNumber(1).minus(new BigNumber(feePercentage).dividedBy(100));
    
    // Buy at DEX1: input -> output
    const amountAfterBuyFee = new BigNumber(amount).multipliedBy(fee);
    const outputFromBuy = this.calculateOutputAmount(amountAfterBuyFee, buyPrice, decimalsIn, decimalsOut);
    
    // Sell at DEX2: output -> input
    const amountAfterSellFee = outputFromBuy.multipliedBy(fee);
    const inverseSellPrice = new BigNumber(1).dividedBy(new BigNumber(sellPrice));
    const finalOutput = this.calculateOutputAmount(amountAfterSellFee, inverseSellPrice, decimalsOut, decimalsIn);
    
    // Profit is final - initial (both in input token decimals)
    return finalOutput.minus(new BigNumber(amount));
  }

  /**
   * Calculate profit percentage
   * @param initialAmount - Initial investment (raw)
   * @param finalAmount - Final amount after arbitrage (raw)
   * @returns Profit percentage as BigNumber
   */
  static calculateProfitPercentage(
    initialAmount: string | number | BigNumber,
    finalAmount: string | number | BigNumber
  ): BigNumber {
    const initial = new BigNumber(initialAmount);
    const final = new BigNumber(finalAmount);
    
    if (initial.isZero()) {
      throw new Error('Initial amount cannot be zero');
    }
    
    return final.minus(initial).dividedBy(initial).multipliedBy(100);
  }

  /**
   * Format BigNumber for display
   * @param amount - Amount as BigNumber
   * @param decimals - Number of decimal places to show
   * @returns Formatted string
   */
  static format(amount: BigNumber, decimals: number = 6): string {
    return amount.toFixed(decimals);
  }

  /**
   * Check if arbitrage is profitable after considering gas costs
   * @param profit - Profit amount (raw)
   * @param gasCost - Estimated gas cost in input token (raw)
   * @param minProfitThreshold - Minimum profit threshold (raw)
   * @returns True if profitable
   */
  static isProfitable(
    profit: string | number | BigNumber,
    gasCost: string | number | BigNumber,
    minProfitThreshold: string | number | BigNumber = 0
  ): boolean {
    const profitBN = new BigNumber(profit);
    const gasBN = new BigNumber(gasCost);
    const thresholdBN = new BigNumber(minProfitThreshold);
    
    const netProfit = profitBN.minus(gasBN);
    return netProfit.isGreaterThan(thresholdBN);
  }
}

/**
 * Configure BigNumber settings for consistent behavior
 */
export function configureBigNumber(): void {
  // Use high precision for intermediate calculations
  BigNumber.config({
    DECIMAL_PLACES: 36,
    ROUNDING_MODE: BigNumber.ROUND_DOWN,
    EXPONENTIAL_AT: [-30, 30],
  });
}
