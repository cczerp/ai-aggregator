#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flashloan Contract Integration
Provides ABI, bytecode references, and deployment helpers for FlashloanTradingBot.sol

Contract Features:
- Aave V3 flashloan support
- Balancer V2 flashloan support
- Dual-DEX arbitrage execution
- Owner authorization and access control
- Emergency withdrawal functions

To deploy:
1. Compile flashloanbot.sol using Remix or hardhat
2. Deploy with Aave and Balancer vault addresses
3. Update CONTRACT_ADDRESS in config.json
4. Set FLASHLOAN_CONTRACT_ADDRESS in .env
"""

import json
from typing import Dict, Any, List
from web3 import Web3
from eth_account import Account

# Contract ABI - Main functions for trading bot
FLASHLOAN_CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_aave", "type": "address"},
            {"internalType": "address", "name": "_balancer", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "address", "name": "tokenIn", "type": "address"},
            {"indexed": False, "internalType": "address", "name": "tokenOut", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "profit", "type": "uint256"}
        ],
        "name": "TradeExecuted",
        "type": "event"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "caller", "type": "address"},
            {"internalType": "bool", "name": "status", "type": "bool"}
        ],
        "name": "authorizeCaller",
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
    },
    {
        "inputs": [{"internalType": "address", "name": "token", "type": "address"}],
        "name": "withdrawToken",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "withdrawETH",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "newOwner", "type": "address"}],
        "name": "transferOwnership",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Polygon Mainnet Contract Addresses
POLYGON_CONTRACTS = {
    "aave_lending_pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",  # Aave V3 Pool
    "balancer_vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",  # Balancer V2 Vault
    "wmatic": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    "weth": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    "usdc": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "usdt": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    "wbtc": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
}

# DEX Router Addresses on Polygon
DEX_ROUTERS = {
    "quickswap": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",  # QuickSwap V2
    "sushiswap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",  # SushiSwap V2
    "uniswap_v3_router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap V3 SwapRouter
}


class FlashloanContract:
    """
    Wrapper for FlashloanTradingBot contract
    """

    def __init__(self, web3: Web3, contract_address: str, private_key: str = None):
        """
        Initialize contract wrapper

        Args:
            web3: Web3 instance
            contract_address: Deployed contract address
            private_key: Private key for signing transactions (optional)
        """
        self.web3 = web3
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.contract = web3.eth.contract(
            address=self.contract_address,
            abi=FLASHLOAN_CONTRACT_ABI
        )
        self.private_key = private_key
        self.account = Account.from_key(private_key) if private_key else None

    def execute_aave_flashloan(
        self,
        token_in: str,
        token_out: str,
        dex1_address: str,
        dex2_address: str,
        amount_in: int,
        min_profit: int,
        gas_price: int = None
    ) -> Dict[str, Any]:
        """
        Execute Aave flashloan arbitrage

        Args:
            token_in: Input token address (token to borrow)
            token_out: Output token address (intermediate token)
            dex1_address: First DEX router address (buy)
            dex2_address: Second DEX router address (sell)
            amount_in: Amount to borrow (in wei)
            min_profit: Minimum profit required (in wei)
            gas_price: Gas price in wei (optional)

        Returns:
            Transaction receipt
        """
        if not self.account:
            raise ValueError("Private key required for execution")

        # Build transaction
        function = self.contract.functions.executeFlashloan(
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            Web3.to_checksum_address(dex1_address),
            Web3.to_checksum_address(dex2_address),
            2,  # dex1Version (V2)
            2,  # dex2Version (V2)
            amount_in,
            min_profit,
            b"",  # dex1Data (empty)
            b""  # dex2Data (empty)
        )

        # Build transaction params
        tx_params = {
            "from": self.account.address,
            "nonce": self.web3.eth.get_transaction_count(self.account.address),
            "gas": 500000,  # Estimate, will be adjusted
            "maxFeePerGas": gas_price or self.web3.eth.gas_price,
            "maxPriorityFeePerGas": self.web3.to_wei(30, "gwei"),
        }

        # Estimate gas
        try:
            estimated_gas = function.estimate_gas(tx_params)
            tx_params["gas"] = int(estimated_gas * 1.2)  # 20% buffer
        except Exception as e:
            print(f"Gas estimation failed: {e}")
            # Keep default gas limit

        # Build and sign transaction
        tx = function.build_transaction(tx_params)
        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)

        # Send transaction
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        # Wait for receipt
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

        return {
            "tx_hash": tx_hash.hex(),
            "status": "success" if receipt["status"] == 1 else "failed",
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "receipt": receipt
        }

    def execute_balancer_flashloan(
        self,
        token_in: str,
        token_out: str,
        dex1_address: str,
        dex2_address: str,
        amount_in: int,
        min_profit: int,
        gas_price: int = None
    ) -> Dict[str, Any]:
        """
        Execute Balancer flashloan arbitrage

        Args:
            token_in: Input token address (token to borrow)
            token_out: Output token address (intermediate token)
            dex1_address: First DEX router address (buy)
            dex2_address: Second DEX router address (sell)
            amount_in: Amount to borrow (in wei)
            min_profit: Minimum profit required (in wei)
            gas_price: Gas price in wei (optional)

        Returns:
            Transaction receipt
        """
        if not self.account:
            raise ValueError("Private key required for execution")

        # Build transaction (similar to Aave, but uses executeBalancerFlashloan)
        function = self.contract.functions.executeBalancerFlashloan(
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            Web3.to_checksum_address(dex1_address),
            Web3.to_checksum_address(dex2_address),
            2,  # dex1Version (V2)
            2,  # dex2Version (V2)
            amount_in,
            min_profit,
            b"",  # dex1Data (empty)
            b""  # dex2Data (empty)
        )

        # Build transaction params
        tx_params = {
            "from": self.account.address,
            "nonce": self.web3.eth.get_transaction_count(self.account.address),
            "gas": 500000,
            "maxFeePerGas": gas_price or self.web3.eth.gas_price,
            "maxPriorityFeePerGas": self.web3.to_wei(30, "gwei"),
        }

        # Estimate gas
        try:
            estimated_gas = function.estimate_gas(tx_params)
            tx_params["gas"] = int(estimated_gas * 1.2)
        except Exception as e:
            print(f"Gas estimation failed: {e}")

        # Build and sign transaction
        tx = function.build_transaction(tx_params)
        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)

        # Send transaction
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        # Wait for receipt
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

        return {
            "tx_hash": tx_hash.hex(),
            "status": "success" if receipt["status"] == 1 else "failed",
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "receipt": receipt
        }

    def get_owner(self) -> str:
        """Get contract owner address"""
        return self.contract.functions.owner().call()

    def authorize_caller(self, caller_address: str, status: bool) -> Dict[str, Any]:
        """
        Authorize or revoke caller access

        Args:
            caller_address: Address to authorize
            status: True to authorize, False to revoke

        Returns:
            Transaction receipt
        """
        if not self.account:
            raise ValueError("Private key required")

        function = self.contract.functions.authorizeCaller(
            Web3.to_checksum_address(caller_address),
            status
        )

        tx = function.build_transaction({
            "from": self.account.address,
            "nonce": self.web3.eth.get_transaction_count(self.account.address),
            "gas": 100000,
            "maxFeePerGas": self.web3.eth.gas_price,
            "maxPriorityFeePerGas": self.web3.to_wei(30, "gwei"),
        })

        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

        return {
            "tx_hash": tx_hash.hex(),
            "status": "success" if receipt["status"] == 1 else "failed"
        }

    def withdraw_token(self, token_address: str) -> Dict[str, Any]:
        """
        Withdraw tokens from contract (owner only)

        Args:
            token_address: Token to withdraw

        Returns:
            Transaction receipt
        """
        if not self.account:
            raise ValueError("Private key required")

        function = self.contract.functions.withdrawToken(
            Web3.to_checksum_address(token_address)
        )

        tx = function.build_transaction({
            "from": self.account.address,
            "nonce": self.web3.eth.get_transaction_count(self.account.address),
            "gas": 100000,
            "maxFeePerGas": self.web3.eth.gas_price,
            "maxPriorityFeePerGas": self.web3.to_wei(30, "gwei"),
        })

        signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

        return {
            "tx_hash": tx_hash.hex(),
            "status": "success" if receipt["status"] == 1 else "failed"
        }


def get_flashloan_contract(web3: Web3, contract_address: str, private_key: str = None) -> FlashloanContract:
    """
    Factory function to get flashloan contract instance

    Args:
        web3: Web3 instance
        contract_address: Deployed contract address
        private_key: Private key for signing (optional)

    Returns:
        FlashloanContract instance
    """
    return FlashloanContract(web3, contract_address, private_key)


# Deployment helper
def get_deployment_params() -> Dict[str, Any]:
    """
    Get deployment parameters for Polygon mainnet

    Returns:
        Dictionary with constructor parameters and deployment info
    """
    return {
        "constructor_args": [
            POLYGON_CONTRACTS["aave_lending_pool"],
            POLYGON_CONTRACTS["balancer_vault"]
        ],
        "network": "polygon",
        "chain_id": 137,
        "contracts": POLYGON_CONTRACTS,
        "dex_routers": DEX_ROUTERS,
        "deployment_instructions": """
Deployment Steps:

1. Compile Contract:
   - Use Remix IDE (https://remix.ethereum.org/)
   - Or use Hardhat/Foundry locally
   - Compiler version: 0.8.20
   - Optimization: 200 runs

2. Deploy Contract:
   - Constructor args: [AAVE_POOL_ADDRESS, BALANCER_VAULT_ADDRESS]
   - Polygon Mainnet:
     - Aave Pool: 0x794a61358D6845594F94dc1DB02A252b5b4814aD
     - Balancer Vault: 0xBA12222222228d8Ba445958a75a0704d566BF2C8
   - Mumbai Testnet (for testing):
     - Aave Pool: 0x6C9fB0D5bD9429eb9Cd96B85B81d872281771E6B
     - Balancer Vault: 0xBA12222222228d8Ba445958a75a0704d566BF2C8

3. After Deployment:
   - Add contract address to .env as FLASHLOAN_CONTRACT_ADDRESS
   - Update config.json with contract address
   - Authorize your bot wallet: contract.authorizeCaller(BOT_ADDRESS, true)

4. Verify Contract on Polygonscan:
   - Go to https://polygonscan.com/verifyContract
   - Enter contract address and constructor args
   - This enables easier debugging and trust

5. Test on Testnet First!
   - Deploy to Mumbai testnet
   - Test with small amounts
   - Verify all functions work correctly
   - Then deploy to mainnet
        """
    }


if __name__ == "__main__":
    # Print deployment info
    params = get_deployment_params()
    print("=== Flashloan Contract Deployment Info ===\n")
    print(f"Network: {params['network'].upper()}")
    print(f"Chain ID: {params['chain_id']}")
    print(f"\nConstructor Arguments:")
    print(f"  Aave Pool: {params['constructor_args'][0]}")
    print(f"  Balancer Vault: {params['constructor_args'][1]}")
    print(f"\n{params['deployment_instructions']}")
