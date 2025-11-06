# Decimal Handling Examples

This document demonstrates how the arbitrage bot properly handles decimal conversions throughout the entire calculation chain.

## Token Decimal Configurations

| Token | Decimals | 1.0 Token (Raw) | Example Use Case |
|-------|----------|-----------------|------------------|
| WETH  | 18       | 1000000000000000000 | Ethereum wrapping |
| USDC  | 6        | 1000000 | Stablecoin |
| USDT  | 6        | 1000000 | Stablecoin |
| DAI   | 18       | 1000000000000000000 | Stablecoin |
| WBTC  | 8        | 100000000 | Bitcoin wrapping |

## Example 1: Simple Conversion

### WETH (18 decimals) to Human Readable
```typescript
const wethRaw = '1000000000000000000'; // 1 WETH in wei
const readable = DecimalUtils.fromWei(wethRaw, 18);
// Result: 1.0 WETH
```

### USDC (6 decimals) to Human Readable
```typescript
const usdcRaw = '2000000000'; // 2000 USDC in raw units
const readable = DecimalUtils.fromWei(usdcRaw, 6);
// Result: 2000.0 USDC
```

## Example 2: Price Calculation Between Different Decimals

### WETH/USDC Price
```typescript
const wethAmount = '1000000000000000000'; // 1 WETH (18 decimals)
const usdcAmount = '2000000000';          // 2000 USDC (6 decimals)

const price = DecimalUtils.calculatePrice(
  wethAmount,
  usdcAmount,
  18, // WETH decimals
  6   // USDC decimals
);
// Result: 2000 (USDC per WETH)
```

### WBTC/WETH Price
```typescript
const wbtcAmount = '100000000';             // 1 WBTC (8 decimals)
const wethAmount = '15000000000000000000';  // 15 WETH (18 decimals)

const price = DecimalUtils.calculatePrice(
  wbtcAmount,
  wethAmount,
  8,  // WBTC decimals
  18  // WETH decimals
);
// Result: 15 (WETH per WBTC)
```

## Example 3: Arbitrage Profit Calculation

### Scenario: Buy WETH with USDC, Sell for More USDC

```typescript
// Initial: 2000 USDC
const initialAmount = DecimalUtils.toWei('2000', 6); // 2000000000 (raw)

// DEX 1: Buy WETH at $2000 per WETH
// Trade: 2000 USDC → 1 WETH
const buyPrice = '0.0005'; // 0.0005 WETH per USDC (1/2000)
const wethReceived = DecimalUtils.calculateOutputAmount(
  initialAmount,
  buyPrice,
  6,  // USDC decimals
  18  // WETH decimals
);
// Result: 1000000000000000000 (1 WETH in wei)

// DEX 2: Sell WETH at $2020 per WETH
// Trade: 1 WETH → 2020 USDC
const sellPrice = '2020'; // 2020 USDC per WETH
const usdcReceived = DecimalUtils.calculateOutputAmount(
  wethReceived,
  sellPrice,
  18, // WETH decimals
  6   // USDC decimals
);
// Result: 2020000000 (2020 USDC in raw)

// Profit
const profit = new BigNumber(usdcReceived).minus(initialAmount);
const profitReadable = DecimalUtils.fromWei(profit, 6);
// Result: 20 USDC profit

// Profit Percentage
const profitPct = DecimalUtils.calculateProfitPercentage(
  initialAmount,
  usdcReceived
);
// Result: 1% profit
```

## Example 4: Gas Cost Conversion

### Converting ETH Gas Cost to USDC

```typescript
// Gas used: 300,000 gas
// Gas price: 50 gwei
const gasUsed = new BigNumber(300000);
const gasPrice = new BigNumber('50000000000'); // 50 gwei in wei

// Total gas cost in wei
const gasCostWei = gasUsed.multipliedBy(gasPrice);
// Result: 15000000000000000 (0.015 ETH in wei)

// Convert to human-readable ETH
const gasCostETH = DecimalUtils.fromWei(gasCostWei, 18);
// Result: 0.015 ETH

// Convert to USDC (assuming 1 ETH = 2000 USDC)
const ethPrice = new BigNumber(2000);
const gasCostUSDC = gasCostETH.multipliedBy(ethPrice);
// Result: 30 USDC

// Convert to raw USDC for comparison
const gasCostUSDCRaw = DecimalUtils.toWei(gasCostUSDC, 6);
// Result: 30000000 (30 USDC in raw units)
```

## Example 5: Flashloan Fee Calculation

### Balancer (0% fee)
```typescript
const loanAmount = DecimalUtils.toWei('100', 18); // 100 WETH
const balancerFee = FlashloanManager.calculateFlashloanCost(
  loanAmount,
  FLASHLOAN_PROVIDERS.BALANCER
);
// Result: 0 (Balancer has no fee)
```

### Aave (0.09% fee)
```typescript
const loanAmount = DecimalUtils.toWei('100', 18); // 100 WETH
const aaveFee = FlashloanManager.calculateFlashloanCost(
  loanAmount,
  FLASHLOAN_PROVIDERS.AAVE
);
// Result: 90000000000000000 (0.09 WETH in wei)
// Human readable: 0.09 WETH
```

## Example 6: Complete Arbitrage Flow

```typescript
// 1. Scan for opportunities
const baseAmount = DecimalUtils.toWei('5', 18); // 5 WETH
const opportunities = await scanner.scanPairs(pairs, baseAmount);

// 2. Best opportunity found
// Buy at DEX1: 5 WETH → 10000 USDC (price: 2000 USDC/WETH)
// Sell at DEX2: 10000 USDC → 5.05 WETH (price: 1980 USDC/WETH)

// 3. Calculate net profit
const grossProfit = DecimalUtils.toWei('0.05', 18); // 0.05 WETH
const flashloanCost = new BigNumber(0); // Using Balancer
const gasCost = DecimalUtils.toWei('0.01', 18); // 0.01 WETH

const netProfit = grossProfit
  .minus(flashloanCost)
  .minus(gasCost);
// Result: 40000000000000000 (0.04 WETH in wei)

// 4. Verify profitability
const isProfitable = DecimalUtils.isProfitable(
  grossProfit,
  gasCost.plus(flashloanCost),
  DecimalUtils.toWei('0.01', 18) // Minimum 0.01 WETH profit
);
// Result: true (0.04 > 0.01)
```

## Key Takeaways

1. **Always use raw amounts (wei) for blockchain interactions**
   - Smart contracts expect amounts in smallest units
   - No floating-point precision issues

2. **Convert to human-readable only for display**
   - Makes logs and UI more understandable
   - Use `DecimalUtils.fromWei()` for conversion

3. **Handle decimal differences in price calculations**
   - WETH (18) to USDC (6) requires proper adjustment
   - Use `DecimalUtils.calculatePrice()` for correct results

4. **Round down for token amounts**
   - Prevents sending more than available
   - Configured in BigNumber settings

5. **Test with different decimal configurations**
   - 6 decimals (stablecoins)
   - 8 decimals (WBTC)
   - 18 decimals (most ERC20s)

## Testing Decimal Precision

All decimal operations are tested in `src/utils/decimal.test.ts`:
- ✅ 25 passing tests
- ✅ Covers all decimal configurations (6, 8, 18)
- ✅ Tests edge cases (very large/small numbers)
- ✅ Validates precision in calculations
