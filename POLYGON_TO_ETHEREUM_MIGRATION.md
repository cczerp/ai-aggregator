# Polygon to Ethereum Migration Guide

## Overview

Your MEV bot is designed for a two-phase approach:
1. **Phase 1 (Polygon)**: Test and optimize arbitrage + ML system with low gas costs
2. **Phase 2 (Ethereum)**: Deploy to mainnet and enable sandwich attacks with Flashbots

---

## Phase 1: Polygon Setup (Current)

### What Works on Polygon
✅ **DEX Arbitrage** - Fully functional
✅ **Flash Loans** - Balancer (0% fee) and Aave (0.09% fee)
✅ **ML Learning** - Learns from every trade
✅ **Token Approvals** - Automatic handling
✅ **Low Gas Costs** - ~$0.01-0.10 per trade

### What Doesn't Work on Polygon
❌ **Sandwich Attacks** - Flashbots doesn't exist on Polygon
❌ **Atomic Bundle Submission** - No guarantee of transaction ordering
❌ **Mempool Priority** - No private relay for frontrunning

### Polygon Configuration
```bash
# .env for Polygon
ENABLE_SANDWICH=false        # Must be FALSE
ENABLE_ARBITRAGE=true         # Primary strategy
ENABLE_ML=true                # Learn and optimize
```

### Deploy on Polygon
1. Deploy flash loan contract to Polygon mainnet
2. Use Aave Pool: `0x794a61358D6845594F94dc1DB02A252b5b4814aD`
3. Use Balancer Vault: `0xBA12222222228d8Ba445958a75a0704d566BF2C8`
4. Fund wallet with 10-20 POL for gas

### Expected Results (Polygon)
- Week 1: $50-200/day
- Week 4: $100-400/day (ML optimized)
- Gas cost: ~$5-20/day
- Net profit: $45-380/day

---

## Phase 2: Ethereum Migration (Future)

### When to Migrate
Consider moving to Ethereum when:
- ✅ ML system is trained (1000+ trades on Polygon)
- ✅ Success rate is consistently 85%+
- ✅ You understand the system well
- ✅ You have capital for higher gas costs
- ✅ Gas prices on Ethereum are reasonable (<50 gwei)

### What Changes on Ethereum

#### Advantages
✅ **Sandwich Attacks** - Flashbots enables profitable frontrunning
✅ **Higher MEV Opportunities** - More volume, more victims
✅ **Atomic Bundles** - Guaranteed transaction ordering
✅ **Private Relay** - Transactions don't hit public mempool

#### Disadvantages
❌ **High Gas Costs** - 10-50x more expensive than Polygon
❌ **Flash Loan Fees** - Aave charges 0.09% (Balancer still 0%)
❌ **Expensive Failures** - Failed trades cost $10-50 in gas
❌ **More Competition** - More MEV bots competing

---

## Migration Checklist

### Step 1: Update Token/DEX Registries
```python
# registries.py - Add Ethereum addresses

TOKENS = {
    'USDC': {
        'ethereum': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
        'polygon': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
    },
    'WETH': {
        'ethereum': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
        'polygon': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619'
    },
    # ... add all tokens for Ethereum
}

DEXES = {
    'uniswap_v2': {
        'ethereum': {
            'router': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
            'factory': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f'
        }
    },
    # ... add all DEXs for Ethereum
}
```

### Step 2: Deploy Contract to Ethereum
```solidity
// Constructor parameters for Ethereum:
_aave: 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2  // Aave V3 Pool
_balancer: 0xBA12222222228d8Ba445958a75a0704d566BF2C8  // Balancer Vault (same!)
```

Deploy via Remix to Ethereum mainnet (expensive - ~$50-200 gas)

### Step 3: Update RPC Endpoints
```python
# rpc_mgr.py - Add Ethereum endpoints

if chain_id == 1:  # Ethereum mainnet
    self.endpoints = [
        'https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY',
        'https://mainnet.infura.io/v3/YOUR_KEY',
        'https://rpc.ankr.com/eth',
        # ... Ethereum RPCs
    ]
elif chain_id == 137:  # Polygon
    # ... existing Polygon endpoints
```

### Step 4: Update Configuration
```bash
# .env for Ethereum
CONTRACT_ADDRESS=0xYourNewEthereumContractAddress  # New deployment
PRIVATE_KEY=0xYourPrivateKey                       # Same or different wallet
FLASHBOTS_RELAY_URL=https://relay.flashbots.net    # Now functional!

# Enable sandwich attacks
ENABLE_SANDWICH=true         # NOW SET TO TRUE
ENABLE_ARBITRAGE=true        # Keep as backup
ENABLE_ML=true               # Transfer learned model

# Chain selection
CHAIN_ID=1                   # Ethereum mainnet
```

### Step 5: Transfer ML Model
```bash
# Copy trained ML model from Polygon run
cp trade_history.json trade_history_polygon_backup.json
# Keep using trade_history.json - ML continues learning on Ethereum
```

### Step 6: Adjust Gas Parameters
```python
# dynamic_gas_tuner.py - Ethereum has higher gas

if gas_cost_per_hop < 5.0:   # CHEAP for Ethereum (was 0.20 on Polygon)
    return GraphSearchParams(max_hops=4, min_profit=10.0)
elif gas_cost_per_hop < 15.0:  # NORMAL (was 0.40)
    return GraphSearchParams(max_hops=3, min_profit=20.0)
else:  # EXPENSIVE (was >0.40)
    return GraphSearchParams(max_hops=2, min_profit=30.0)
```

### Step 7: Update Profit Thresholds
```python
# sandwich_bot.py
self.MIN_VICTIM_VALUE_USD = 100000  # Increase from $50k to $100k
self.MIN_PROFIT_USD = 50.0          # Increase from $10 to $50
self.GAS_PER_SANDWICH = 300000      # Same

# execution_router.py
self.min_profit_usd = 10.0  # Increase from $1 to $10 (higher gas on ETH)
```

---

## Cost Comparison

### Polygon (Phase 1)
```
Deployment: $2-5
Approval per token: $0.01-0.05
Trade execution: $0.01-0.10
Daily gas budget: $5-20

Expected profit: $50-200/day
Net profit: $45-180/day
ROI: Positive from day 1
```

### Ethereum (Phase 2)
```
Deployment: $50-200
Approval per token: $5-20
Trade execution: $10-50
Sandwich bundle: $20-100 (includes bribe)
Daily gas budget: $100-500

Expected profit: $210-1200/day
Net profit: $110-700/day (after gas)
ROI: Positive after 2-3 days
```

---

## Recommended Strategy

### Phase 1: Polygon Training (Month 1-2)
**Goal**: Train ML system, test strategies, learn the system

```bash
ENABLE_SANDWICH=false
ENABLE_ARBITRAGE=true
ENABLE_ML=true
```

**Activities**:
- Run bot 24/7 on Polygon
- Let ML learn from 1000+ trades
- Monitor success rate (target: 85%+)
- Understand failure patterns
- Optimize parameters
- Low risk, low cost

**Success Metrics**:
- ✅ ML success rate: 85%+
- ✅ Consistent daily profit
- ✅ You understand logs and behavior
- ✅ 1000+ trades in history

---

### Phase 2: Ethereum Production (Month 3+)
**Goal**: Scale up with sandwich attacks, maximize profit

```bash
ENABLE_SANDWICH=true   # Enable now!
ENABLE_ARBITRAGE=true  # Keep as backup
ENABLE_ML=true         # Use trained model
```

**Activities**:
- Deploy to Ethereum with trained ML model
- Enable sandwich attacks
- Monitor Flashbots submission success
- Adjust bribes based on competition
- Scale up capital as confidence grows

**Success Metrics**:
- ✅ Sandwich success rate: 60%+ (Week 1) → 85%+ (Month 2)
- ✅ Daily profit > daily gas costs
- ✅ ML continues learning on Ethereum
- ✅ Profitable after gas + bribes

---

## Files Requiring Updates for Ethereum

### Core Files to Update
1. **registries.py** - Add Ethereum token/DEX addresses
2. **rpc_mgr.py** - Add Ethereum RPC endpoints
3. **dynamic_gas_tuner.py** - Adjust gas thresholds for ETH
4. **execution_router.py** - Increase min profit thresholds
5. **sandwich_bot.py** - Increase victim size and profit mins
6. **.env** - New contract address, enable sandwich, set CHAIN_ID=1

### Files That Work As-Is
- ✅ swap_decoder.py - Works on both chains
- ✅ token_approval.py - Works on both chains
- ✅ ml_strategy_brain.py - Transfer learned model
- ✅ main_menu.py - No changes needed
- ✅ master_mev_bot.py - No changes needed
- ✅ unified_mev_bot.py - No changes needed

---

## Testing Before Migration

### Dry Run on Ethereum
```bash
# Point to Ethereum testnet (Goerli/Sepolia) first
CHAIN_ID=11155111  # Sepolia
ENABLE_SANDWICH=false  # Test arbitrage first
```

Test:
1. Contract deployment works
2. Token approvals work
3. Arbitrage executes successfully
4. Gas estimation is correct
5. RPC endpoints are fast enough

### Then Enable Sandwich on Mainnet
Once testnet works:
```bash
CHAIN_ID=1
ENABLE_SANDWICH=true
```

Start conservatively:
- Monitor first 24 hours closely
- Verify Flashbots bundles are landing
- Check bundle inclusion rate
- Adjust bribes if needed

---

## Risk Management

### Polygon Phase (Low Risk)
- Start with 10-20 POL (~$5-10)
- Each trade risks ~$0.01-0.10 in gas
- Max daily loss: $20 (gas only)
- No capital at risk (flash loans)

### Ethereum Phase (Higher Risk)
- Start with 1-2 ETH (~$2000-4000)
- Each trade risks $10-50 in gas
- Sandwich bribes: $10-100 per attempt
- Max daily loss: $500 (gas + failed bribes)
- Still no capital at risk (flash loans)

**Mitigation**:
- Test on testnet first
- Start with small amounts
- Monitor first week closely
- Scale up gradually
- Use kill switch (10 consecutive failures)

---

## Bottom Line

**Current State (Polygon)**:
- ✅ Arbitrage fully functional
- ✅ Low cost testing environment
- ✅ ML learning system operational
- ✅ Perfect for Phase 1

**Future State (Ethereum)**:
- 🔄 Sandwich attacks available
- 🔄 Higher profit potential
- 🔄 Higher costs and competition
- 🔄 Deploy when Polygon system is proven

**Timeline**:
- Month 1-2: Train on Polygon
- Month 3: Migrate to Ethereum
- Month 4+: Scale and optimize

**Your approach is perfect** - test cheap, deploy expensive only when proven! 🚀
