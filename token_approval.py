"""
Token Approval Manager
Handles ERC20 token approvals for DEX routers and flash loan contracts
"""

from web3 import Web3
from eth_account import Account
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Standard ERC20 ABI (approve function)
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


class TokenApprovalManager:
    """
    Manages token approvals for trading
    Checks allowances and approves when needed
    """

    # Max uint256 for unlimited approval
    MAX_APPROVAL = 2**256 - 1

    def __init__(self, w3: Web3, private_key: str):
        """
        Args:
            w3: Web3 instance
            private_key: Private key for signing transactions
        """
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.approved_cache = {}  # Cache of approved tokens

    def check_allowance(
        self,
        token_address: str,
        spender_address: str,
        required_amount: int
    ) -> bool:
        """
        Check if token has sufficient allowance

        Args:
            token_address: ERC20 token address
            spender_address: Address that will spend tokens (router/contract)
            required_amount: Minimum required allowance in wei

        Returns:
            True if allowance is sufficient
        """
        try:
            # Check cache first
            cache_key = f"{token_address}:{spender_address}"
            if cache_key in self.approved_cache:
                if self.approved_cache[cache_key] >= required_amount:
                    return True

            # Check on-chain
            token = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )

            allowance = token.functions.allowance(
                self.account.address,
                Web3.to_checksum_address(spender_address)
            ).call()

            # Update cache
            self.approved_cache[cache_key] = allowance

            return allowance >= required_amount

        except Exception as e:
            logger.error(f"Error checking allowance: {e}")
            return False

    def approve_token(
        self,
        token_address: str,
        spender_address: str,
        amount: Optional[int] = None,
        unlimited: bool = True
    ) -> Dict:
        """
        Approve token spending

        Args:
            token_address: ERC20 token address
            spender_address: Address that will spend tokens
            amount: Specific amount to approve (if not unlimited)
            unlimited: If True, approve max uint256

        Returns:
            Dict with transaction result
        """
        try:
            token_address = Web3.to_checksum_address(token_address)
            spender_address = Web3.to_checksum_address(spender_address)

            token = self.w3.eth.contract(
                address=token_address,
                abi=ERC20_ABI
            )

            # Determine approval amount
            approval_amount = self.MAX_APPROVAL if unlimited else amount

            logger.info(f"Approving {token_address} for {spender_address}")

            # Build transaction
            nonce = self.w3.eth.get_transaction_count(self.account.address)

            tx = token.functions.approve(
                spender_address,
                approval_amount
            ).build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': 100000,  # Standard gas for approve
                'maxFeePerGas': self.w3.eth.gas_price,
                'maxPriorityFeePerGas': int(self.w3.eth.gas_price * 0.1),
                'chainId': 137  # Polygon
            })

            # Sign and send
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

            logger.info(f"Approval tx sent: {tx_hash.hex()}")

            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt['status'] == 1:
                logger.info(f"Approval successful!")

                # Update cache
                cache_key = f"{token_address}:{spender_address}"
                self.approved_cache[cache_key] = approval_amount

                return {
                    'status': 'success',
                    'tx_hash': tx_hash.hex(),
                    'gas_used': receipt['gasUsed']
                }
            else:
                logger.error("Approval transaction failed")
                return {
                    'status': 'failed',
                    'tx_hash': tx_hash.hex()
                }

        except Exception as e:
            logger.error(f"Error approving token: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }

    def ensure_approval(
        self,
        token_address: str,
        spender_address: str,
        required_amount: int
    ) -> bool:
        """
        Ensure token has sufficient allowance, approve if needed

        Args:
            token_address: ERC20 token address
            spender_address: Address that will spend tokens
            required_amount: Required allowance in wei

        Returns:
            True if approval is sufficient or successful
        """
        # Check if already approved
        if self.check_allowance(token_address, spender_address, required_amount):
            logger.info(f"Token {token_address} already approved for {spender_address}")
            return True

        # Need to approve
        logger.info(f"Approving token {token_address} for {spender_address}")
        result = self.approve_token(token_address, spender_address, unlimited=True)

        return result['status'] == 'success'

    def approve_multiple(
        self,
        approvals: list
    ) -> Dict[str, bool]:
        """
        Approve multiple tokens in batch

        Args:
            approvals: List of dicts with keys: token_address, spender_address, amount

        Returns:
            Dict mapping "token:spender" to success status
        """
        results = {}

        for approval in approvals:
            token = approval['token_address']
            spender = approval['spender_address']
            amount = approval.get('amount', self.MAX_APPROVAL)

            key = f"{token}:{spender}"
            success = self.ensure_approval(token, spender, amount)
            results[key] = success

        return results

    def revoke_approval(
        self,
        token_address: str,
        spender_address: str
    ) -> Dict:
        """
        Revoke token approval (set to 0)

        Args:
            token_address: ERC20 token address
            spender_address: Spender to revoke

        Returns:
            Transaction result
        """
        logger.info(f"Revoking approval for {token_address} from {spender_address}")
        result = self.approve_token(token_address, spender_address, amount=0, unlimited=False)

        if result['status'] == 'success':
            # Clear from cache
            cache_key = f"{token_address}:{spender_address}"
            if cache_key in self.approved_cache:
                del self.approved_cache[cache_key]

        return result


# Convenience function for quick approval
def quick_approve(
    w3: Web3,
    private_key: str,
    token_address: str,
    spender_address: str
) -> bool:
    """
    Quick approval helper

    Args:
        w3: Web3 instance
        private_key: Private key
        token_address: Token to approve
        spender_address: Spender (router/contract)

    Returns:
        True if successful
    """
    manager = TokenApprovalManager(w3, private_key)
    return manager.ensure_approval(token_address, spender_address, manager.MAX_APPROVAL)
