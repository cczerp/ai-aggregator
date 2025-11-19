#!/usr/bin/env python3
"""
Quick setup script for mainnet flashloan contract
Authorizes your wallet and verifies the setup
"""

from web3 import Web3
from eth_account import Account
from abis import FLASHLOAN_CONTRACT_ABI
import os
from dotenv import load_dotenv
from colorama import Fore, Style, init

init(autoreset=True)

print(f"\n{Fore.CYAN}{'='*80}")
print(f"🚀 FLASHLOAN CONTRACT SETUP")
print(f"{'='*80}{Style.RESET_ALL}\n")

# Load environment variables
load_dotenv()

# Configuration
contract_address = os.getenv('FLASHLOAN_CONTRACT_ADDRESS')
private_key = os.getenv('PRIVATE_KEY')
alchemy_key = os.getenv('PREMIUM_ALCHEMY_KEY') or os.getenv('ALCHEMY_API_KEY')

# Validate configuration
if not contract_address:
    print(f"{Fore.RED}❌ FLASHLOAN_CONTRACT_ADDRESS not set in .env{Style.RESET_ALL}")
    print(f"   Deploy the contract first, then add the address to .env")
    exit(1)

if not private_key:
    print(f"{Fore.RED}❌ PRIVATE_KEY not set in .env{Style.RESET_ALL}")
    print(f"   Add your wallet private key to .env")
    exit(1)

if not alchemy_key:
    print(f"{Fore.RED}❌ ALCHEMY_API_KEY not set in .env{Style.RESET_ALL}")
    print(f"   Add your Alchemy API key to .env")
    exit(1)

# Connect to Polygon mainnet
rpc_url = f"https://polygon-mainnet.g.alchemy.com/v2/{alchemy_key}"
w3 = Web3(Web3.HTTPProvider(rpc_url))

if not w3.is_connected():
    print(f"{Fore.RED}❌ Failed to connect to Polygon mainnet{Style.RESET_ALL}")
    print(f"   Check your ALCHEMY_API_KEY")
    exit(1)

chain_id = w3.eth.chain_id
if chain_id != 137:
    print(f"{Fore.YELLOW}⚠️  WARNING: Connected to chain {chain_id}, not Polygon mainnet (137){Style.RESET_ALL}")
    if chain_id == 80001:
        print(f"   Connected to Mumbai testnet - this is fine for testing!")
else:
    print(f"{Fore.GREEN}✅ Connected to Polygon Mainnet{Style.RESET_ALL}")

# Get account
try:
    account = Account.from_key(private_key)
except Exception as e:
    print(f"{Fore.RED}❌ Invalid PRIVATE_KEY: {e}{Style.RESET_ALL}")
    exit(1)

print(f"{Fore.GREEN}✅ Wallet loaded{Style.RESET_ALL}")
print(f"   Address: {account.address}")

# Check balance
balance = w3.eth.get_balance(account.address)
balance_pol = balance / 1e18
print(f"   Balance: {balance_pol:.4f} POL")

if balance_pol < 0.1:
    print(f"{Fore.YELLOW}⚠️  WARNING: Low POL balance. Add at least 0.5 POL for gas.{Style.RESET_ALL}")
    print(f"   You need POL for:")
    print(f"   - Authorization transaction (~$0.02)")
    print(f"   - Gas for arbitrage trades (~$0.20-0.50 each)")

# Load contract
print(f"\n{Fore.CYAN}📄 Loading contract...{Style.RESET_ALL}")

try:
    contract = w3.eth.contract(
        address=w3.to_checksum_address(contract_address),
        abi=FLASHLOAN_CONTRACT_ABI
    )
    print(f"{Fore.GREEN}✅ Contract loaded at {contract_address}{Style.RESET_ALL}")
except Exception as e:
    print(f"{Fore.RED}❌ Failed to load contract: {e}{Style.RESET_ALL}")
    print(f"   Is FLASHLOAN_CONTRACT_ADDRESS correct?")
    exit(1)

# Check owner
print(f"\n{Fore.CYAN}👑 Checking contract owner...{Style.RESET_ALL}")

try:
    owner = contract.functions.owner().call()
    print(f"   Contract owner: {owner}")

    if owner.lower() == account.address.lower():
        print(f"{Fore.GREEN}✅ You are the owner!{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}❌ You are NOT the owner!{Style.RESET_ALL}")
        print(f"   Your address: {account.address}")
        print(f"   Contract owner: {owner}")
        print(f"\n   You can only authorize wallets if you're the owner.")
        print(f"   If you deployed this contract, use that wallet's private key.")
        exit(1)
except Exception as e:
    print(f"{Fore.RED}❌ Failed to read contract: {e}{Style.RESET_ALL}")
    print(f"   Possible reasons:")
    print(f"   - Wrong contract address")
    print(f"   - Contract not deployed yet")
    print(f"   - Network issues")
    exit(1)

# Authorize wallet
print(f"\n{Fore.CYAN}🔐 Authorizing wallet...{Style.RESET_ALL}")
print(f"   Wallet to authorize: {account.address}")

try:
    # Build transaction
    tx = contract.functions.authorizeCaller(
        w3.to_checksum_address(account.address),
        True  # Authorize
    ).build_transaction({
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gas': 100000,
        'maxFeePerGas': int(w3.eth.gas_price * 1.5),  # 1.5x current price
        'maxPriorityFeePerGas': w3.to_wei(30, 'gwei'),
        'chainId': chain_id
    })

    # Estimate gas cost
    gas_cost_wei = tx['gas'] * tx['maxFeePerGas']
    gas_cost_pol = gas_cost_wei / 1e18
    pol_price = 0.40  # Approximate
    gas_cost_usd = gas_cost_pol * pol_price

    print(f"   Gas estimate: {tx['gas']:,} gas")
    print(f"   Cost: ~${gas_cost_usd:.4f}")

    # Sign and send
    print(f"\n   Signing transaction...")
    signed = w3.eth.account.sign_transaction(tx, private_key)

    print(f"   Broadcasting transaction...")
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    tx_hash_hex = tx_hash.hex()

    print(f"{Fore.GREEN}✅ Transaction sent!{Style.RESET_ALL}")
    print(f"   TX Hash: {tx_hash_hex}")

    if chain_id == 137:
        print(f"   View on Polygonscan: https://polygonscan.com/tx/{tx_hash_hex}")
    elif chain_id == 80001:
        print(f"   View on Mumbai: https://mumbai.polygonscan.com/tx/{tx_hash_hex}")

    print(f"\n   Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt['status'] == 1:
        print(f"\n{Fore.GREEN}{'='*80}")
        print(f"✅ SUCCESS! Wallet authorized!")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Block: {receipt['blockNumber']}")
        print(f"   Gas used: {receipt['gasUsed']:,}")
        actual_cost_pol = (receipt['gasUsed'] * receipt['effectiveGasPrice']) / 1e18
        print(f"   Actual cost: {actual_cost_pol:.6f} POL (~${actual_cost_pol * pol_price:.4f})")
    else:
        print(f"\n{Fore.RED}❌ Transaction failed!{Style.RESET_ALL}")
        print(f"   The transaction was mined but reverted on-chain")
        exit(1)

except Exception as e:
    print(f"\n{Fore.RED}❌ Authorization failed: {e}{Style.RESET_ALL}")
    import traceback
    traceback.print_exc()
    exit(1)

# Verify setup
print(f"\n{Fore.CYAN}🔍 Verifying setup...{Style.RESET_ALL}")

print(f"   ✅ Contract deployed: {contract_address}")
print(f"   ✅ Wallet authorized: {account.address}")
print(f"   ✅ Balance: {balance_pol:.4f} POL")

print(f"\n{Fore.GREEN}{'='*80}")
print(f"🎉 SETUP COMPLETE!")
print(f"{'='*80}{Style.RESET_ALL}\n")

print(f"Your bot is ready to trade! Next steps:\n")
print(f"1. Run the bot:")
print(f"   {Fore.CYAN}python polygon_arb_bot.py{Style.RESET_ALL}\n")
print(f"2. Select option 1 (Single Scan)")
print(f"3. Review opportunities")
print(f"4. Enable auto-execution when comfortable\n")

print(f"💡 Tips:")
print(f"   - Start with manual mode to learn how it works")
print(f"   - Each trade costs ~$0.20-0.50 in gas")
print(f"   - Zero capital risk - flash loans auto-revert")
print(f"   - Bot only executes if profit > $1 after gas\n")

print(f"📊 Monitor your performance:")
print(f"   - Profits accumulate in the contract")
print(f"   - Withdraw using: contract.withdrawToken(TOKEN_ADDRESS)")
print(f"   - Track stats in the bot interface\n")

print(f"{Fore.GREEN}Good luck and happy arbitraging! 🚀{Style.RESET_ALL}\n")
