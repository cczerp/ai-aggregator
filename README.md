# AI Aggregator - DeFi Arbitrage Bot

A sophisticated arbitrage bot that scans 300+ token pairs across 4 different DEXs to find the best arbitrage opportunities, then executes flashloans with Aave or Balancer (whichever is cheaper) and sends through Alchemy bundler for fast/private submissions.

## Features

- 🔍 **Multi-DEX Scanning**: Monitors Uniswap V2, Uniswap V3, SushiSwap, and Curve
- 💰 **Smart Flashloans**: Automatically selects the cheapest flashloan provider (Aave vs Balancer)
- 🎯 **Precise Decimal Handling**: Properly handles token decimals from start to finish (6, 8, 18 decimals)
- 🔒 **MEV Protection**: Uses Alchemy bundler for private transaction submission
- ⚡ **Real-time Monitoring**: Continuous scanning for arbitrage opportunities
- 📊 **Profit Calculation**: Accurate profit calculation including gas costs and fees

## Key Innovation: Decimal Math Precision

This bot correctly handles decimal conversions throughout the entire arbitrage calculation chain:

1. **Token Amount Conversion**: Converts between raw amounts (wei) and human-readable amounts
2. **Price Calculation**: Properly calculates prices considering different token decimals
3. **Profit Estimation**: Accurate profit calculation with proper decimal adjustments
4. **Gas Cost Conversion**: Converts gas costs to token amounts with correct decimals

### Example Decimal Handling

```typescript
// WETH (18 decimals) to USDC (6 decimals)
const wethAmount = DecimalUtils.toWei('1', 18);     // 1000000000000000000
const usdcAmount = DecimalUtils.toWei('2000', 6);   // 2000000000
const price = DecimalUtils.calculatePrice(
  wethAmount, 
  usdcAmount, 
  18, 
  6
); // Result: 2000 (USDC per WETH)
```

## Installation

```bash
# Install dependencies
npm install

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env

# Build the project
npm run build
```

## Configuration

Edit `.env` file with your settings:

```env
RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY
ALCHEMY_BUNDLER_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY
PRIVATE_KEY=your_private_key_here
MIN_PROFIT_THRESHOLD_USD=50
GAS_PRICE_MULTIPLIER=1.1
```

## Usage

```bash
# Development mode with hot reload
npm run dev

# Production mode
npm start
```

## Architecture

### Core Components

1. **DecimalUtils** (`src/utils/decimal.ts`)
   - Handles all decimal conversions (wei ↔ human readable)
   - Calculates prices with proper decimal adjustments
   - Computes arbitrage profits considering different token decimals
   - Validates profitability after gas costs

2. **DEX Interface** (`src/dex/`)
   - Unified interface for different DEX implementations
   - Uniswap V2-style DEX support (UniswapV2, SushiSwap)
   - Proper reserve and price calculations

3. **Arbitrage Scanner** (`src/arbitrage/scanner.ts`)
   - Scans multiple token pairs across all DEXs
   - Identifies price discrepancies
   - Calculates potential profits with decimal precision

4. **Flashloan Manager** (`src/flashloan/manager.ts`)
   - Compares Aave and Balancer fees
   - Selects cheapest provider automatically
   - Calculates net profit after all costs

5. **Alchemy Bundler** (`src/flashloan/bundler.ts`)
   - Submits transactions privately
   - Provides MEV protection
   - Ensures fast inclusion

## Decimal Handling Deep Dive

The bot handles three common token decimal configurations:

| Token Type | Decimals | Example | Raw Amount for 1.0 |
|------------|----------|---------|-------------------|
| Standard ERC20 | 18 | WETH, DAI, UNI | 1000000000000000000 |
| Stablecoins | 6 | USDC, USDT | 1000000 |
| Wrapped BTC | 8 | WBTC | 100000000 |

### Calculation Flow

```
1. Scan Phase
   ├─ Fetch prices from DEXs (raw amounts)
   ├─ Convert to comparable prices (decimal adjusted)
   └─ Identify arbitrage opportunities

2. Validation Phase
   ├─ Calculate gross profit (raw amounts)
   ├─ Estimate gas cost (convert ETH → token with decimals)
   ├─ Calculate flashloan fee (raw amounts)
   └─ Compute net profit

3. Execution Phase
   ├─ Prepare flashloan with correct amount (raw)
   ├─ Execute trades on DEXs (raw amounts)
   └─ Repay flashloan + fee (raw amounts)
```

## Testing

```bash
# Run tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test
npm test decimal.test.ts
```

## Supported Tokens

The bot monitors these tokens by default:
- WETH (18 decimals)
- USDC (6 decimals)
- USDT (6 decimals)
- DAI (18 decimals)
- WBTC (8 decimals)
- UNI, LINK, AAVE, MATIC, CRV (all 18 decimals)

## DEXs Supported

1. **Uniswap V2** - 0.3% fee
2. **SushiSwap** - 0.3% fee
3. **Uniswap V3** - 0.3% fee (default tier)
4. **Curve** - 0.04% fee

## Flashloan Providers

1. **Balancer** - 0% fee (preferred when available)
2. **Aave V3** - 0.09% fee

## Safety Features

- ✅ Simulation before execution
- ✅ Slippage protection
- ✅ Minimum profit threshold
- ✅ Gas cost consideration
- ✅ Private transaction submission
- ✅ Proper error handling

## Disclaimer

This software is for educational purposes. Use at your own risk. Cryptocurrency trading involves substantial risk of loss. Always test with small amounts first.

## License

MIT
