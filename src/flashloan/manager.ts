import BigNumber from 'bignumber.js';
import { FlashloanProvider, FlashloanParams, Token, ArbitrageOpportunity } from '../types';
import { DecimalUtils } from '../utils/decimal';
import { FLASHLOAN_PROVIDERS } from '../config';

/**
 * Flashloan manager that selects the cheapest provider and calculates costs
 */
export class FlashloanManager {
  /**
   * Calculate flashloan cost for a given provider and amount
   * Returns the fee amount in the same token (raw amount)
   */
  static calculateFlashloanCost(
    amount: BigNumber,
    provider: FlashloanProvider
  ): BigNumber {
    const feePercentage = new BigNumber(provider.feePercentage).dividedBy(100);
    return amount.multipliedBy(feePercentage).integerValue(BigNumber.ROUND_UP);
  }

  /**
   * Select the cheapest flashloan provider for a given amount
   * Balancer typically has no fee (0%), Aave has 0.09%
   */
  static selectCheapestProvider(
    token: Token,
    amount: BigNumber
  ): FlashloanParams {
    const providers = Object.values(FLASHLOAN_PROVIDERS);
    
    let cheapestProvider = providers[0];
    let lowestCost = this.calculateFlashloanCost(amount, providers[0]);

    for (const provider of providers.slice(1)) {
      const cost = this.calculateFlashloanCost(amount, provider);
      if (cost.isLessThan(lowestCost)) {
        lowestCost = cost;
        cheapestProvider = provider;
      }
    }

    return {
      token,
      amount,
      provider: cheapestProvider,
      estimatedCost: lowestCost
    };
  }

  /**
   * Calculate net profit after flashloan fees
   */
  static calculateNetProfit(
    grossProfit: BigNumber,
    flashloanCost: BigNumber,
    gasCost: BigNumber
  ): BigNumber {
    return grossProfit.minus(flashloanCost).minus(gasCost);
  }

  /**
   * Determine if arbitrage is profitable after all costs
   */
  static isProfitableAfterCosts(
    opportunity: ArbitrageOpportunity,
    gasCostInTokenA: BigNumber,
    minProfitThreshold: BigNumber
  ): { profitable: boolean; netProfit: BigNumber; flashloanParams: FlashloanParams } {
    // Select cheapest flashloan provider
    const flashloanParams = this.selectCheapestProvider(
      opportunity.tokenA,
      opportunity.amountIn
    );

    // Calculate net profit
    const netProfit = this.calculateNetProfit(
      opportunity.expectedProfit,
      flashloanParams.estimatedCost,
      gasCostInTokenA
    );

    const profitable = netProfit.isGreaterThan(minProfitThreshold);

    return {
      profitable,
      netProfit,
      flashloanParams
    };
  }

  /**
   * Format flashloan parameters for execution
   * In a real implementation, this would encode the calldata for the flashloan
   */
  static prepareFlashloanExecution(
    params: FlashloanParams,
    opportunity: ArbitrageOpportunity
  ): {
    provider: string;
    token: string;
    amount: string;
    fee: string;
    calldata: string;
  } {
    return {
      provider: params.provider.name,
      token: params.token.address,
      amount: params.amount.toFixed(0),
      fee: params.estimatedCost.toFixed(0),
      calldata: this.encodeArbitrageCalldata(opportunity, params)
    };
  }

  /**
   * Encode the arbitrage execution calldata
   * This would be the actual trades to execute during the flashloan callback
   */
  private static encodeArbitrageCalldata(
    opportunity: ArbitrageOpportunity,
    params: FlashloanParams
  ): string {
    // In a real implementation, this would use ethers.js to encode the function calls
    // For now, return a placeholder that represents the trade path
    const data = {
      step1: {
        dex: opportunity.buyDex,
        tokenIn: opportunity.tokenA.address,
        tokenOut: opportunity.tokenB.address,
        amountIn: params.amount.toFixed(0)
      },
      step2: {
        dex: opportunity.sellDex,
        tokenIn: opportunity.tokenB.address,
        tokenOut: opportunity.tokenA.address,
        amountIn: 'calculated_from_step1'
      },
      repayAmount: params.amount.plus(params.estimatedCost).toFixed(0)
    };

    // This would be actual encoded calldata in production
    return JSON.stringify(data);
  }

  /**
   * Estimate gas cost for the arbitrage transaction
   * Returns estimated cost in the input token (raw amount)
   */
  static estimateGasCost(
    gasPrice: BigNumber,
    tokenPrice: BigNumber,
    tokenDecimals: number
  ): BigNumber {
    // Estimate ~300k gas for a typical flashloan arbitrage
    const estimatedGas = new BigNumber(300000);
    
    // Gas cost in ETH (wei)
    const gasCostWei = estimatedGas.multipliedBy(gasPrice);
    
    // Convert to human readable ETH
    const gasCostETH = DecimalUtils.fromWei(gasCostWei, 18);
    
    // Convert to token amount (human readable)
    const gasCostToken = gasCostETH.dividedBy(tokenPrice);
    
    // Convert back to raw token amount
    return DecimalUtils.toWei(gasCostToken, tokenDecimals);
  }
}
