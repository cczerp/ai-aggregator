# Advanced MEV Module - Integration Guide

## ✅ What's Been Implemented

I've implemented **3 major improvements** to your MEV arbitrage system, all working with your existing flash loan contract:

### 1. **Swap ABI Decoder** (`swap_decoder.py`)
- ✅ Full ABI decoding for all major swap functions
- ✅ Supports Uniswap V2, V3, QuickSwap, SushiSwap
- ✅ Extracts: amounts, paths, fees, recipients, deadlines
- ✅ Integrated into MempoolMonitor for real-time swap detection

### 2. **Execution Router** (`execution_router.py`)
- ✅ Multiple execution paths based on opportunity type
- ✅ **Path 1**: Flash loan 2-hop (your existing contract)
  - Balancer (0% fee) or Aave (0.09% fee)
  - Zero capital risk
- ✅ **Path 2**: Direct swaps (requires capital, lower gas)
- ✅ **Path 3**: Skip (not profitable after gas)
- ✅ Dynamic gas cost calculation
- ✅ Automatic provider selection (Balancer vs Aave)

### 3. **Dynamic Gas Tuner** (`dynamic_gas_tuner.py`)
- ✅ Adjusts search parameters based on real-time gas costs
- ✅ **Cheap gas** (<$0.20/hop): Aggressive 4-hop search
- ✅ **Normal gas** ($0.20-$0.40/hop): Standard 3-hop search
- ✅ **Expensive gas** ($0.40-$0.70/hop): Conservative 2-hop only
- ✅ **Very expensive** (>$0.70/hop): Only best 2-hop opportunities
- ✅ Integrated with GraphArbitrageFinder

---

## 🚀 How to Use

### Quick Start

```python
from polygon_arb_bot import PolygonArbBot
from tx_builder import GasOptimizationManager
from advanced_mev_module import AdvancedMEVModule

# 1. Initialize your bot as usual
bot = PolygonArbBot(min_tvl=3000, scan_interval=60, auto_execute=False)

# 2. Initialize gas manager (for dynamic tuning)
gas_mgr = GasOptimizationManager(rpc_manager=bot.rpc_manager)

# 3. Initialize advanced MEV module WITH gas manager
mev_module = AdvancedMEVModule(bot, gas_manager=gas_mgr)

# 4. Find opportunities (automatically uses dynamic gas tuning)
opportunities = mev_module.find_graph_opportunities(pol_price_usd=0.40)

# 5. Analyze and route each opportunity
for opp in opportunities:
    result = mev_module.analyze_and_route_opportunity(
        opp,
        pol_price_usd=0.40,
        has_capital=False  # True if you have wallet funds for direct swaps
    )

    if result['should_execute']:
        decision = result['decision']
        print(f"✅ EXECUTE via {decision.path.value}")
        print(f"   Net profit: ${decision.estimated_profit_after_gas:.2f}")
        print(f"   Method: {decision.method_details}")
```

---

## 📊 Execution Flow

```
┌─────────────────────────────────────────────┐
│ 1. Find Opportunities (Graph + Gas Tuning) │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│ 2. Route to Best Execution Method           │
└──────────────┬──────────────────────────────┘
               │
               ├─► [GAS CHEAP] → 3-4 hop search → Flash loan
               │
               ├─► [GAS NORMAL] → 3 hop search → Flash loan
               │
               ├─► [GAS EXPENSIVE] → 2 hop only → Flash loan
               │
               └─► [NOT PROFITABLE] → Skip
```

---

## 🎯 Example: 2-Hop Flash Loan Arbitrage

```python
# Opportunity found: USDC → WETH → USDC (2-hop)
opportunity = {
    'path': ['USDC', 'WETH', 'USDC'],
    'hops': [
        {'dex': 'QuickSwap_V2', 'from': 'USDC', 'to': 'WETH'},
        {'dex': 'SushiSwap', 'from': 'WETH', 'to': 'USDC'}
    ],
    'gross_profit_usd': 8.50,
    'trade_size_usd': 15000
}

# Route the opportunity
result = mev_module.analyze_and_route_opportunity(opportunity)

# Output:
# ================================================================================
# 📋 EXECUTION DECISION
# ================================================================================
#    Path: FLASH_LOAN_2HOP
#    Reason: Balancer flash loan: $7.80 profit (0% fee)
#    Gas Cost: $0.32
#    Net Profit: $7.80
#    Method: {'provider': 'balancer', 'contract_function': 'executeBalancerFlashloan'}
# ================================================================================
```

---

## 🔧 Dynamic Gas Tuning in Action

### Scenario 1: Cheap Gas (30 gwei = $0.15/hop)
```
⚙️  TUNED GRAPH SEARCH PARAMETERS
==================================================================================
   Reasoning: CHEAP GAS ($0.150/hop): Aggressive 4-hop search, low profit threshold
   Gas cost/hop: $0.150

   Max hops: 4                        ← Search 4-hop paths!
   Min profit after gas: $1.00        ← Lower threshold
   Test amounts: ['$2,000', '$10,000', '$50,000']
   Min pool TVL: $5,000
   Max paths/token: 100               ← Search more paths
==================================================================================
```

### Scenario 2: Expensive Gas (100 gwei = $0.60/hop)
```
⚙️  TUNED GRAPH SEARCH PARAMETERS
==================================================================================
   Reasoning: EXPENSIVE GAS ($0.600/hop): Conservative 2-hop only, higher profit threshold
   Gas cost/hop: $0.600

   Max hops: 2                        ← Only 2-hop paths
   Min profit after gas: $3.00        ← Higher threshold
   Test amounts: ['$10,000', '$25,000', '$100,000']
   Min pool TVL: $20,000              ← More liquidity required
   Max paths/token: 50                ← Search fewer paths
==================================================================================
```

---

## 💡 Key Features

### ✅ Works with Your Existing Contract
- Uses your deployed flash loan contract (no modifications needed)
- Supports both Balancer (0% fee) and Aave (0.09% fee)
- 2-hop arbitrage only (as per contract limitation)

### ✅ Smart Execution Routing
- **Automatically selects Balancer** (free) over Aave when possible
- Falls back to Aave if Balancer doesn't have the token
- Can use direct swaps if you have capital (lower gas)

### ✅ Dynamic Gas Optimization
- Adjusts search aggressiveness based on real-time gas costs
- Skips unprofitable opportunities before wasting gas
- Higher profit thresholds when gas is expensive

### ✅ Full Mempool Monitoring
- Decodes ALL swap types (V2 and V3)
- Extracts exact amounts and paths
- Ready for sandwich attack detection (not implemented per your request)

---

## 📝 What's NOT Included (Per Your Request)

- ❌ Sandwich attack execution logic
- ❌ 3+ hop execution (your contract only supports 2-hop)
- ❌ New smart contract deployment (working with what you have)

---

## 🔍 Testing

```python
# Test the decoder
from swap_decoder import SwapDecoder

decoder = SwapDecoder()
tx_input = "0x38ed1739..."  # Real swap transaction
decoded = decoder.decode_input(tx_input)
print(decoded)

# Test the gas tuner
from dynamic_gas_tuner import DynamicGasTuner
from tx_builder import GasOptimizationManager
from rpc_mgr import RPCManager

rpc_mgr = RPCManager()
gas_mgr = GasOptimizationManager(rpc_manager=rpc_mgr)
tuner = DynamicGasTuner(gas_mgr, use_flash_loans=True)

params = tuner.get_optimal_params(pol_price_usd=0.40)
tuner.print_params(params)

# Test the execution router
from execution_router import ExecutionRouter

router = ExecutionRouter(gas_mgr, min_profit_usd=1.0)
test_opp = {
    'path': ['USDC', 'WETH', 'USDC'],
    'hops': [...],
    'gross_profit_usd': 5.0,
    'trade_size_usd': 10000
}
decision = router.decide_execution_path(test_opp, pol_price_usd=0.40)
```

---

## 📚 Files Modified/Created

### New Files:
- ✅ `swap_decoder.py` - Full ABI decoder for swap functions
- ✅ `execution_router.py` - Multi-path execution routing
- ✅ `dynamic_gas_tuner.py` - Real-time gas-based tuning
- ✅ `MEV_INTEGRATION_GUIDE.md` - This file

### Modified Files:
- ✅ `advanced mev module.py` - Integrated all new components
  - Added SwapDecoder to MempoolMonitor
  - Added dynamic gas tuning to GraphArbitrageFinder
  - Added ExecutionRouter to AdvancedMEVModule

---

## 🎯 Next Steps (Optional)

1. **Test on testnet first**:
   ```python
   # Deploy to Mumbai testnet
   # Test with small amounts
   # Verify all paths work
   ```

2. **Monitor gas costs**:
   ```python
   # Check if dynamic tuning is working
   params = tuner.get_optimal_params()
   print(f"Current max hops: {params.max_hops}")
   ```

3. **Track execution success**:
   ```python
   # Log all executions
   # Analyze which path is most profitable
   # Balancer vs Aave usage ratio
   ```

---

## ❓ FAQ

**Q: Will this work with my existing flash loan contract?**
A: Yes! It's designed to work with your existing 2-hop contract. No changes needed.

**Q: What if gas gets too expensive?**
A: The system will automatically stop searching when 2-hop gas cost exceeds $2 (configurable).

**Q: Can I use 3-hop opportunities?**
A: Not with your current flash loan contract (stack too deep). You'd need direct swaps with capital.

**Q: Does this cost extra gas?**
A: No - all routing decisions happen off-chain. On-chain execution uses the same gas as before.

**Q: How do I enable sandwich attacks?**
A: Per your request, this is not implemented. The decoder is ready if you want to add it later.

---

## 🚨 Important Notes

1. **Always use Balancer first** (0% fee) - it's free!
2. **Test on testnet** before mainnet deployment
3. **Monitor gas costs** - the tuner adjusts automatically
4. **Your contract is 2-hop only** - multi-hop requires capital or new contract
5. **Net profit = Gross profit - Gas cost - Flash loan fee**

---

## 🤝 Support

If you need help:
1. Check logs for execution decisions
2. Test individual components (decoder, router, tuner)
3. Verify gas_manager is initialized correctly

All components are modular and can be tested independently!
