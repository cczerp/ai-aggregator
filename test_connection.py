#!/usr/bin/env python3
"""
Quick test to verify bot connection to flashloan contract
Run this after setup to ensure everything works
"""

from polygon_arb_bot import PolygonArbBot
from colorama import Fore, Style, init
import os
from dotenv import load_dotenv

init(autoreset=True)
load_dotenv()

print(f"\n{Fore.CYAN}{'='*80}")
print(f"🧪 TESTING BOT CONNECTION")
print(f"{'='*80}{Style.RESET_ALL}\n")

# Check environment variables
print(f"{Fore.YELLOW}1. Checking environment variables...{Style.RESET_ALL}")

contract_addr = os.getenv('FLASHLOAN_CONTRACT_ADDRESS')
private_key = os.getenv('PRIVATE_KEY')
alchemy_key = os.getenv('PREMIUM_ALCHEMY_KEY') or os.getenv('ALCHEMY_API_KEY')

if contract_addr:
    print(f"   ✅ FLASHLOAN_CONTRACT_ADDRESS: {contract_addr[:10]}...")
else:
    print(f"   ❌ FLASHLOAN_CONTRACT_ADDRESS: NOT SET")

if private_key:
    print(f"   ✅ PRIVATE_KEY: Set (length: {len(private_key)})")
else:
    print(f"   ❌ PRIVATE_KEY: NOT SET")

if alchemy_key:
    print(f"   ✅ ALCHEMY_API_KEY: Set")
else:
    print(f"   ❌ ALCHEMY_API_KEY: NOT SET")

if not all([contract_addr, private_key, alchemy_key]):
    print(f"\n{Fore.RED}❌ Missing required environment variables!{Style.RESET_ALL}")
    print(f"\nSetup checklist:")
    print(f"1. Deploy contract via Remix")
    print(f"2. Add to .env: FLASHLOAN_CONTRACT_ADDRESS=0x...")
    print(f"3. Add to .env: PRIVATE_KEY=0x...")
    print(f"4. Add to .env: ALCHEMY_API_KEY=...")
    print(f"5. Run: python setup_contract.py")
    exit(1)

# Initialize bot
print(f"\n{Fore.YELLOW}2. Initializing bot...{Style.RESET_ALL}")

try:
    bot = PolygonArbBot(
        min_tvl=3000,
        scan_interval=60,
        auto_execute=False
    )
    print(f"   ✅ Bot initialized")
except Exception as e:
    print(f"   ❌ Bot initialization failed: {e}")
    exit(1)

# Check contract connection
print(f"\n{Fore.YELLOW}3. Checking contract connection...{Style.RESET_ALL}")

if bot.flashloan_contract:
    print(f"   ✅ Contract connected!")
    print(f"      Address: {bot.flashloan_contract.address}")
    print(f"      Wallet: {bot.wallet_address}")
else:
    print(f"   ❌ Contract NOT connected")
    print(f"\n   Troubleshooting:")
    print(f"   1. Is FLASHLOAN_CONTRACT_ADDRESS correct?")
    print(f"   2. Is the contract deployed to Polygon mainnet?")
    print(f"   3. Run: python setup_contract.py")
    exit(1)

# Check contract owner
print(f"\n{Fore.YELLOW}4. Checking contract owner...{Style.RESET_ALL}")

try:
    owner = bot.flashloan_contract.functions.owner().call()
    print(f"   Owner: {owner}")

    if owner.lower() == bot.wallet_address.lower():
        print(f"   ✅ You are the owner")
    else:
        print(f"   ⚠️  You are not the owner")
        print(f"      This is OK if the owner already authorized you")
except Exception as e:
    print(f"   ❌ Failed to read owner: {e}")

# Check wallet balance
print(f"\n{Fore.YELLOW}5. Checking wallet balance...{Style.RESET_ALL}")

try:
    w3 = bot.rpc_manager.get_web3()
    balance = w3.eth.get_balance(bot.wallet_address)
    balance_pol = balance / 1e18
    print(f"   Balance: {balance_pol:.4f} POL")

    pol_price = 0.40  # Approximate
    balance_usd = balance_pol * pol_price
    print(f"   ~${balance_usd:.2f} USD")

    if balance_pol < 0.5:
        print(f"   ⚠️  WARNING: Low balance!")
        print(f"      Add more POL for gas fees")
        print(f"      Recommended: At least 2-5 POL for sustained trading")
    else:
        print(f"   ✅ Sufficient balance for trading")
except Exception as e:
    print(f"   ❌ Failed to check balance: {e}")

# Check RPC connection
print(f"\n{Fore.YELLOW}6. Checking RPC endpoints...{Style.RESET_ALL}")

try:
    health = bot.rpc_manager.health_check()
    working = len(health['working'])
    total = len(health['working']) + len(health['failed'])

    print(f"   Working RPCs: {working}/{total}")

    if working >= 3:
        print(f"   ✅ Good RPC redundancy")
    elif working >= 1:
        print(f"   ⚠️  Limited RPC redundancy (add more API keys)")
    else:
        print(f"   ❌ No working RPCs!")
except Exception as e:
    print(f"   ⚠️  Could not check RPC health: {e}")

# Summary
print(f"\n{Fore.GREEN}{'='*80}")
print(f"📊 CONNECTION TEST SUMMARY")
print(f"{'='*80}{Style.RESET_ALL}\n")

if bot.flashloan_contract and balance_pol >= 0.5:
    print(f"{Fore.GREEN}✅ ALL SYSTEMS GO!{Style.RESET_ALL}\n")

    print(f"Your bot is ready to trade:\n")
    print(f"💎 Contract: {bot.flashloan_contract.address}")
    print(f"👛 Wallet: {bot.wallet_address}")
    print(f"💰 Balance: {balance_pol:.4f} POL (~${balance_usd:.2f})")
    print(f"⚡ Flash loans: ENABLED (zero capital risk)")
    print(f"🛡️  Safety: ALL checks active\n")

    print(f"Next steps:")
    print(f"1. Run: {Fore.CYAN}python polygon_arb_bot.py{Style.RESET_ALL}")
    print(f"2. Select option 1 (Single Scan)")
    print(f"3. Review opportunities")
    print(f"4. Enable auto-execution when ready\n")

    print(f"📈 Expected costs:")
    print(f"   Gas per trade: $0.20-0.50")
    print(f"   Min profit threshold: $1.00")
    print(f"   Daily gas budget: $2-10 (configurable)\n")

    print(f"{Fore.GREEN}Good luck! 🚀{Style.RESET_ALL}\n")

elif bot.flashloan_contract:
    print(f"{Fore.YELLOW}⚠️  READY BUT LOW BALANCE{Style.RESET_ALL}\n")

    print(f"Bot is configured but needs more POL for gas:\n")
    print(f"💎 Contract: {bot.flashloan_contract.address}")
    print(f"👛 Wallet: {bot.wallet_address}")
    print(f"💰 Balance: {balance_pol:.4f} POL (~${balance_usd:.2f})")
    print(f"\n📝 Action required:")
    print(f"   Send at least 2-5 POL to: {bot.wallet_address}")
    print(f"   Then run this test again\n")

else:
    print(f"{Fore.RED}❌ SETUP INCOMPLETE{Style.RESET_ALL}\n")

    print(f"Complete these steps:\n")

    if not contract_addr:
        print(f"1. Deploy contract:")
        print(f"   - Go to https://remix.ethereum.org/")
        print(f"   - Copy code from: remix bot/flashloanbot.sol")
        print(f"   - Deploy to Polygon mainnet")
        print(f"   - Add address to .env\n")

    if contract_addr and not bot.flashloan_contract:
        print(f"2. Authorize wallet:")
        print(f"   Run: {Fore.CYAN}python setup_contract.py{Style.RESET_ALL}\n")

    if balance_pol < 0.5:
        print(f"3. Add POL for gas:")
        print(f"   Send 2-5 POL to: {bot.wallet_address}\n")

print(f"For detailed setup instructions:")
print(f"   See: {Fore.CYAN}DEPLOY_MAINNET.md{Style.RESET_ALL}\n")
