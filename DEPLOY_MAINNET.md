# 🚀 Mainnet Deployment Guide - Flash Loan Arbitrage Bot

**⚡ ZERO CAPITAL RISK - Flash loans auto-revert if unprofitable!**

You're only spending gas (~$0.20-0.50 per attempt). No capital needed in the contract.

---

## 📍 Mainnet Contract Addresses

**Polygon Mainnet:**
```
Aave V3 Pool:      0x794a61358D6845594F94dc1DB02A252b5b4814aD
Balancer V2 Vault: 0xBA12222222228d8Ba445958a75a0704d566BF2C8
```

---

## 🚀 Quick Deploy (5 minutes)

### Step 1: Deploy Contract via Remix

1. **Open Remix:** https://remix.ethereum.org/
2. **Create file:** `FlashloanTradingBot.sol`
3. **Copy contract:** From `remix bot/flashloanbot.sol`
4. **Compile:**
   - Compiler: `0.8.20`
   - Optimization: `200 runs`
   - Click "Compile"

5. **Connect MetaMask:**
   - Deploy tab → Environment: `Injected Provider - MetaMask`
   - **Switch to Polygon Mainnet**
   - Ensure you have ~$1 POL for gas

6. **Deploy:**
   - Constructor parameters:
     ```
     _aave:     0x794a61358D6845594F94dc1DB02A252b5b4814aD
     _balancer: 0xBA12222222228d8Ba445958a75a0704d566BF2C8
     ```
   - Click "Deploy"
   - Approve in MetaMask (~$0.50 gas)
   - Wait for confirmation

7. **Copy Address:**
   - Copy deployed contract address
   - Save it!

---

### Step 2: Configure `.env`

```bash
# === MAINNET CONTRACT ===
FLASHLOAN_CONTRACT_ADDRESS=0x...  # YOUR DEPLOYED ADDRESS

# === WALLET ===
PRIVATE_KEY=0x...  # Your wallet private key (KEEP SECRET!)

# === RPC ENDPOINTS (for redundancy) ===
PREMIUM_ALCHEMY_KEY=...  # Your Alchemy key (premium tracking)
ALCHEMY_API_KEY=...      # Regular Alchemy (fallback)
INFURA_API_KEY=...       # Infura (additional redundancy)
```

---

### Step 3: Authorize Your Wallet

**Quick method - In Remix:**

1. In Remix, find your deployed contract
2. Expand the contract functions
3. Find `authorizeCaller`
4. Enter:
   - `caller`: Your wallet address (same as deployed from)
   - `status`: `true`
5. Click "transact"
6. Approve in MetaMask
7. Done! ✅

**Or use Python script below** ↓

---

## 🐍 Python Quick Setup Script

Save as `setup_contract.py`:

```python
#!/usr/bin/env python3
"""Quick setup script for mainnet deployment"""

from web3 import Web3
from eth_account import Account
from abis import FLASHLOAN_CONTRACT_ABI
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
contract_address = os.getenv('FLASHLOAN_CONTRACT_ADDRESS')
private_key = os.getenv('PRIVATE_KEY')
alchemy_key = os.getenv('PREMIUM_ALCHEMY_KEY') or os.getenv('ALCHEMY_API_KEY')

if not all([contract_address, private_key, alchemy_key]):
    print("❌ Missing environment variables!")
    print("   Set FLASHLOAN_CONTRACT_ADDRESS, PRIVATE_KEY, and ALCHEMY_API_KEY in .env")
    exit(1)

# Connect to Polygon mainnet
rpc_url = f"https://polygon-mainnet.g.alchemy.com/v2/{alchemy_key}"
w3 = Web3(Web3.HTTPProvider(rpc_url))

if not w3.is_connected():
    print("❌ Failed to connect to Polygon mainnet")
    exit(1)

print(f"✅ Connected to Polygon Mainnet (Chain ID: {w3.eth.chain_id})")

# Get account
account = Account.from_key(private_key)
print(f"📍 Wallet: {account.address}")

# Check balance
balance = w3.eth.get_balance(account.address)
balance_pol = balance / 1e18
print(f"💰 Balance: {balance_pol:.4f} POL")

if balance_pol < 0.1:
    print(f"⚠️  WARNING: Low POL balance. Add at least 0.5 POL for gas.")

# Load contract
contract = w3.eth.contract(
    address=w3.to_checksum_address(contract_address),
    abi=FLASHLOAN_CONTRACT_ABI
)

# Check owner
try:
    owner = contract.functions.owner().call()
    print(f"👑 Contract owner: {owner}")

    if owner.lower() != account.address.lower():
        print(f"❌ You are not the owner! Cannot authorize.")
        exit(1)
except Exception as e:
    print(f"❌ Failed to read contract: {e}")
    print(f"   Is FLASHLOAN_CONTRACT_ADDRESS correct?")
    exit(1)

# Authorize wallet
print(f"\n🔐 Authorizing {account.address}...")

try:
    tx = contract.functions.authorizeCaller(
        w3.to_checksum_address(account.address),
        True
    ).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'maxFeePerGas': w3.eth.gas_price * 2,
        'maxPriorityFeePerGas': w3.to_wei(30, 'gwei'),
        'chainId': 137
    })

    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"📤 TX sent: {tx_hash.hex()}")

    print(f"⏳ Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt['status'] == 1:
        print(f"✅ SUCCESS! Wallet authorized!")
        print(f"   Block: {receipt['blockNumber']}")
        print(f"   Gas used: {receipt['gasUsed']:,}")
        print(f"   View: https://polygonscan.com/tx/{tx_hash.hex()}")
    else:
        print(f"❌ Transaction failed!")

except Exception as e:
    print(f"❌ Authorization failed: {e}")
    exit(1)

print(f"\n🎉 Setup complete! Your bot is ready to trade.")
print(f"\nNext steps:")
print(f"1. Run: python polygon_arb_bot.py")
print(f"2. Select option 1 (Single Scan)")
print(f"3. Review opportunities")
print(f"4. Let the bot execute automatically!")
```

Run it:
```bash
python setup_contract.py
```

---

## ✅ Test the Bot

Quick test to verify everything works:

```python
#!/usr/bin/env python3
"""Test bot connection"""

from polygon_arb_bot import PolygonArbBot

print("🤖 Initializing bot...")
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,
    auto_execute=False
)

if bot.flashloan_contract:
    print("\n✅ CONTRACT CONNECTED!")
    print(f"   Address: {bot.flashloan_contract.address}")
    print(f"   Wallet: {bot.wallet_address}")

    # Check owner
    owner = bot.flashloan_contract.functions.owner().call()
    print(f"   Owner: {owner}")

    # Check balance
    w3 = bot.rpc_manager.get_web3()
    balance = w3.eth.get_balance(bot.wallet_address)
    print(f"   Balance: {balance / 1e18:.4f} POL")

    print(f"\n🎉 READY TO TRADE!")
    print(f"   Only cost: ~$0.20-0.50 gas per trade")
    print(f"   Zero capital risk (flash loans auto-revert)")
else:
    print("\n❌ Contract not connected")
    print("   1. Deploy contract via Remix")
    print("   2. Set FLASHLOAN_CONTRACT_ADDRESS in .env")
    print("   3. Run setup_contract.py")
```

---

## 🎯 Start Trading

### Manual Mode (Recommended First):

```python
from polygon_arb_bot import PolygonArbBot

# Initialize
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,
    auto_execute=False  # Manual approval
)

# Run a scan
opportunities = bot.run_single_scan()

# If opportunities found, bot will show them
# You can review and approve each one
```

### Auto Mode (After Testing):

```python
from polygon_arb_bot import PolygonArbBot

# Initialize with auto-execution
bot = PolygonArbBot(
    min_tvl=3000,
    scan_interval=60,
    auto_execute=True  # ⚡ AUTO-EXECUTE!
)

# Run continuous scanning
# Bot will execute profitable trades automatically
bot.run_continuous()
```

Or use the interactive menu:
```bash
python polygon_arb_bot.py
```

---

## 💰 Understanding Gas Costs

**Per-trade costs on Polygon:**
- Gas limit: ~400,000 gas
- Gas price: ~40 gwei (Polygon)
- POL price: ~$0.40
- **Total: $0.20-0.50 per trade**

**Daily budget:**
- 10 trades/day = $2-5 in gas
- 50 trades/day = $10-25 in gas
- 100 trades/day = $20-50 in gas

**Profit threshold:**
- Bot only executes if profit > $1 after gas
- With $0.30 gas, need $1.30 gross profit
- Realistic: $2-10 profit per successful trade

---

## 🛡️ Safety Features (All Active)

✅ **Gas estimation before execution** - Rejects unprofitable trades
✅ **Minimum profit thresholds** - Only trades if profit > $1
✅ **Rate limiting** - Max 10 trades/min, $5 gas/hour
✅ **Kill switch** - Stops after 10 consecutive failures
✅ **Flash loan safety** - Trades auto-revert if unprofitable
✅ **MEV protection** - Private transactions via Alchemy
✅ **RPC redundancy** - 15+ endpoints with auto-failover

---

## 📊 Expected Performance

**Realistic expectations:**

| Metric | Conservative | Optimistic |
|--------|--------------|------------|
| Opportunities/day | 5-20 | 20-100 |
| Success rate | 50-70% | 70-85% |
| Profit per trade | $1-5 | $5-20 |
| Daily gas cost | $2-10 | $10-30 |
| Daily net profit | $0-20 | $20-100 |

**Key factors:**
- Market volatility (more = more opportunities)
- Gas price (lower = more profitable trades)
- Competition (other bots)
- Pool liquidity (higher = less slippage)

---

## 🔧 Advanced Configuration

Optimize your `.env` for better results:

```bash
# Aggressive settings (more trades)
MIN_PROFIT_AFTER_FEES=0.75      # Lower threshold
MAX_SLIPPAGE_PCT=3.0            # Allow higher slippage
COOLDOWN_SECONDS=0.05           # Faster execution

# Conservative settings (higher quality)
MIN_PROFIT_AFTER_FEES=2.00      # Higher threshold
MAX_SLIPPAGE_PCT=1.5            # Lower slippage
MIN_POOL_TVL=10000              # Only high-liquidity pools

# Rate limits
MAX_TRADES_PER_MINUTE=10        # Prevent spam
MAX_GAS_SPENT_PER_HOUR=10.0     # Budget control
```

---

## 📈 Monitoring Your Bot

### View Statistics:

```python
# In auto-execution mode
if bot.auto_executor:
    stats = bot.auto_executor.get_stats()
    print(f"📊 Performance:")
    print(f"   Total trades: {stats['total_trades']}")
    print(f"   Successful: {stats['successful_trades']}")
    print(f"   Success rate: {stats['success_rate']:.1f}%")
    print(f"   Total profit: ${stats['total_profit']:.2f}")
    print(f"   Gas spent: ${stats['total_gas_spent']:.2f}")
    print(f"   Net P&L: ${stats['net_profit']:.2f}")
```

### Withdraw Profits:

```python
from web3 import Web3
from eth_account import Account
from abis import FLASHLOAN_CONTRACT_ABI

# Connect
w3 = Web3(Web3.HTTPProvider('YOUR_RPC'))
contract = w3.eth.contract(address='CONTRACT_ADDRESS', abi=FLASHLOAN_CONTRACT_ABI)

# Withdraw USDC profits (example)
usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

tx = contract.functions.withdrawToken(usdc_address).build_transaction({
    'from': 'YOUR_ADDRESS',
    'nonce': w3.eth.get_transaction_count('YOUR_ADDRESS'),
    'gas': 100000,
    'maxFeePerGas': w3.eth.gas_price,
    'maxPriorityFeePerGas': w3.to_wei(30, 'gwei'),
})

# Sign and send...
```

---

## 🎉 You're Ready!

**Summary:**
1. ✅ Deploy contract to Polygon mainnet (5 min)
2. ✅ Update `.env` with contract address
3. ✅ Run `setup_contract.py` to authorize
4. ✅ Start bot with `python polygon_arb_bot.py`
5. ✅ Watch it find and execute profitable trades!

**Remember:**
- 💰 Zero capital risk (flash loans)
- ⛽ Only cost is gas (~$0.20-0.50/trade)
- 🎯 Bot only trades if profit > $1 after gas
- 🛡️ All safety features active
- 📊 Track performance in real-time

**Need help? Check:**
- `CODE_REVIEW_REPORT.md` - Detailed analysis
- `INTEGRATION_GUIDE.md` - Complete documentation
- Smart contract: `remix bot/flashloanbot.sol`

**Good luck and happy arbitraging! 🚀**
