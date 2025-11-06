import BigNumber from 'bignumber.js';
import { Token, Price } from '../types';

/**
 * Base interface for DEX integrations
 */
export interface IDex {
  name: string;
  
  /**
   * Get the price for a token pair
   * @param tokenIn - Input token
   * @param tokenOut - Output token
   * @param amountIn - Amount to trade (raw)
   * @returns Price information with decimal-adjusted calculations
   */
  getPrice(tokenIn: Token, tokenOut: Token, amountIn: BigNumber): Promise<Price>;
  
  /**
   * Get reserves for a pair (for AMM-based DEXs)
   * @param tokenA - First token
   * @param tokenB - Second token
   * @returns Reserves as [reserveA, reserveB] (raw amounts)
   */
  getReserves(tokenA: Token, tokenB: Token): Promise<[BigNumber, BigNumber]>;
}
