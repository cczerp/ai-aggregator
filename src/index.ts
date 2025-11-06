import BigNumber from 'bignumber.js';
import { configureBigNumber, DecimalUtils } from './utils/decimal';
import { DexFactory } from './dex/factory';
import { ArbitrageScanner } from './arbitrage/scanner';
import { FlashloanManager } from './flashloan/manager';
import { AlchemyBundler } from './flashloan/bundler';
import { DEXS, TOKENS, generateTokenPairs, CONFIG } from './config';
import { ArbitrageOpportunity, FlashloanParams } from './types';

// Configure BigNumber for proper decimal handling
configureBigNumber();

/**
 * Main arbitrage bot class
 */
export class ArbitrageBot {
  private scanner: ArbitrageScanner;
  private bundler: AlchemyBundler;
  private isRunning: boolean = false;

  constructor() {
    // Initialize DEXs
    const dexes = DexFactory.createAllDexes(DEXS);
    
    // Initialize scanner with 0.5% minimum profit threshold
    this.scanner = new ArbitrageScanner(dexes, 0.5);
    
    // Initialize Alchemy bundler
    this.bundler = new AlchemyBundler(
      CONFIG.ALCHEMY_BUNDLER_URL,
      CONFIG.PRIVATE_KEY
    );
  }

  /**
   * Start the arbitrage bot
   */
  async start(): Promise<void> {
    console.log('🚀 Starting Arbitrage Bot...');
    console.log(`Scanning ${Object.keys(TOKENS).length} tokens across ${Object.keys(DEXS).length} DEXs`);
    
    this.isRunning = true;

    while (this.isRunning) {
      try {
        await this.scanAndExecute();
        
        // Wait before next scan
        await this.sleep(CONFIG.SCAN_INTERVAL_MS);
      } catch (error) {
        console.error('Error in main loop:', error);
        await this.sleep(5000);
      }
    }
  }

  /**
   * Stop the bot
   */
  stop(): void {
    console.log('Stopping bot...');
    this.isRunning = false;
  }

  /**
   * Scan for opportunities and execute if profitable
   */
  private async scanAndExecute(): Promise<void> {
    console.log('\n📊 Scanning for arbitrage opportunities...');
    
    // Generate all token pairs
    const pairs = generateTokenPairs();
    console.log(`Scanning ${pairs.length} token pairs...`);

    // Use a standard amount for scanning (e.g., $10,000 worth)
    // For WETH, use 5 ETH as base amount
    const baseAmount = DecimalUtils.toWei('5', TOKENS.WETH.decimals);

    // Scan all pairs
    const opportunities = await this.scanner.scanPairs(pairs, baseAmount);

    console.log(`Found ${opportunities.length} potential opportunities`);

    if (opportunities.length === 0) {
      console.log('No profitable opportunities found');
      return;
    }

    // Get the best opportunity
    const best = this.scanner.findBestOpportunity(opportunities);
    
    if (!best) {
      return;
    }

    console.log('\n💰 Best Opportunity Found:');
    this.logOpportunity(best);

    // Check if profitable after costs
    const gasCost = await this.estimateGasCost(best);
    const minProfit = DecimalUtils.toWei('0.01', best.tokenA.decimals); // 0.01 tokens minimum

    const profitAnalysis = FlashloanManager.isProfitableAfterCosts(
      best,
      gasCost,
      minProfit
    );

    console.log('\n📈 Profit Analysis:');
    console.log(`Gross Profit: ${DecimalUtils.format(DecimalUtils.fromWei(best.expectedProfit, best.tokenA.decimals), 6)} ${best.tokenA.symbol}`);
    console.log(`Flashloan Cost: ${DecimalUtils.format(DecimalUtils.fromWei(profitAnalysis.flashloanParams.estimatedCost, best.tokenA.decimals), 6)} ${best.tokenA.symbol}`);
    console.log(`Gas Cost: ${DecimalUtils.format(DecimalUtils.fromWei(gasCost, best.tokenA.decimals), 6)} ${best.tokenA.symbol}`);
    console.log(`Net Profit: ${DecimalUtils.format(DecimalUtils.fromWei(profitAnalysis.netProfit, best.tokenA.decimals), 6)} ${best.tokenA.symbol}`);
    console.log(`Flashloan Provider: ${profitAnalysis.flashloanParams.provider.name} (${profitAnalysis.flashloanParams.provider.feePercentage}% fee)`);

    if (!profitAnalysis.profitable) {
      console.log('❌ Not profitable after costs');
      return;
    }

    console.log('✅ Profitable! Preparing execution...');

    // Execute the arbitrage
    await this.executeArbitrage(best, profitAnalysis.flashloanParams);
  }

  /**
   * Execute the arbitrage opportunity
   */
  private async executeArbitrage(
    opportunity: ArbitrageOpportunity,
    flashloanParams: FlashloanParams
  ): Promise<void> {
    console.log('\n🔥 Executing arbitrage...');

    try {
      // Prepare flashloan execution
      const executionData = FlashloanManager.prepareFlashloanExecution(
        flashloanParams,
        opportunity
      );

      console.log('Execution Plan:');
      console.log(`1. Flashloan ${DecimalUtils.format(DecimalUtils.fromWei(flashloanParams.amount, opportunity.tokenA.decimals))} ${opportunity.tokenA.symbol} from ${executionData.provider}`);
      console.log(`2. Swap on ${opportunity.buyDex}: ${opportunity.tokenA.symbol} → ${opportunity.tokenB.symbol}`);
      console.log(`3. Swap on ${opportunity.sellDex}: ${opportunity.tokenB.symbol} → ${opportunity.tokenA.symbol}`);
      console.log(`4. Repay flashloan + fee`);

      // Simulate the bundle first
      const simulation = await this.bundler.simulateBundle([
        {
          to: flashloanParams.provider.address,
          data: executionData.calldata,
          value: '0',
          gasLimit: '500000'
        }
      ]);

      if (!simulation.success) {
        console.log('❌ Simulation failed:', simulation.revertReason);
        return;
      }

      console.log('✅ Simulation successful');

      // Submit to Alchemy bundler for private execution
      const result = await this.bundler.submitPrivateTransaction(
        flashloanParams.provider.address,
        executionData.calldata,
        '0',
        '500000'
      );

      if (result.success) {
        console.log(`✅ Transaction submitted: ${result.txHash}`);
        console.log('Waiting for confirmation...');
        
        const confirmed = await this.bundler.waitForInclusion(result.txHash!);
        
        if (confirmed) {
          console.log('✅ Arbitrage executed successfully!');
        }
      } else {
        console.log('❌ Transaction failed:', result.error);
      }
    } catch (error) {
      console.error('Error executing arbitrage:', error);
    }
  }

  /**
   * Estimate gas cost in terms of the input token
   */
  private async estimateGasCost(opportunity: ArbitrageOpportunity): Promise<BigNumber> {
    const gasPrice = await this.bundler.getGasPrice();
    const priorityGasPrice = this.bundler.calculatePriorityFee(gasPrice, CONFIG.GAS_PRICE_MULTIPLIER);
    
    // TODO: Fetch real-time ETH price from a price feed or DEX
    // For now, use a conservative estimate
    // In production, this should query Chainlink or get spot price from Uniswap
    const ethPriceInToken = new BigNumber(2000);
    
    // Estimate gas based on complexity:
    // - Simple swap: ~150k gas
    // - Flashloan + 2 swaps: ~300k gas
    // - Complex routes: ~500k gas
    const estimatedGasUnits = 300000; // Default for flashloan arbitrage
    
    return FlashloanManager.estimateGasCost(
      priorityGasPrice,
      ethPriceInToken,
      opportunity.tokenA.decimals,
      estimatedGasUnits
    );
  }

  /**
   * Log opportunity details
   */
  private logOpportunity(opp: ArbitrageOpportunity): void {
    console.log(`Pair: ${opp.tokenA.symbol}/${opp.tokenB.symbol}`);
    console.log(`Route: ${opp.route.join(' → ')}`);
    console.log(`Amount: ${DecimalUtils.format(DecimalUtils.fromWei(opp.amountIn, opp.tokenA.decimals))} ${opp.tokenA.symbol}`);
    console.log(`Expected Profit: ${DecimalUtils.format(DecimalUtils.fromWei(opp.expectedProfit, opp.tokenA.decimals))} ${opp.tokenA.symbol} (${DecimalUtils.format(opp.profitPercentage, 2)}%)`);
    console.log(`Buy Price (${opp.buyDex}): ${DecimalUtils.format(opp.buyPrice, 6)}`);
    console.log(`Sell Price (${opp.sellDex}): ${DecimalUtils.format(opp.sellPrice, 6)}`);
  }

  /**
   * Sleep utility
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// Main entry point
async function main() {
  console.log('='.repeat(60));
  console.log('🤖 AI Aggregator - Arbitrage Bot');
  console.log('='.repeat(60));
  
  const bot = new ArbitrageBot();
  
  // Handle graceful shutdown
  process.on('SIGINT', () => {
    console.log('\nShutting down...');
    bot.stop();
    process.exit(0);
  });

  await bot.start();
}

// Run if this is the main module
if (require.main === module) {
  main().catch(console.error);
}

export default ArbitrageBot;
