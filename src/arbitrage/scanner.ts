import BigNumber from 'bignumber.js';
import { IDex } from '../dex/interface';
import { Token, ArbitrageOpportunity, Price } from '../types';
import { DecimalUtils } from '../utils/decimal';

/**
 * Arbitrage scanner that finds profitable opportunities across DEXs
 */
export class ArbitrageScanner {
  private dexes: IDex[];
  private minProfitPercentage: number;

  constructor(dexes: IDex[], minProfitPercentage: number = 0.5) {
    this.dexes = dexes;
    this.minProfitPercentage = minProfitPercentage;
  }

  /**
   * Scan a token pair across all DEXs for arbitrage opportunities
   * This properly handles decimal conversions throughout the calculation
   */
  async scanPair(
    tokenA: Token,
    tokenB: Token,
    amountIn: BigNumber
  ): Promise<ArbitrageOpportunity | null> {
    try {
      // Get prices from all DEXs for both directions
      const pricesAtoB: Price[] = [];
      const pricesBtoA: Price[] = [];

      // Fetch all prices in parallel for efficiency
      const pricePromises = this.dexes.flatMap(dex => [
        dex.getPrice(tokenA, tokenB, amountIn),
        dex.getPrice(tokenB, tokenA, amountIn)
      ]);

      const allPrices = await Promise.allSettled(pricePromises);
      
      // Separate fulfilled prices
      for (let i = 0; i < allPrices.length; i += 2) {
        if (allPrices[i].status === 'fulfilled') {
          pricesAtoB.push((allPrices[i] as PromiseFulfilledResult<Price>).value);
        }
        if (allPrices[i + 1].status === 'fulfilled') {
          pricesBtoA.push((allPrices[i + 1] as PromiseFulfilledResult<Price>).value);
        }
      }

      if (pricesAtoB.length === 0 || pricesBtoA.length === 0) {
        return null;
      }

      // Find best buy and sell prices
      // Best buy: highest amountOut for given amountIn (best rate to get tokenB)
      const bestBuy = this.findBestPrice(pricesAtoB, true);
      
      // Best sell: highest amountOut for given amountIn (best rate to convert back to tokenA)
      const bestSell = this.findBestPrice(pricesBtoA, true);

      if (!bestBuy || !bestSell) {
        return null;
      }

      // Calculate arbitrage: A -> B on bestBuy DEX, then B -> A on bestSell DEX
      const profit = this.calculateArbitrageProfit(
        bestBuy,
        bestSell,
        amountIn,
        tokenA,
        tokenB
      );

      const profitPercentage = DecimalUtils.calculateProfitPercentage(amountIn, profit.finalAmount);

      // Check if profitable enough
      if (profitPercentage.isLessThan(this.minProfitPercentage)) {
        return null;
      }

      return {
        tokenA,
        tokenB,
        buyDex: bestBuy.dex,
        sellDex: bestSell.dex,
        buyPrice: bestBuy.price,
        sellPrice: bestSell.price,
        amountIn,
        expectedProfit: profit.finalAmount.minus(amountIn),
        profitPercentage,
        route: [bestBuy.dex, bestSell.dex]
      };
    } catch (error) {
      console.error(`Error scanning pair ${tokenA.symbol}/${tokenB.symbol}:`, error);
      return null;
    }
  }

  /**
   * Find the best price from a list of prices
   */
  private findBestPrice(prices: Price[], maximizeOutput: boolean): Price | null {
    if (prices.length === 0) return null;

    return prices.reduce((best, current) => {
      if (!best) return current;
      
      if (maximizeOutput) {
        // Want highest output amount
        return current.amountOut.isGreaterThan(best.amountOut) ? current : best;
      } else {
        // Want lowest price
        return current.price.isLessThan(best.price) ? current : best;
      }
    });
  }

  /**
   * Calculate actual arbitrage profit with proper decimal handling
   * Step 1: Trade tokenA -> tokenB on buyDex
   * Step 2: Trade tokenB -> tokenA on sellDex
   * Profit = final tokenA amount - initial tokenA amount
   */
  private calculateArbitrageProfit(
    buyPrice: Price,
    sellPrice: Price,
    initialAmount: BigNumber,
    tokenA: Token,
    tokenB: Token
  ): { finalAmount: BigNumber; tokenBAmount: BigNumber } {
    // Step 1: A -> B (use the amountOut from buyPrice directly as it includes fees)
    const tokenBAmount = buyPrice.amountOut;
    
    // Step 2: B -> A (calculate using sellPrice)
    // sellPrice is already B->A, so we can use it directly
    const finalAmount = DecimalUtils.calculateOutputAmount(
      tokenBAmount,
      sellPrice.price,
      tokenB.decimals,
      tokenA.decimals
    );
    
    // The sellPrice already includes the DEX fee calculation from getPrice()
    // So we don't need to apply it again here

    return {
      finalAmount,
      tokenBAmount
    };
  }

  /**
   * Scan multiple pairs for arbitrage opportunities
   */
  async scanPairs(
    pairs: Array<{ tokenA: Token; tokenB: Token }>,
    amountIn: BigNumber
  ): Promise<ArbitrageOpportunity[]> {
    const opportunities: ArbitrageOpportunity[] = [];

    // Scan pairs in batches to avoid overwhelming the system
    const batchSize = 10;
    for (let i = 0; i < pairs.length; i += batchSize) {
      const batch = pairs.slice(i, i + batchSize);
      const results = await Promise.allSettled(
        batch.map(pair => this.scanPair(pair.tokenA, pair.tokenB, amountIn))
      );

      for (const result of results) {
        if (result.status === 'fulfilled' && result.value) {
          opportunities.push(result.value);
        }
      }
    }

    // Sort by profit percentage descending
    return opportunities.sort((a, b) => 
      b.profitPercentage.minus(a.profitPercentage).toNumber()
    );
  }

  /**
   * Find the best arbitrage opportunity from a list
   */
  findBestOpportunity(opportunities: ArbitrageOpportunity[]): ArbitrageOpportunity | null {
    if (opportunities.length === 0) return null;
    
    // Already sorted by profit percentage, return the best one
    return opportunities[0];
  }
}
