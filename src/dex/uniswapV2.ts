import BigNumber from 'bignumber.js';
import { IDex } from './interface';
import { Token, Price, DexInfo } from '../types';
import { DecimalUtils } from '../utils/decimal';

/**
 * Uniswap V2 style DEX implementation
 * Supports Uniswap V2, SushiSwap, and other V2 clones
 */
export class UniswapV2Dex implements IDex {
  public name: string;
  private dexInfo: DexInfo;

  constructor(dexInfo: DexInfo) {
    this.dexInfo = dexInfo;
    this.name = dexInfo.name;
  }

  /**
   * Get price using constant product formula: x * y = k
   * Properly handles decimal conversions
   */
  async getPrice(tokenIn: Token, tokenOut: Token, amountIn: BigNumber): Promise<Price> {
    const [reserveIn, reserveOut] = await this.getReserves(tokenIn, tokenOut);
    
    // Calculate output using constant product formula
    // amountOut = (amountIn * (1 - fee) * reserveOut) / (reserveIn + amountIn * (1 - fee))
    const fee = new BigNumber(1).minus(new BigNumber(this.dexInfo.fee).dividedBy(100));
    const amountInWithFee = amountIn.multipliedBy(fee);
    
    const numerator = amountInWithFee.multipliedBy(reserveOut);
    const denominator = reserveIn.plus(amountInWithFee);
    const amountOut = numerator.dividedBy(denominator).integerValue(BigNumber.ROUND_DOWN);
    
    // Calculate price with proper decimal handling
    const price = DecimalUtils.calculatePrice(
      amountIn,
      amountOut,
      tokenIn.decimals,
      tokenOut.decimals
    );
    
    return {
      tokenIn,
      tokenOut,
      price,
      amountIn,
      amountOut,
      dex: this.name,
      timestamp: Date.now()
    };
  }

  /**
   * Get reserves from the DEX pair
   * In a real implementation, this would call the blockchain
   */
  async getReserves(tokenA: Token, tokenB: Token): Promise<[BigNumber, BigNumber]> {
    // Mock implementation - in production, this would call the pair contract
    // For now, return simulated reserves with proper decimals
    
    // Simulate reserves: tokenA reserve in its own decimals, tokenB in its own decimals
    const reserveA = DecimalUtils.toWei('1000', tokenA.decimals);
    const reserveB = DecimalUtils.toWei('2000', tokenB.decimals);
    
    return [reserveA, reserveB];
  }

  /**
   * Calculate optimal input amount for maximum profit
   * Uses quadratic formula to find optimal trade size
   */
  calculateOptimalInput(
    reserveIn: BigNumber,
    reserveOut: BigNumber,
    targetPrice: BigNumber,
    _decimalsIn: number,
    _decimalsOut: number
  ): BigNumber {
    // This is a simplified version - optimal input calculation
    // For real arbitrage, you'd use more sophisticated algorithms
    const fee = new BigNumber(1).minus(new BigNumber(this.dexInfo.fee).dividedBy(100));
    
    // Optimal input = (sqrt(reserveIn * reserveOut * targetPrice * fee) - reserveIn) / fee
    const sqrt = reserveIn
      .multipliedBy(reserveOut)
      .multipliedBy(targetPrice)
      .multipliedBy(fee)
      .sqrt();
    
    const optimal = sqrt.minus(reserveIn).dividedBy(fee);
    
    return optimal.integerValue(BigNumber.ROUND_DOWN);
  }
}
