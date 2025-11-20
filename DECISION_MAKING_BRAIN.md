# The Bot's "Brain" - Where Decisions Are Made

## 🧠 Current Decision-Making Flow

Here's **exactly** what decides what to look at, calculate, and when to trade:

---

## **Level 1: What to Look At** (Search Strategy)

### **File: `dynamic_gas_tuner.py`**
**Function: `get_optimal_params()`**

```python
# Line 62-130
def get_optimal_params(self, pol_price_usd: float = 0.40):
    gas_cost_per_hop = self._get_gas_cost_per_hop(pol_price_usd)

    # DECISION LOGIC:
    if gas_cost_per_hop < 0.20:
        # CHEAP GAS → Look at 4-hop paths
        return GraphSearchParams(
            max_hops=4,
            test_amounts_usd=[2000, 10000, 50000],
            max_paths=100
        )
    elif gas_cost_per_hop < 0.40:
        # NORMAL GAS → Look at 3-hop paths
        return GraphSearchParams(
            max_hops=3,
            test_amounts_usd=[5000, 15000, 50000],
            max_paths=75
        )
    else:
        # EXPENSIVE GAS → Only 2-hop paths
        return GraphSearchParams(
            max_hops=2,
            test_amounts_usd=[10000, 25000, 100000],
            max_paths=50
        )
```

**What it decides:**
- ✅ How many hops to search (2, 3, or 4)
- ✅ What trade sizes to test
- ✅ How many paths to explore
- ✅ Minimum pool liquidity required

**When it decides:** Every scan (every 60 seconds)

---

## **Level 2: What to Calculate** (Opportunity Evaluation)

### **File: `advanced mev module.py`**
**Class: `GraphArbitrageFinder`**
**Function: `find_all_opportunities()` - Line 508-576**

```python
def find_all_opportunities(self, pools_data, pol_price_usd=0.40):
    # Get tuned parameters from Level 1
    if self.gas_tuner:
        params = self.gas_tuner.get_optimal_params(pol_price_usd)
        max_hops = params.max_hops
        test_amounts = params.test_amounts_usd
        max_paths = params.max_paths

    # Build graph of all possible swaps
    self.build_graph(pools_data)

    opportunities = []

    # DECISION: Which tokens to start from
    for base_token in ['USDC', 'WETH', 'WPOL']:

        # DECISION: Find all cycles back to base token
        paths = self.find_triangular_paths(
            base_token,
            max_hops=max_hops,  # ← From gas tuner
            max_paths=max_paths  # ← From gas tuner
        )

        # DECISION: Calculate profit for each path
        for path in paths:
            for amount in test_amounts:  # ← From gas tuner
                result = self.calculate_path_profit(path, amount, pools_data)

                # DECISION: Is it profitable enough?
                if result and result['profit_usd'] > min_profit:
                    opportunities.append(result)

    return opportunities
```

**What it decides:**
- ✅ Which token pairs to examine
- ✅ Which paths to calculate
- ✅ What trade sizes to simulate
- ✅ Which opportunities pass profit threshold

**When it decides:** Every scan, after gas tuning

---

## **Level 3: How to Execute** (Execution Method)

### **File: `execution_router.py`**
**Class: `ExecutionRouter`**
**Function: `decide_execution_path()` - Line 73-247**

```python
def decide_execution_path(self, opportunity, pol_price_usd=0.40, has_capital=False):
    num_hops = len(opportunity['hops'])
    gross_profit = opportunity['gross_profit_usd']
    trade_size = opportunity['trade_size_usd']

    # DECISION: Can we use our 2-hop flash loan contract?
    if num_hops == 2:

        # DECISION: Try Balancer (0% fee) first
        gas_cost_balancer = self._calculate_gas_cost_usd(400000, pol_price_usd)
        flash_fee_balancer = 0  # FREE!
        net_profit_balancer = gross_profit - gas_cost_balancer - flash_fee_balancer

        if net_profit_balancer >= self.min_profit_usd:
            return ExecutionDecision(
                path=FLASH_LOAN_2HOP,
                provider='balancer',
                net_profit=net_profit_balancer
            )

        # DECISION: Try Aave (0.09% fee) if Balancer fails
        flash_fee_aave = trade_size * 0.0009
        net_profit_aave = gross_profit - gas_cost_aave - flash_fee_aave

        if net_profit_aave >= self.min_profit_usd:
            return ExecutionDecision(
                path=FLASH_LOAN_2HOP,
                provider='aave',
                net_profit=net_profit_aave
            )

    # DECISION: Skip if not 2-hop or not profitable
    return ExecutionDecision(path=SKIP, reason="Not profitable or not 2-hop")
```

**What it decides:**
- ✅ Flash loan provider (Balancer vs Aave)
- ✅ Whether profit covers gas + fees
- ✅ Execute or skip

**When it decides:** For each opportunity found in Level 2

---

## **Level 4: Final Safety Check** (Should We Really Execute?)

### **File: `auto_executor.py`**
**Class: `FlashLoanExecutor`**
**Function: `check_execution_safety()` - Line 98-157**

```python
def check_execution_safety(self, opportunity):
    # DECISION: Kill switch active?
    if not self.limits.enabled:
        return False, "Kill switch activated"

    # DECISION: Too many consecutive failures?
    if self.consecutive_failures >= 10:
        self.limits.enabled = False
        return False, "Kill switch: 10 consecutive failures"

    # DECISION: Are we rate limited?
    now = time.time()
    self.trades_this_minute = [t for t in self.trades_this_minute if now - t < 60]
    if len(self.trades_this_minute) >= 10:
        return False, "Rate limit: 10 trades/min"

    # DECISION: Have we spent too much gas this hour?
    hourly_gas = sum(g[1] for g in self.gas_spent_this_hour)
    if hourly_gas >= 5.0:
        return False, "Gas limit: $5.00 spent this hour"

    # DECISION: Is profit after gas still good?
    net_profit = opportunity['net_profit_usd'] - gas_cost - flash_fee
    if net_profit < 1.00:
        return False, f"Net profit ${net_profit:.2f} < min $1.00"

    # DECISION: Is pool liquidity sufficient?
    min_tvl = min(opportunity['buy_tvl_usd'], opportunity['sell_tvl_usd'])
    if min_tvl < 5000:
        return False, f"Pool TVL ${min_tvl:,.0f} < min $5,000"

    return True, "All safety checks passed"
```

**What it decides:**
- ✅ Kill switch status
- ✅ Rate limiting enforcement
- ✅ Gas budget enforcement
- ✅ Final profit verification
- ✅ Pool liquidity checks

**When it decides:** Right before execution

---

## 🎯 Summary: The Complete Decision Chain

```
EVERY 60 SECONDS:

┌─────────────────────────────────────────────────────────────┐
│ Level 1: DYNAMIC GAS TUNER                                  │
│ Decides: What to search for                                 │
│ ├─ Check gas price                                          │
│ ├─ IF gas cheap → Search 4-hop paths, $1 min profit        │
│ ├─ IF gas normal → Search 3-hop paths, $2 min profit       │
│ └─ IF gas expensive → Search 2-hop only, $3 min profit     │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Level 2: GRAPH ARBITRAGE FINDER                             │
│ Decides: What to calculate                                  │
│ ├─ Build graph of all token pairs                           │
│ ├─ Find cycles from USDC, WETH, WPOL                       │
│ ├─ Test each path with tuned trade sizes                    │
│ └─ Keep paths with profit > threshold                       │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Level 3: EXECUTION ROUTER                                   │
│ Decides: How to execute                                     │
│ ├─ Is it 2-hop? → Can use flash loan contract              │
│ ├─ Try Balancer (0% fee) first                             │
│ ├─ Try Aave (0.09% fee) if needed                          │
│ └─ Return: Execute via X or Skip                            │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│ Level 4: AUTO EXECUTOR (Safety)                             │
│ Decides: Should we really execute?                          │
│ ├─ Check kill switch                                        │
│ ├─ Check rate limits                                        │
│ ├─ Check gas budget                                         │
│ ├─ Verify profit still good                                 │
│ └─ Return: GO or NO-GO                                      │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
           [EXECUTE TRADE]
```

---

## 🔢 Current Decision Parameters (Hardcoded)

### **Gas Tuner** (`dynamic_gas_tuner.py:62-130`)
```python
# Gas thresholds (HARDCODED)
if gas_cost_per_hop < 0.20:    # Cheap
if gas_cost_per_hop < 0.40:    # Normal
else:                           # Expensive

# Trade amounts (HARDCODED)
cheap_gas: [2000, 10000, 50000]
normal_gas: [5000, 15000, 50000]
expensive_gas: [10000, 25000, 100000]

# Hop limits (HARDCODED)
cheap_gas: max_hops=4
normal_gas: max_hops=3
expensive_gas: max_hops=2
```

### **Execution Router** (`execution_router.py:73-247`)
```python
# Gas costs (HARDCODED)
flash_loan_2hop_balancer: 400000 gas
flash_loan_2hop_aave: 450000 gas
direct_2hop: 250000 gas

# Flash loan fees (HARDCODED)
balancer: 0.0%
aave: 0.09%

# Min profit (HARDCODED)
min_profit_usd: $1.00
```

### **Auto Executor** (`auto_executor.py:32-60`)
```python
# Safety limits (HARDCODED, but configurable via env)
min_profit_after_fees: $1.00
max_trades_per_minute: 10
max_gas_spent_per_hour: $5.00
kill_on_consecutive_failures: 10
min_pool_tvl: $5,000
max_slippage_pct: 3.0%
```

---

## 🤔 The Problem: These Are All Static Rules!

**Current "intelligence":**
- ❌ Gas thresholds are hardcoded
- ❌ Trade sizes are fixed
- ❌ No learning from past trades
- ❌ No pattern recognition
- ❌ No adaptation to market conditions
- ❌ Same strategy every time

**It's like a calculator, not a brain!**

The bot will **never** get smarter. It uses the same rules forever, regardless of:
- Which trades were profitable
- Which trades failed
- Market volatility
- Time of day
- Day of week
- Pool behavior patterns

---

## 🧪 What Could a Neural Network Do?

A neural network could **learn and optimize** these decisions:

### **1. Optimal Trade Sizing** (Reinforcement Learning)
```
Input:
- Pool reserves
- Historical volatility
- Time of day
- Gas price
- Recent success rate

Neural Network → Output:
- Optimal trade size for THIS specific opportunity
- Predicted slippage
- Success probability

Example:
"Pool USDC/WETH on QuickSwap has low volatility at 3am UTC.
I've learned that $25k trades succeed 87% of the time here.
Recommend: $25k (not the default $15k)"
```

### **2. Gas Price Prediction** (Time Series LSTM)
```
Input:
- Historical gas prices (last 24 hours)
- Time of day
- Day of week
- Pending transaction count

Neural Network → Output:
- Predicted gas price in 5 minutes
- Confidence interval

Example:
"Gas is 35 gwei now, but my model predicts 28 gwei in 5 minutes.
Decision: Wait 5 minutes before executing."
```

### **3. Opportunity Scoring** (Classification)
```
Input:
- DEX pair
- Token pair
- Gross profit
- Pool TVL
- Time since last trade on this pool
- Historical success rate on this path
- Current market volatility

Neural Network → Output:
- Probability of successful execution (0-100%)
- Risk score

Example:
"USDC → WETH → USDC on QuickSwap/SushiSwap:
- Predicted success: 92%
- Risk: LOW
- Recommendation: EXECUTE"

vs.

"USDC → QUICK → WPOL → USDC on complex path:
- Predicted success: 34%
- Risk: HIGH
- Recommendation: SKIP (even though profit looks good)"
```

### **4. Dynamic Parameter Tuning** (Reinforcement Learning)
```
Input:
- Current gas price
- Time of day
- Recent success rate
- Total profit this hour
- Failed trade count

Neural Network → Output:
- Optimal max_hops
- Optimal min_profit threshold
- Optimal trade sizes

Example:
"It's 2am UTC, gas is cheap, and I've had 8 successful trades in the last hour.
My model says: Increase max_hops to 4, lower min_profit to $0.75.
This will find more opportunities while risk is low."
```

### **5. Path Quality Prediction** (Graph Neural Network)
```
Input:
- Token path: [USDC, WETH, WPOL, USDC]
- DEX path: [QuickSwap, Uniswap, SushiSwap]
- Pool liquidity for each hop
- Historical success rate for each pool
- Network topology features

Neural Network → Output:
- Quality score for this path
- Predicted profit accuracy

Example:
"Path USDC → WETH → WPOL → USDC:
- Quality score: 0.85/1.0
- Profit prediction confidence: 89%
- Historical success on similar paths: 78%
- Recommendation: Good path, execute if profit > $2"
```

---

## 🎯 Where Neural Networks Would Go

I can create a new file showing exactly where to integrate ML:

1. **`ml_brain.py`** - Neural network models
2. **`ml_trainer.py`** - Training loop using trade history
3. **`trade_database.py`** - Already exists! Logs all trades
4. **Integration points** - Replace hardcoded decisions with ML predictions

Would you like me to:
1. ✅ Show you where to integrate neural networks?
2. ✅ Create a basic ML model for trade scoring?
3. ✅ Build a reinforcement learning loop?
4. ✅ Design a training pipeline using your trade history?

Let me know which aspects interest you most and I'll build it! 🧠🚀
