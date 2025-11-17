"""
Gas Optimization Manager
- Multi-provider rotation (Infura, Alchemy, Nodies, Ankr)
- Gas estimation with eth_feeHistory and Ankr Gas API
- Token decimals & ABI caching
- EIP-1559 dynamic fees for Polygon
- Private transaction submission via Alchemy
- Cooldown & replay protection
"""

import os
import time
import json
import hashlib
import requests
from typing import Dict, List, Optional, Tuple, Any
from web3 import Web3
from eth_account import Account
from functools import lru_cache
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GasOptimizationManager:
    """
    Manages gas optimization across multiple RPC providers with caching and replay protection
    """
    
    # Provider configuration
    PROVIDERS = {
        "infura": {
            "name": "Infura",
            "http": f"https://polygon-mainnet.infura.io/v3/{os.getenv('INFURA_API_KEY')}",
            "gas_api": f"https://gas.api.infura.io/v3/{os.getenv('INFURA_API_KEY')}",
            "priority": 1
        },
        "alchemy": {
            "name": "Alchemy",
            "http": f"https://polygon-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY')}",
            "private_tx": f"https://polygon-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY')}",
            "priority": 2
        },
        "alchemy_premium": {
            "name": "Alchemy Premium (Pay-as-you-go tracking)",
            "http": f"https://polygon-mainnet.g.alchemy.com/v2/{os.getenv('PREMIUM_ALCHEMY_KEY', os.getenv('ALCHEMY_API_KEY'))}",
            "private_tx": f"https://polygon-mainnet.g.alchemy.com/v2/{os.getenv('PREMIUM_ALCHEMY_KEY', os.getenv('ALCHEMY_API_KEY'))}",
            "priority": 0  # Highest priority for premium calls
        },
        "nodies": {
            "name": "Nodies",
            "http": f"https://lb.nodies.app/v1/{os.getenv('NODIES_API_KEY')}",
            "priority": 3
        },
        "ankr": {
            "name": "Ankr",
            "http": "https://rpc.ankr.com/polygon",
            "gas_api": "https://rpc.ankr.com/polygon/gas",
            "priority": 4
        }
    }
    
    # Constants
    TRADE_COOLDOWN = 10  # seconds between trades
    ROTATION_THRESHOLD = 100  # calls before rotating provider
    GAS_PADDING_PCT = 7  # 7% gas padding
    MAX_PRIORITY_FEE_MULTIPLIER = 1.5  # Max 1.5x priority fee
    
    def __init__(self, rpc_manager=None):
        self.current_provider = "infura"
        self.call_count = 0
        self.last_trade_time = 0
        self.executed_trades = set()  # Hash of executed tx
        
        # Use external RPCManager if provided, otherwise initialize own connections
        self.rpc_manager = rpc_manager
        
        if self.rpc_manager:
            # Use external RPC manager
            self.w3 = self.rpc_manager.get_web3()
            self.w3_instances = None  # Not needed when using external manager
            logger.info("✓ Using external RPC Manager")
        else:
            # Initialize Web3 connections (fallback to legacy mode)
            self.w3_instances: Dict[str, Web3] = {}
            for provider_id, config in self.PROVIDERS.items():
                try:
                    self.w3_instances[provider_id] = Web3(Web3.HTTPProvider(config["http"]))
                    if self.w3_instances[provider_id].is_connected():
                        logger.info(f"✓ Connected to {config['name']}")
                except Exception as e:
                    logger.warning(f"✗ Failed to connect to {config['name']}: {e}")
        
            # Current Web3 instance
            self.w3 = self.w3_instances.get(self.current_provider)
        
        self._token_decimals_cache: Dict[str, int] = {}
        self._router_abi_cache: Dict[str, List] = {}
        self._gas_price_cache: Optional[Tuple[int, int, float]] = None  # (maxFee, maxPriority, timestamp)
        self._cache_duration = 15  # seconds
    
    def rotate_provider(self, force: bool = False) -> None:
        """Rotate to next available RPC provider"""
        # If using external RPC manager, delegate to it
        if self.rpc_manager:
            # External RPC manager handles rotation automatically
            self.w3 = self.rpc_manager.get_web3()
            return
            
        if not force and self.call_count < self.ROTATION_THRESHOLD:
            return
            
        # Get next provider in priority order
        providers = sorted(self.PROVIDERS.items(), key=lambda x: x[1]["priority"])
        current_idx = next((i for i, (k, _) in enumerate(providers) if k == self.current_provider), 0)
        next_idx = (current_idx + 1) % len(providers)
        next_provider = providers[next_idx][0]
        
        if next_provider in self.w3_instances and self.w3_instances[next_provider].is_connected():
            self.current_provider = next_provider
            self.w3 = self.w3_instances[next_provider]
            self.call_count = 0
            logger.info(f"🔄 Rotated to {self.PROVIDERS[next_provider]['name']}")
        else:
            logger.warning(f"⚠️ Could not rotate to {next_provider}, staying with {self.current_provider}")
    
    def _make_rpc_call(self, func, *args, **kwargs) -> Any:
        """Make RPC call with automatic rotation and failover"""
        # If using external RPC manager, use its failover mechanism
        if self.rpc_manager:
            return self.rpc_manager.execute_with_failover(lambda w3: func(*args, **kwargs))
        
        self.call_count += 1
        self.rotate_provider()
        
        # Try current provider first
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"RPC call failed on {self.current_provider}: {e}")
            
            # Failover chain: Infura > Nodies > Alchemy
            failover_order = ["infura", "nodies", "alchemy"]
            for provider_id in failover_order:
                if provider_id == self.current_provider or provider_id not in self.w3_instances:
                    continue
                    
                try:
                    logger.info(f"🔄 Failing over to {self.PROVIDERS[provider_id]['name']}")
                    temp_w3 = self.w3_instances[provider_id]
                    result = func(*args, **kwargs) if not hasattr(func, '__self__') else getattr(temp_w3.eth, func.__name__)(*args, **kwargs)
                    
                    # Switch to this provider
                    self.current_provider = provider_id
                    self.w3 = temp_w3
                    return result
                except Exception as fe:
                    logger.warning(f"Failover to {provider_id} also failed: {fe}")
                    continue
            
            raise Exception("All RPC providers failed")
    
    @lru_cache(maxsize=256)
    def get_token_decimals(self, token_address: str) -> int:
        """Get token decimals with caching"""
        if token_address in self._token_decimals_cache:
            return self._token_decimals_cache[token_address]
        
        try:
            token_address = Web3.to_checksum_address(token_address)
            erc20_abi = [{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]
            contract = self.w3.eth.contract(address=token_address, abi=erc20_abi)
            decimals = self._make_rpc_call(contract.functions.decimals().call)
            self._token_decimals_cache[token_address] = decimals
            return decimals
        except Exception as e:
            logger.warning(f"Failed to get decimals for {token_address}: {e}, defaulting to 18")
            return 18
    
    def get_router_abi(self, router_address: str) -> List:
        """Get router ABI with caching - loads from local registry"""
        if router_address in self._router_abi_cache:
            return self._router_abi_cache[router_address]
        
        # Load from your existing registries
        try:
            with open('router_abis.json', 'r') as f:
                all_abis = json.load(f)
                abi = all_abis.get(router_address.lower())
                if abi:
                    self._router_abi_cache[router_address] = abi
                    return abi
        except Exception as e:
            logger.warning(f"Could not load ABI for {router_address}: {e}")
        
        return []
    
    def get_gas_from_ankr(self) -> Optional[Dict[str, int]]:
        """Fetch gas prices from Ankr Gas API"""
        try:
            response = requests.get(self.PROVIDERS["ankr"]["gas_api"], timeout=3)
            if response.status_code == 200:
                data = response.json()
                # Ankr returns rapid/fast/standard/slow
                return {
                    "maxFeePerGas": int(data.get("fast", {}).get("maxFee", 0) * 1e9),  # Convert to wei
                    "maxPriorityFeePerGas": int(data.get("fast", {}).get("maxPriorityFee", 0) * 1e9)
                }
        except Exception as e:
            logger.debug(f"Ankr gas API failed: {e}")
        return None
    
    def get_gas_from_infura(self) -> Optional[Dict[str, int]]:
        """Fetch gas prices from Infura Gas API"""
        if "INFURA_API_KEY" not in os.environ:
            return None
            
        try:
            response = requests.get(self.PROVIDERS["infura"]["gas_api"], timeout=3)
            if response.status_code == 200:
                data = response.json()
                return {
                    "maxFeePerGas": int(data.get("high", {}).get("suggestedMaxFeePerGas", 0)),
                    "maxPriorityFeePerGas": int(data.get("high", {}).get("suggestedMaxPriorityFeePerGas", 0))
                }
        except Exception as e:
            logger.debug(f"Infura gas API failed: {e}")
        return None
    
    def get_gas_from_fee_history(self) -> Dict[str, int]:
        """Calculate EIP-1559 gas prices using eth_feeHistory"""
        try:
            # Get last 10 blocks
            fee_history = self._make_rpc_call(
                self.w3.eth.fee_history,
                10, 'latest', [50]  # 50th percentile
            )
            
            # Get base fee from most recent block
            base_fee = fee_history['baseFeePerGas'][-1]
            
            # Calculate median priority fee
            priority_fees = [reward[0] for reward in fee_history['reward']]
            median_priority = sorted(priority_fees)[len(priority_fees)//2]
            
            # Add buffer to priority fee but cap it
            priority_fee = min(
                int(median_priority * 1.2),
                int(median_priority * self.MAX_PRIORITY_FEE_MULTIPLIER)
            )
            
            # Max fee = (2 * base) + priority
            max_fee = (2 * base_fee) + priority_fee
            
            return {
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": priority_fee
            }
        except Exception as e:
            logger.warning(f"eth_feeHistory failed: {e}")
            # Fallback to eth_gasPrice
            try:
                gas_price = self._make_rpc_call(self.w3.eth.gas_price)
                return {
                    "maxFeePerGas": int(gas_price * 1.2),
                    "maxPriorityFeePerGas": int(gas_price * 0.1)
                }
            except:
                raise Exception("All gas estimation methods failed")
    
    def get_optimized_gas_params(self, use_cache: bool = True) -> Dict[str, int]:
        """
        Get optimized EIP-1559 gas parameters with multi-source validation
        Priority: Ankr Gas API > eth_feeHistory > Infura Gas API
        """
        # Check cache
        if use_cache and self._gas_price_cache:
            max_fee, max_priority, timestamp = self._gas_price_cache
            if time.time() - timestamp < self._cache_duration:
                return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": max_priority}
        
        gas_prices = []
        
        # 1. Try Ankr Gas API (fastest, most reliable)
        ankr_gas = self.get_gas_from_ankr()
        if ankr_gas:
            gas_prices.append(("Ankr", ankr_gas))
        
        # 2. eth_feeHistory (always available)
        try:
            history_gas = self.get_gas_from_fee_history()
            gas_prices.append(("FeeHistory", history_gas))
        except Exception as e:
            logger.warning(f"FeeHistory failed: {e}")
        
        # 3. Infura Gas API (backup)
        infura_gas = self.get_gas_from_infura()
        if infura_gas:
            gas_prices.append(("Infura", infura_gas))
        
        if not gas_prices:
            raise Exception("Could not fetch gas prices from any source")
        
        # Validation: use median if multiple sources, otherwise use the one we got
        if len(gas_prices) >= 2:
            max_fees = [gp[1]["maxFeePerGas"] for gp in gas_prices]
            priority_fees = [gp[1]["maxPriorityFeePerGas"] for gp in gas_prices]
            
            result = {
                "maxFeePerGas": sorted(max_fees)[len(max_fees)//2],
                "maxPriorityFeePerGas": sorted(priority_fees)[len(priority_fees)//2]
            }
            logger.info(f"✓ Gas validation from {len(gas_prices)} sources")
        else:
            result = gas_prices[0][1]
            logger.info(f"✓ Gas from {gas_prices[0][0]}")
        
        # Cache result
        self._gas_price_cache = (result["maxFeePerGas"], result["maxPriorityFeePerGas"], time.time())
        
        return result
    
    def estimate_gas_with_padding(self, transaction: Dict) -> int:
        """
        Estimate gas and add safety padding
        Uses PREMIUM_ALCHEMY_KEY for easier cost tracking on pay-as-you-go
        """
        try:
            # Use premium Alchemy endpoint for gas estimation (premium call)
            if os.getenv('PREMIUM_ALCHEMY_KEY') and 'alchemy_premium' in self.PROVIDERS:
                premium_url = self.PROVIDERS['alchemy_premium']['http']
                premium_w3 = Web3(Web3.HTTPProvider(premium_url, request_kwargs={'timeout': 10}))
                estimated = premium_w3.eth.estimate_gas(transaction)
                logger.info(f"✓ Gas estimate via PREMIUM_ALCHEMY_KEY: {estimated}")
            else:
                # Fallback to regular endpoint
                estimated = self._make_rpc_call(self.w3.eth.estimate_gas, transaction)
                logger.info(f"✓ Gas estimate via regular RPC: {estimated}")

            padded = int(estimated * (1 + self.GAS_PADDING_PCT / 100))
            logger.info(f"Gas estimate: {estimated} → {padded} (+{self.GAS_PADDING_PCT}%)")
            return padded
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            # Return a conservative default
            return 500000
    
    def build_eip1559_transaction(
        self,
        to: str,
        data: str,
        from_address: str,
        value: int = 0,
        gas_limit: Optional[int] = None
    ) -> Dict:
        """Build EIP-1559 transaction with optimized gas params"""
        
        # Get optimized gas params
        gas_params = self.get_optimized_gas_params()
        
        # Build transaction
        tx = {
            "from": Web3.to_checksum_address(from_address),
            "to": Web3.to_checksum_address(to),
            "value": value,
            "data": data,
            "chainId": 137,  # Polygon
            "type": 2,  # EIP-1559
            "maxFeePerGas": gas_params["maxFeePerGas"],
            "maxPriorityFeePerGas": gas_params["maxPriorityFeePerGas"],
            "nonce": self._make_rpc_call(self.w3.eth.get_transaction_count, from_address)
        }
        
        # Estimate gas if not provided
        if gas_limit is None:
            tx["gas"] = self.estimate_gas_with_padding(tx)
        else:
            tx["gas"] = gas_limit
        
        return tx
    
    def send_private_transaction(
        self,
        signed_tx: str,
        max_block_number: Optional[int] = None
    ) -> str:
        """
        Send private transaction via Alchemy to prevent frontrunning
        Uses PREMIUM_ALCHEMY_KEY for cost tracking (premium call)
        """
        # Use premium key if available, otherwise fall back to regular key
        alchemy_key = os.getenv('PREMIUM_ALCHEMY_KEY') or os.getenv('ALCHEMY_API_KEY')

        if not alchemy_key:
            logger.warning("No Alchemy API key set, sending as regular tx")
            return self.w3.eth.send_raw_transaction(signed_tx).hex()

        try:
            # Use premium endpoint for private transactions
            url = f"https://polygon-mainnet.g.alchemy.com/v2/{alchemy_key}"
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_sendPrivateTransaction",
                "params": [{
                    "tx": signed_tx if signed_tx.startswith('0x') else f'0x{signed_tx}',
                    "maxBlockNumber": hex(max_block_number) if max_block_number else None,
                    "preferences": {
                        "fast": True
                    }
                }]
            }

            response = requests.post(url, json=payload, timeout=10)
            result = response.json()

            if "error" in result:
                raise Exception(f"Alchemy private tx error: {result['error']}")

            tx_hash = result["result"]
            key_type = "PREMIUM" if os.getenv('PREMIUM_ALCHEMY_KEY') else "REGULAR"
            logger.info(f"🔒 Private transaction sent via {key_type} Alchemy key: {tx_hash}")
            return tx_hash

        except Exception as e:
            logger.warning(f"Private tx failed, falling back to public: {e}")
            return self.w3.eth.send_raw_transaction(signed_tx).hex()
    
    def check_trade_cooldown(self) -> bool:
        """Check if cooldown period has passed"""
        elapsed = time.time() - self.last_trade_time
        if elapsed < self.TRADE_COOLDOWN:
            logger.info(f"⏳ Cooldown active: {self.TRADE_COOLDOWN - elapsed:.1f}s remaining")
            return False
        return True
    
    def is_trade_executed(self, trade_id: str) -> bool:
        """Check if trade has already been executed (replay protection)"""
        trade_hash = hashlib.sha256(trade_id.encode()).hexdigest()
        return trade_hash in self.executed_trades
    
    def mark_trade_executed(self, tx_hash: str) -> None:
        """Mark trade as executed for replay protection"""
        self.executed_trades.add(tx_hash)
        self.last_trade_time = time.time()
        logger.info(f"✓ Trade logged: {tx_hash[:10]}...")
        
        # Cleanup old trades (keep last 10000)
        if len(self.executed_trades) > 10000:
            self.executed_trades = set(list(self.executed_trades)[-10000:])
    
    def oracle_sanity_check(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        expected_amount_out: int,
        max_slippage_pct: float = 2.0
    ) -> bool:
        """
        Off-chain oracle sanity check before executing trade
        Compares expected output with oracle price
        """
        try:
            # This is a placeholder - implement your actual oracle logic
            # Could use Chainlink, Band Protocol, or your own price feeds
            
            # For now, just a basic ratio check
            # You should replace this with actual oracle calls
            logger.info(f"🔍 Oracle check: {amount_in} → {expected_amount_out}")
            
            # Example: Check if price deviation is within acceptable range
            # In production, fetch actual oracle prices and compare
            
            return True  # Placeholder - implement your oracle logic
            
        except Exception as e:
            logger.error(f"Oracle sanity check failed: {e}")
            return False
    
    def execute_trade(
        self,
        contract_address: str,
        function_data: str,
        private_key: str,
        value: int = 0,
        use_private_tx: bool = True
    ) -> Optional[str]:
        """
        Execute a trade with all optimizations and safety checks
        """
        # 1. Check cooldown
        if not self.check_trade_cooldown():
            return None

        # 2. Generate trade ID for replay protection
        trade_id = f"{contract_address}:{function_data}:{int(time.time())}"
        if self.is_trade_executed(trade_id):
            logger.warning("⚠️ Trade already executed (replay protection)")
            return None

        try:
            # 3. Build transaction
            account = Account.from_key(private_key)
            tx = self.build_eip1559_transaction(
                to=contract_address,
                data=function_data,
                from_address=account.address,
                value=value
            )

            # 4. Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key)

            # 5. Send transaction (private if requested)
            if use_private_tx:
                tx_hash = self.send_private_transaction(signed_tx.raw_transaction.hex())
            else:
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction).hex()

            # 6. Mark as executed
            self.mark_trade_executed(tx_hash)

            logger.info(f"✅ Trade executed: {tx_hash}")
            return tx_hash

        except Exception as e:
            logger.error(f"❌ Trade execution failed: {e}")
            return None


# Alias for backward compatibility with Polygon bot
# (Flashbots doesn't exist on Polygon - we use Alchemy private TX instead)
FlashbotsTxBuilder = GasOptimizationManager