# tx_builder.py - Polygon Transaction Builder (Alchemy)
from web3 import Web3
from eth_account import Account
import os
from typing import Dict, Any
from dotenv import load_dotenv
from colorama import Fore, Style

load_dotenv()

class FlashbotsTxBuilder:
    """Transaction builder for Polygon using Alchemy RPC"""
    
    def __init__(
        self,
        contract_address: str,
        private_key: str,
        rpc_url: str,
        flashbots_relay_url: str = None,  # Ignored, kept for compatibility
        chain_id: int = 137
    ):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.account = Account.from_key(private_key)
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.chain_id = chain_id
        
        # Flashloan contract ABI
        self.contract_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "address", "name": "dex1", "type": "address"},
                    {"internalType": "address", "name": "dex2", "type": "address"},
                    {"internalType": "uint8", "name": "dex1Version", "type": "uint8"},
                    {"internalType": "uint8", "name": "dex2Version", "type": "uint8"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "minProfitAmount", "type": "uint256"},
                    {"internalType": "bytes", "name": "dex1Data", "type": "bytes"},
                    {"internalType": "bytes", "name": "dex2Data", "type": "bytes"}
                ],
                "name": "executeFlashloan",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "address", "name": "dex1", "type": "address"},
                    {"internalType": "address", "name": "dex2", "type": "address"},
                    {"internalType": "uint8", "name": "dex1Version", "type": "uint8"},
                    {"internalType": "uint8", "name": "dex2Version", "type": "uint8"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "minProfitAmount", "type": "uint256"},
                    {"internalType": "bytes", "name": "dex1Data", "type": "bytes"},
                    {"internalType": "bytes", "name": "dex2Data", "type": "bytes"}
                ],
                "name": "executeBalancerFlashloan",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        self.contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=self.contract_abi
        )
        
        print(f"✅ TX Builder initialized (Alchemy)")
        print(f"   Contract: {self.contract_address}")
        print(f"   Wallet: {self.account.address}")
        print(f"   Chain: Polygon (ID: {self.chain_id})")
        
        try:
            balance = self.w3.eth.get_balance(self.account.address)
            print(f"   Balance: {balance / 1e18:.4f} POL")
        except:
            print(f"   Balance: Unable to fetch")

    def send_arbitrage_tx(
        self,
        token_in_address: str,
        token_out_address: str,
        dex1_address: str,
        dex2_address: str,
        dex1_version: int,
        dex2_version: int,
        amount_in_wei: int,
        min_profit_wei: int,
        dex1_data: bytes = b'',
        dex2_data: bytes = b'',
        use_flashbots: bool = False,  # Ignored on Polygon
        use_balancer: bool = False,
        bot_source: str = "polygon-bot"
    ) -> Dict[str, Any]:
        """Send arbitrage transaction via Alchemy RPC"""
        
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🚀 PREPARING TRANSACTION")
        print(f"{'='*80}{Style.RESET_ALL}")
        
        # Checksummed addresses
        token_in = Web3.to_checksum_address(token_in_address)
        token_out = Web3.to_checksum_address(token_out_address)
        dex1 = Web3.to_checksum_address(dex1_address)
        dex2 = Web3.to_checksum_address(dex2_address)
        
        print(f"   Token In:  {token_in}")
        print(f"   Token Out: {token_out}")
        print(f"   DEX 1:     {dex1}")
        print(f"   DEX 2:     {dex2}")
        print(f"   Amount:    {amount_in_wei:,} wei")
        print(f"   Min Profit: {min_profit_wei:,} wei")
        
        # Get current gas prices (Polygon)
        try:
            gas_price = self.w3.eth.gas_price
            # Add 10% buffer for faster inclusion
            gas_price = int(gas_price * 1.1)
            
            print(f"   Gas Price: {gas_price / 1e9:.2f} gwei")
        except Exception as e:
            print(f"{Fore.YELLOW}   Warning: Could not fetch gas price, using default{Style.RESET_ALL}")
            gas_price = Web3.to_wei(50, 'gwei')  # Fallback
        
        # Get nonce
        nonce = self.w3.eth.get_transaction_count(self.account.address, 'pending')
        
        # Choose flashloan provider
        function_name = "executeBalancerFlashloan" if use_balancer else "executeFlashloan"
        print(f"   Provider:  {'Balancer' if use_balancer else 'Aave'}")
        
        # Build transaction
        try:
            if use_balancer:
                tx = self.contract.functions.executeBalancerFlashloan(
                    token_in,
                    token_out,
                    dex1,
                    dex2,
                    dex1_version,
                    dex2_version,
                    amount_in_wei,
                    min_profit_wei,
                    dex1_data,
                    dex2_data
                ).build_transaction({
                    'from': self.account.address,
                    'nonce': nonce,
                    'gasPrice': gas_price,
                    'gas': 500000,  # Estimate, will be replaced
                    'chainId': self.chain_id
                })
            else:
                tx = self.contract.functions.executeFlashloan(
                    token_in,
                    token_out,
                    dex1,
                    dex2,
                    dex1_version,
                    dex2_version,
                    amount_in_wei,
                    min_profit_wei,
                    dex1_data,
                    dex2_data
                ).build_transaction({
                    'from': self.account.address,
                    'nonce': nonce,
                    'gasPrice': gas_price,
                    'gas': 500000,
                    'chainId': self.chain_id
                })
            
            # Estimate gas
            try:
                gas_estimate = self.w3.eth.estimate_gas(tx)
                tx['gas'] = int(gas_estimate * 1.2)  # 20% buffer
                print(f"   Gas Limit: {tx['gas']}")
            except Exception as e:
                print(f"{Fore.YELLOW}   Warning: Gas estimation failed, using default{Style.RESET_ALL}")
                print(f"   Error: {e}")
            
            # Calculate total gas cost
            gas_cost_wei = tx['gas'] * gas_price
            gas_cost_pol = gas_cost_wei / 1e18
            print(f"   Gas Cost:  {gas_cost_pol:.4f} POL")
            
            print(f"\n{Fore.CYAN}{'─'*80}")
            print(f"📤 SENDING TRANSACTION")
            print(f"{'─'*80}{Style.RESET_ALL}")
            
            # Sign transaction
            signed_tx = self.account.sign_transaction(tx)
            
            # Send transaction via Alchemy
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            
            print(f"   ✅ Sent: {tx_hash_hex}")
            print(f"   ⏳ Waiting for confirmation...")
            
            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                print(f"\n{Fore.GREEN}{'='*80}")
                print(f"✅ TRANSACTION SUCCESSFUL")
                print(f"{'='*80}{Style.RESET_ALL}")
                print(f"   Block: {receipt['blockNumber']}")
                print(f"   Gas Used: {receipt['gasUsed']}")
                print(f"   TX: https://polygonscan.com/tx/{tx_hash_hex}")
                
                # Calculate actual gas cost
                actual_cost = receipt['gasUsed'] * gas_price / 1e18
                print(f"   Gas Cost: {actual_cost:.4f} POL")
                
                return {
                    "success": True,
                    "tx_hash": tx_hash_hex,
                    "block_number": receipt['blockNumber'],
                    "gas_used": receipt['gasUsed'],
                    "gas_cost_pol": actual_cost
                }
            else:
                print(f"\n{Fore.RED}{'='*80}")
                print(f"❌ TRANSACTION REVERTED")
                print(f"{'='*80}{Style.RESET_ALL}")
                print(f"   TX: https://polygonscan.com/tx/{tx_hash_hex}")
                
                return {
                    "success": False,
                    "error": "Transaction reverted",
                    "tx_hash": tx_hash_hex
                }
        
        except Exception as e:
            print(f"\n{Fore.RED}{'='*80}")
            print(f"❌ TRANSACTION FAILED")
            print(f"{'='*80}{Style.RESET_ALL}")
            print(f"   Error: {str(e)}")
            
            return {
                "success": False,
                "error": str(e),
                "stage": "send"
            }
    
    def simulate_arbitrage(
        self,
        token_in_address: str,
        token_out_address: str,
        dex1_address: str,
        dex2_address: str,
        dex1_version: int,
        dex2_version: int,
        amount_in_wei: int,
        min_profit_wei: int,
        dex1_data: bytes = b'',
        dex2_data: bytes = b'',
        use_balancer: bool = False
    ) -> Dict[str, Any]:
        """Simulate transaction without sending (dry run)"""
        
        print(f"\n{Fore.YELLOW}🧪 SIMULATING TRANSACTION (DRY RUN){Style.RESET_ALL}")
        
        token_in = Web3.to_checksum_address(token_in_address)
        token_out = Web3.to_checksum_address(token_out_address)
        dex1 = Web3.to_checksum_address(dex1_address)
        dex2 = Web3.to_checksum_address(dex2_address)
        
        try:
            if use_balancer:
                tx = self.contract.functions.executeBalancerFlashloan(
                    token_in, token_out, dex1, dex2,
                    dex1_version, dex2_version,
                    amount_in_wei, min_profit_wei,
                    dex1_data, dex2_data
                ).build_transaction({
                    'from': self.account.address,
                    'nonce': self.w3.eth.get_transaction_count(self.account.address),
                    'gasPrice': self.w3.eth.gas_price,
                    'chainId': self.chain_id
                })
            else:
                tx = self.contract.functions.executeFlashloan(
                    token_in, token_out, dex1, dex2,
                    dex1_version, dex2_version,
                    amount_in_wei, min_profit_wei,
                    dex1_data, dex2_data
                ).build_transaction({
                    'from': self.account.address,
                    'nonce': self.w3.eth.get_transaction_count(self.account.address),
                    'gasPrice': self.w3.eth.gas_price,
                    'chainId': self.chain_id
                })
            
            # Estimate gas (will revert if trade would fail)
            gas_estimate = self.w3.eth.estimate_gas(tx)
            gas_cost = gas_estimate * self.w3.eth.gas_price / 1e18
            
            print(f"{Fore.GREEN}   ✅ Simulation successful!{Style.RESET_ALL}")
            print(f"   Gas estimate: {gas_estimate}")
            print(f"   Gas cost: {gas_cost:.4f} POL")
            
            return {
                "success": True,
                "gas_estimate": gas_estimate,
                "gas_cost_pol": gas_cost
            }
        
        except Exception as e:
            print(f"{Fore.RED}   ❌ Simulation failed: {e}{Style.RESET_ALL}")
            return {
                "success": False,
                "error": str(e)
            }