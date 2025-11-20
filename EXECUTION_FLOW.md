# Complete MEV Execution Flow

## 🔄 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. INITIALIZATION                             │
│  PolygonArbBot + GasManager + AdvancedMEVModule                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                2. DYNAMIC GAS TUNING                             │
│  Check current gas price → Adjust search parameters              │
│  • Cheap: 4-hop, $1 min profit                                   │
│  • Normal: 3-hop, $2 min profit                                  │
│  • Expensive: 2-hop, $3 min profit                               │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                3. FIND OPPORTUNITIES                             │
│  GraphArbitrageFinder scans with tuned parameters                │
│  • Build graph from pool data                                    │
│  • Find cycles (USDC → WETH → USDC)                             │
│  • Calculate profit for each path                                │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                4. EXECUTION ROUTING                              │
│  For each opportunity, decide HOW to execute:                    │
│  • 2-hop? → Use flash loan contract                             │
│  • 3-hop? → Skip (contract doesn't support)                     │
│  • Profitable after gas? → Execute or Skip                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                5. EXECUTE TRADE                                  │
│  Call your flash loan contract:                                  │
│  • executeBalancerFlashloan() [0% fee] OR                       │
│  • executeFlashloan() [0.09% fee]                               │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                6. ON-CHAIN EXECUTION                             │
│  Your contract:                                                   │
│  1. Borrows tokens via flash loan                                │
│  2. Swap 1: Buy on DEX1                                          │
│  3. Swap 2: Sell on DEX2                                         │
│  4. Repay flash loan + fee                                       │
│  5. Send profit to you                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📝 Detailed Flow with Code

### **Step 1: Initialize Everything**

```python
from polygon_arb_bot import PolygonArbBot
from tx_builder import GasOptimizationManager
from advanced_mev_module import AdvancedMEVModule
from remix_bot.flashloan_contract import FlashloanContract
import os

# Initialize bot
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,
    auto_execute=False
)

# Initialize gas manager for dynamic tuning
gas_mgr = GasOptimizationManager(rpc_manager=bot.rpc_manager)

# Initialize advanced MEV module
mev_module = AdvancedMEVModule(
    polygon_bot=bot,
    gas_manager=gas_mgr  # ← This enables dynamic tuning!
)

# Initialize flash loan contract wrapper
flash_contract = FlashloanContract(
    web3=bot.rpc_manager.get_web3(),
    contract_address=os.getenv('CONTRACT_ADDRESS'),
    private_key=os.getenv('PRIVATE_KEY')
)
```

**What happens**:
- ✅ Bot connects to 15+ RPC endpoints
- ✅ Cache loads historical data
- ✅ Gas manager initializes
- ✅ MEV module sets up: decoder, router, tuner

---

### **Step 2: Check Gas & Tune Parameters**

```python
# Get current POL price (from CoinGecko)
pol_price_usd = bot.price_fetcher.price_fetcher.get_price("WPOL") or 0.40

# Gas tuner automatically checks gas costs and tunes parameters
# This happens inside find_graph_opportunities()
```

**What happens** (inside `dynamic_gas_tuner.py`):
```python
gas_params = gas_mgr.get_optimized_gas_params()
gas_price_gwei = gas_params['maxFeePerGas'] / 1e9  # e.g., 35 gwei

# Calculate cost per hop
gas_per_hop = 150000  # units (flash loan + swap)
gas_cost_per_hop_usd = (gas_per_hop * gas_params['maxFeePerGas'] / 1e18) * pol_price_usd

# Example: 150000 * 35e9 / 1e18 * 0.40 = $0.21

if gas_cost_per_hop_usd < 0.20:
    # CHEAP GAS
    max_hops = 4
    min_profit = 1.0
    test_amounts = [2000, 10000, 50000]
elif gas_cost_per_hop_usd < 0.40:
    # NORMAL GAS
    max_hops = 3
    min_profit = 2.0
    test_amounts = [5000, 15000, 50000]
else:
    # EXPENSIVE GAS
    max_hops = 2
    min_profit = 3.0
    test_amounts = [10000, 25000, 100000]
```

**Output**:
```
⚙️  DYNAMIC GAS TUNING
   Gas cost per hop: $0.320

⚙️  TUNED GRAPH SEARCH PARAMETERS
   Reasoning: NORMAL GAS ($0.320/hop): Standard 3-hop search
   Max hops: 3
   Min profit after gas: $2.00
   Test amounts: ['$5,000', '$15,000', '$50,000']
```

---

### **Step 3: Find Opportunities**

```python
# Find opportunities (uses tuned parameters automatically)
opportunities = mev_module.find_graph_opportunities(pol_price_usd=pol_price_usd)

print(f"Found {len(opportunities)} opportunities")
for opp in opportunities[:3]:
    print(f"  • {opp['path']}: ${opp['profit_usd']:.2f} profit")
```

**What happens** (inside `GraphArbitrageFinder`):
```python
# 1. Build graph from pool data
for dex, pairs in pools_data.items():
    for pair in pairs:
        # Add edge: USDC → WETH (via QuickSwap)
        # Add edge: WETH → USDC (via SushiSwap)
        # etc.

# 2. Find cycles from each base token
for base_token in ['USDC', 'WETH', 'WPOL']:
    paths = find_triangular_paths(
        base_token,
        max_hops=3,  # ← From gas tuner
        max_paths=75  # ← From gas tuner
    )
    # Example paths found:
    # - USDC → WETH → USDC (2-hop)
    # - USDC → WETH → WPOL → USDC (3-hop)

    # 3. Calculate profit for each path
    for path in paths:
        for amount in [5000, 15000, 50000]:  # ← From gas tuner
            profit = calculate_path_profit(path, amount)
            if profit > 2.0:  # ← From gas tuner
                opportunities.append({
                    'path': path,
                    'profit_usd': profit,
                    'trade_size_usd': amount,
                    'hops': [...],
                    'gross_profit_usd': profit
                })
```

**Output**:
```
🔍 GRAPH-BASED ARBITRAGE SCAN

🎯 Scanning paths from USDC...
   Found 47 potential paths
   ✅ USDC → WETH → USDC = $8.50
   ✅ USDC → WPOL → USDC = $3.20

🎯 Scanning paths from WETH...
   Found 38 potential paths
   ✅ WETH → USDC → WETH = $5.75

Found 3 graph-based opportunities
```

---

### **Step 4: Route Each Opportunity**

```python
executable_opportunities = []

for opp in opportunities:
    # Analyze and route to best execution method
    result = mev_module.analyze_and_route_opportunity(
        opportunity=opp,
        pol_price_usd=pol_price_usd,
        has_capital=False  # Set True if you have wallet funds
    )

    if result['should_execute']:
        executable_opportunities.append({
            'opportunity': opp,
            'decision': result['decision']
        })
```

**What happens** (inside `ExecutionRouter`):
```python
# Check opportunity type
num_hops = len(opp['hops'])

if num_hops == 2:
    # Can use flash loan contract!

    # Option A: Balancer (0% fee)
    gas_cost = (400000 * gas_price) * pol_price  # $0.32
    flash_fee = 0  # FREE!
    net_profit = 8.50 - 0.32 - 0 = $8.18

    if net_profit >= 1.0:  # min threshold
        return ExecutionDecision(
            path=FLASH_LOAN_2HOP,
            provider='balancer',
            net_profit=$8.18,
            method='executeBalancerFlashloan'
        )

    # Option B: Aave (0.09% fee)
    flash_fee = 15000 * 0.0009 = $13.50
    net_profit = 8.50 - 0.32 - 13.50 = NEGATIVE!
    # Skip Aave, use Balancer

elif num_hops == 3:
    # Your contract doesn't support 3-hop
    return ExecutionDecision(
        path=SKIP,
        reason="3-hop not supported by flash loan contract"
    )
```

**Output**:
```
📋 EXECUTION DECISION #1
==================================================================================
   Path: FLASH_LOAN_2HOP
   Reason: Balancer flash loan: $8.18 profit (0% fee)
   Gas Cost: $0.32
   Net Profit: $8.18
   Method: {'provider': 'balancer', 'contract_function': 'executeBalancerFlashloan'}
==================================================================================

📋 EXECUTION DECISION #2
==================================================================================
   Path: SKIP
   Reason: Net profit $0.88 < min $1.00 after gas
==================================================================================
```

---

### **Step 5: Execute the Trade**

```python
from registries import get_token_address, DEXES

for exec_opp in executable_opportunities:
    decision = exec_opp['decision']
    opp = exec_opp['opportunity']

    if decision.path == ExecutionPath.FLASH_LOAN_2HOP:
        # Extract parameters from opportunity
        hops = opp['hops']

        # Hop 1: USDC → WETH on QuickSwap
        hop1 = hops[0]
        dex1_address = DEXES[hop1['dex']]['router']
        token_in = get_token_address(hop1['from'])
        token_out = get_token_address(hop1['to'])

        # Hop 2: WETH → USDC on SushiSwap
        hop2 = hops[1]
        dex2_address = DEXES[hop2['dex']]['router']

        # Trade size
        amount_in_usd = opp['trade_size_usd']
        amount_in_wei = int(amount_in_usd * 1e6)  # USDC has 6 decimals

        # Min profit (with 5% slippage buffer)
        expected_profit = decision.estimated_profit_after_gas
        min_profit_wei = int((expected_profit * 0.95) * 1e6)

        # Execute based on provider
        if decision.method_details['provider'] == 'balancer':
            print(f"🚀 Executing via Balancer flash loan...")

            tx_result = flash_contract.execute_balancer_flashloan(
                token_in=token_in,
                token_out=token_out,
                dex1_address=dex1_address,
                dex2_address=dex2_address,
                amount_in=amount_in_wei,
                min_profit=min_profit_wei
            )

        elif decision.method_details['provider'] == 'aave':
            print(f"🚀 Executing via Aave flash loan...")

            tx_result = flash_contract.execute_aave_flashloan(
                token_in=token_in,
                token_out=token_out,
                dex1_address=dex1_address,
                dex2_address=dex2_address,
                amount_in=amount_in_wei,
                min_profit=min_profit_wei
            )

        if tx_result['status'] == 'success':
            print(f"✅ SUCCESS! TX: {tx_result['tx_hash']}")
            print(f"   Gas used: {tx_result['gas_used']:,}")
            print(f"   Expected profit: ${expected_profit:.2f}")
        else:
            print(f"❌ FAILED: {tx_result.get('error')}")
```

**Output**:
```
🚀 Executing via Balancer flash loan...
✅ SUCCESS! TX: 0xabcd1234...
   Gas used: 387,234
   Expected profit: $8.18
```

---

### **Step 6: On-Chain Execution** (What Your Contract Does)

```solidity
// Inside your flash loan contract:

function executeBalancerFlashloan(
    address tokenIn,
    address tokenOut,
    address dex1,
    address dex2,
    uint8 dex1Version,
    uint8 dex2Version,
    uint256 amountIn,
    uint256 minProfitAmount,
    bytes memory dex1Data,
    bytes memory dex2Data
) external {
    // 1. Request flash loan from Balancer (0% fee!)
    balancerVault.flashLoan(
        this,
        [tokenIn],
        [amountIn],  // Borrow $15,000 USDC
        abi.encode(...)
    );
}

// Balancer calls this back:
function receiveFlashLoan(
    address[] memory tokens,
    uint256[] memory amounts,
    uint256[] memory feeAmounts,
    bytes memory userData
) external {
    // 2. Execute Swap 1: USDC → WETH on QuickSwap
    IERC20(USDC).approve(quickswapRouter, 15000e6);
    quickswapRouter.swapExactTokensForTokens(
        15000e6,  // USDC in
        0,        // min WETH out
        [USDC, WETH],
        address(this),
        deadline
    );
    // Received: ~5.2 WETH

    // 3. Execute Swap 2: WETH → USDC on SushiSwap
    IERC20(WETH).approve(sushiswapRouter, 5.2e18);
    sushiswapRouter.swapExactTokensForTokens(
        5.2e18,   // WETH in
        15000e6,  // min USDC out
        [WETH, USDC],
        address(this),
        deadline
    );
    // Received: ~15,008.18 USDC

    // 4. Repay flash loan
    IERC20(USDC).transfer(balancerVault, 15000e6 + 0);  // 0% fee!

    // 5. Calculate profit
    uint256 profit = IERC20(USDC).balanceOf(address(this));
    // profit = 8.18 USDC

    // 6. Require min profit met
    require(profit >= minProfitAmount, "Insufficient profit");

    // 7. Send profit to msg.sender (you!)
    IERC20(USDC).transfer(msg.sender, profit);
}
```

**Result**:
- ✅ Borrowed: $15,000 USDC (flash loan)
- ✅ Swap 1: $15,000 USDC → 5.2 WETH (QuickSwap)
- ✅ Swap 2: 5.2 WETH → $15,008.18 USDC (SushiSwap)
- ✅ Repaid: $15,000 USDC + $0 fee (Balancer)
- ✅ Profit: $8.18 sent to your wallet
- ✅ Gas: ~$0.32 (paid from your wallet)
- ✅ Net: $7.86 pure profit!

---

## 🔁 Continuous Loop

```python
import time

while True:
    try:
        print(f"\n{'='*80}")
        print(f"⏰ Starting scan at {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*80}\n")

        # 1. Check gas (auto-tuning)
        # 2. Find opportunities
        opportunities = mev_module.find_graph_opportunities(pol_price_usd=0.40)

        # 3. Route & execute
        for opp in opportunities:
            result = mev_module.analyze_and_route_opportunity(opp)
            if result['should_execute']:
                # Execute trade here...
                pass

        # 4. Wait before next scan
        print(f"\n💤 Sleeping 60s until next scan...")
        time.sleep(60)

    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        break
    except Exception as e:
        print(f"❌ Error: {e}")
        time.sleep(10)
```

---

## 🎯 Key Decision Points

### **Decision 1: Should I search? (Gas Tuner)**
- ❌ If 2-hop gas > $2 → Don't even search
- ✅ If gas is cheap → Search 4-hop paths
- ✅ If gas is normal → Search 3-hop paths
- ✅ If gas is expensive → Search 2-hop only

### **Decision 2: Which execution method? (Router)**
- ✅ 2-hop + profitable → Use Balancer flash loan (0% fee)
- ⚠️ 2-hop + token not on Balancer → Use Aave (0.09% fee)
- ❌ 3-hop → Skip (contract doesn't support)
- ❌ Not profitable after gas → Skip

### **Decision 3: Should I execute? (Final check)**
- ✅ Net profit > $1 → YES
- ✅ Pool has enough liquidity → YES
- ❌ Net profit < threshold → NO
- ❌ Gas too expensive → NO

---

## 📊 Summary

1. **Gas Tuner**: Adjusts search based on gas costs
2. **Graph Finder**: Finds opportunities with tuned params
3. **Execution Router**: Picks best execution method
4. **Flash Contract**: Executes 2-hop arbitrage on-chain
5. **Profit**: Sent to your wallet!

All of this runs **automatically** when you call:
```python
opportunities = mev_module.find_graph_opportunities()
```

The routing happens when you call:
```python
result = mev_module.analyze_and_route_opportunity(opp)
```

**Zero modifications to your contract needed!** 🎉
