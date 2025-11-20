"""
Sandwich Attack Bot - PRIMARY MEV STRATEGY
Monitors mempool for large swaps and sandwiches them for profit

Flow:
1. Monitor mempool for pending swaps
2. Decode swap to get amount, path, slippage
3. Calculate sandwich profit (frontrun + victim + backrun)
4. Build atomic bundle (3 transactions)
5. Submit to Flashbots/private relay
6. Profit from victim's price impact

This is the MAIN strategy. Arbitrage finder runs as backup.
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from eth_account import Account
from colorama import Fore, Style, init
import logging

from swap_decoder import SwapDecoder
from registries import TOKENS, DEXES, get_token_address
from tx_builder import GasOptimizationManager

init(autoreset=True)
logger = logging.getLogger(__name__)


class SandwichCalculator:
    """
    Calculates if a sandwich attack is profitable
    Given a victim's swap, calculates:
    - Frontrun amount (our buy)
    - Expected price impact
    - Backrun amount (our sell)
    - Net profit after gas + bribes
    """

    def __init__(self, web3: Web3, gas_manager: GasOptimizationManager):
        self.w3 = web3
        self.gas_manager = gas_manager

        # Sandwich parameters
        self.MIN_VICTIM_VALUE_USD = 50000  # Only sandwich swaps > $50k
        self.MIN_PROFIT_USD = 10.0  # Min profit after gas
        self.MAX_FRONTRUN_PERCENT = 0.3  # Max 30% of victim's trade
        self.GAS_PER_SANDWICH = 300000  # Estimated gas for 2 swaps

        logger.info(f"{Fore.GREEN}✅ Sandwich Calculator initialized{Style.RESET_ALL}")
        logger.info(f"   Min victim value: ${self.MIN_VICTIM_VALUE_USD:,}")
        logger.info(f"   Min profit: ${self.MIN_PROFIT_USD}")

    def calculate_sandwich_opportunity(
        self,
        victim_swap: Dict,
        pool_reserves: Dict
    ) -> Optional[Dict]:
        """
        Calculate if sandwiching this victim is profitable

        Args:
            victim_swap: Decoded swap data from mempool
                - amountIn: Victim's input amount
                - amountOutMin: Victim's min output
                - path: [tokenIn, tokenOut]
                - to: Victim's address
                - deadline: Swap deadline

            pool_reserves: Current pool reserves
                - reserve0, reserve1
                - token0, token1

        Returns:
            Sandwich opportunity dict or None
        """
        try:
            # Extract victim details
            victim_amount_in = victim_swap.get('amountIn', 0)
            victim_path = victim_swap.get('path', [])

            if not victim_amount_in or len(victim_path) < 2:
                return None

            token_in = victim_path[0]
            token_out = victim_path[-1]

            # Get token info
            token_in_info = self._get_token_info(token_in)
            token_out_info = self._get_token_info(token_out)

            if not token_in_info or not token_out_info:
                return None

            # Calculate victim's trade value in USD
            victim_value_usd = self._estimate_value_usd(
                victim_amount_in,
                token_in_info
            )

            # Filter: Only sandwich large trades
            if victim_value_usd < self.MIN_VICTIM_VALUE_USD:
                logger.debug(f"Victim too small: ${victim_value_usd:,.0f} < ${self.MIN_VICTIM_VALUE_USD:,}")
                return None

            logger.info(f"\n{Fore.YELLOW}🎯 POTENTIAL SANDWICH TARGET{Style.RESET_ALL}")
            logger.info(f"   Victim value: ${victim_value_usd:,.0f}")
            logger.info(f"   Path: {token_in_info['symbol']} → {token_out_info['symbol']}")

            # Calculate optimal frontrun amount (% of victim's trade)
            frontrun_percent = min(0.2, self.MAX_FRONTRUN_PERCENT)  # Start with 20%
            frontrun_amount = int(victim_amount_in * frontrun_percent)

            # Simulate the sandwich
            simulation = self._simulate_sandwich(
                frontrun_amount=frontrun_amount,
                victim_amount=victim_amount_in,
                token_in=token_in,
                token_out=token_out,
                pool_reserves=pool_reserves
            )

            if not simulation:
                logger.debug("Simulation failed")
                return None

            # Calculate costs
            gas_cost_usd = self._estimate_gas_cost()
            flashbots_bribe_usd = self._calculate_optimal_bribe(simulation['gross_profit_usd'])

            # Net profit
            net_profit = simulation['gross_profit_usd'] - gas_cost_usd - flashbots_bribe_usd

            logger.info(f"   Gross profit: ${simulation['gross_profit_usd']:.2f}")
            logger.info(f"   Gas cost: ${gas_cost_usd:.2f}")
            logger.info(f"   Flashbots bribe: ${flashbots_bribe_usd:.2f}")
            logger.info(f"   Net profit: ${net_profit:.2f}")

            if net_profit < self.MIN_PROFIT_USD:
                logger.debug(f"Not profitable: ${net_profit:.2f} < ${self.MIN_PROFIT_USD}")
                return None

            # Profitable sandwich!
            return {
                'victim_tx_hash': victim_swap.get('tx_hash'),
                'victim_amount': victim_amount_in,
                'victim_value_usd': victim_value_usd,
                'frontrun_amount': frontrun_amount,
                'backrun_amount': simulation['tokens_acquired'],
                'token_in': token_in,
                'token_out': token_out,
                'token_in_symbol': token_in_info['symbol'],
                'token_out_symbol': token_out_info['symbol'],
                'pool_address': pool_reserves.get('pool_address'),
                'dex': pool_reserves.get('dex'),
                'gross_profit_usd': simulation['gross_profit_usd'],
                'gas_cost_usd': gas_cost_usd,
                'flashbots_bribe_usd': flashbots_bribe_usd,
                'net_profit_usd': net_profit,
                'victim_slippage_pct': simulation['victim_slippage_pct']
            }

        except Exception as e:
            logger.error(f"Sandwich calculation error: {e}")
            return None

    def _simulate_sandwich(
        self,
        frontrun_amount: int,
        victim_amount: int,
        token_in: str,
        token_out: str,
        pool_reserves: Dict
    ) -> Optional[Dict]:
        """
        Simulate the 3-step sandwich:
        1. Our frontrun buy
        2. Victim's buy (at worse price)
        3. Our backrun sell
        """
        reserve_in = pool_reserves['reserve0']
        reserve_out = pool_reserves['reserve1']

        # STEP 1: Our frontrun buy (token_in -> token_out)
        tokens_we_get = self._calculate_output(frontrun_amount, reserve_in, reserve_out)

        # Update reserves after our buy
        reserve_in += frontrun_amount
        reserve_out -= tokens_we_get

        # STEP 2: Victim's buy (at inflated price)
        victim_gets = self._calculate_output(victim_amount, reserve_in, reserve_out)
        victim_min_out = victim_gets * 0.95  # Assume 5% slippage tolerance

        # Calculate victim's slippage
        original_victim_output = self._calculate_output(victim_amount, pool_reserves['reserve0'], pool_reserves['reserve1'])
        victim_slippage_pct = ((original_victim_output - victim_gets) / original_victim_output) * 100

        # Update reserves after victim's buy
        reserve_in += victim_amount
        reserve_out -= victim_gets

        # STEP 3: Our backrun sell (token_out -> token_in)
        tokens_we_sell_for = self._calculate_output(tokens_we_get, reserve_out, reserve_in)

        # Calculate profit
        gross_profit = tokens_we_sell_for - frontrun_amount
        gross_profit_usd = self._tokens_to_usd(gross_profit, token_in)

        return {
            'tokens_acquired': tokens_we_get,
            'gross_profit': gross_profit,
            'gross_profit_usd': gross_profit_usd,
            'victim_slippage_pct': victim_slippage_pct
        }

    def _calculate_output(self, amount_in: int, reserve_in: int, reserve_out: int) -> int:
        """Uniswap V2 constant product formula with 0.3% fee"""
        if amount_in == 0 or reserve_in == 0 or reserve_out == 0:
            return 0

        amount_in_with_fee = amount_in * 997  # 0.3% fee
        numerator = amount_in_with_fee * reserve_out
        denominator = (reserve_in * 1000) + amount_in_with_fee

        return numerator // denominator

    def _get_token_info(self, address: str) -> Optional[Dict]:
        """Get token info from registry"""
        address = address.lower()
        for symbol, info in TOKENS.items():
            if info['address'].lower() == address:
                return {**info, 'symbol': symbol}
        return None

    def _estimate_value_usd(self, amount: int, token_info: Dict) -> float:
        """Estimate token value in USD"""
        # Simplified - use CoinGecko price
        amount_normalized = amount / (10 ** token_info['decimals'])

        # Rough price estimates (should use real price feed)
        prices = {
            'USDC': 1.0,
            'USDT': 1.0,
            'WETH': 2000.0,
            'WBTC': 40000.0,
            'WPOL': 0.40
        }

        price = prices.get(token_info['symbol'], 1.0)
        return amount_normalized * price

    def _tokens_to_usd(self, amount: int, token_address: str) -> float:
        """Convert token amount to USD"""
        token_info = self._get_token_info(token_address)
        if not token_info:
            return 0.0
        return self._estimate_value_usd(amount, token_info)

    def _estimate_gas_cost(self) -> float:
        """Estimate gas cost for sandwich (2 swaps)"""
        try:
            gas_params = self.gas_manager.get_optimized_gas_params()
            gas_price = gas_params['maxFeePerGas']

            # 2 swaps: ~300k gas
            gas_cost_wei = self.GAS_PER_SANDWICH * gas_price
            gas_cost_pol = gas_cost_wei / 1e18

            return gas_cost_pol * 0.40  # POL price
        except:
            return 0.50  # Fallback estimate

    def _calculate_optimal_bribe(self, gross_profit: float) -> float:
        """
        Calculate optimal Flashbots bribe
        Typically 10-20% of gross profit to win the block
        """
        return gross_profit * 0.15  # 15% bribe


class SandwichBot:
    """
    Main sandwich attack bot
    Monitors mempool and executes sandwich attacks via Flashbots
    """

    def __init__(
        self,
        rpc_manager,
        contract_address: str,
        private_key: str,
        flashbots_relay_url: str = "https://relay.flashbots.net"
    ):
        self.rpc_manager = rpc_manager
        self.contract_address = contract_address
        self.private_key = private_key
        self.flashbots_relay_url = flashbots_relay_url

        self.w3 = rpc_manager.get_web3(rpc_manager.endpoints[0])
        self.account = Account.from_key(private_key)

        # Initialize components
        self.swap_decoder = SwapDecoder()
        self.gas_manager = GasOptimizationManager(rpc_manager=rpc_manager)
        self.calculator = SandwichCalculator(self.w3, self.gas_manager)

        # Stats
        self.pending_swaps_seen = 0
        self.sandwiches_attempted = 0
        self.sandwiches_successful = 0
        self.total_profit = 0.0

        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"🥪 SANDWICH BOT INITIALIZED")
        logger.info(f"{'='*80}{Style.RESET_ALL}")
        logger.info(f"   Contract: {contract_address[:10]}...")
        logger.info(f"   Wallet: {self.account.address[:10]}...")
        logger.info(f"   Flashbots relay: {flashbots_relay_url}")
        logger.info(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")

    async def monitor_mempool(self):
        """
        Monitor mempool for pending swaps
        This is the main loop - runs forever
        """
        logger.info(f"{Fore.GREEN}🔍 Starting mempool monitoring...{Style.RESET_ALL}\n")

        # Subscribe to pending transactions
        pending_filter = self.w3.eth.filter('pending')

        while True:
            try:
                # Get new pending txs
                new_txs = pending_filter.get_new_entries()

                for tx_hash in new_txs:
                    await self._process_pending_tx(tx_hash)

                await asyncio.sleep(0.1)  # Small delay

            except Exception as e:
                logger.error(f"Mempool monitoring error: {e}")
                await asyncio.sleep(1)

    async def _process_pending_tx(self, tx_hash: str):
        """Process a single pending transaction"""
        try:
            # Get transaction details
            tx = self.w3.eth.get_transaction(tx_hash)

            if not tx or not tx.get('to'):
                return

            self.pending_swaps_seen += 1

            # Check if it's a DEX swap
            to_address = tx['to'].lower()
            dex_routers = {addr.lower(): name for addr, name in [
                (DEXES['QuickSwap_V2']['router'], 'QuickSwap_V2'),
                (DEXES['SushiSwap']['router'], 'SushiSwap'),
                (DEXES['Uniswap_V3']['router'], 'Uniswap_V3'),
            ]}

            if to_address not in dex_routers:
                return  # Not a DEX swap

            dex_name = dex_routers[to_address]

            # Decode the swap
            decoded = self.swap_decoder.decode_input(tx['input'])

            if not decoded:
                return  # Couldn't decode

            logger.info(f"\n{Fore.CYAN}📥 PENDING SWAP DETECTED{Style.RESET_ALL}")
            logger.info(f"   TX: {tx_hash.hex()[:10]}...")
            logger.info(f"   DEX: {dex_name}")
            logger.info(f"   Function: {decoded['function']}")

            # Add transaction metadata
            decoded['tx_hash'] = tx_hash.hex()
            decoded['dex'] = dex_name
            decoded['gas_price'] = tx.get('gasPrice', 0)

            # Check if we can sandwich this
            await self._attempt_sandwich(decoded)

        except Exception as e:
            logger.debug(f"Error processing tx: {e}")

    async def _attempt_sandwich(self, victim_swap: Dict):
        """Attempt to sandwich this victim's swap"""
        try:
            # Get pool reserves (simplified - need real implementation)
            pool_reserves = await self._get_pool_reserves(victim_swap)

            if not pool_reserves:
                logger.debug("Couldn't get pool reserves")
                return

            # Calculate sandwich opportunity
            opportunity = self.calculator.calculate_sandwich_opportunity(
                victim_swap,
                pool_reserves
            )

            if not opportunity:
                return  # Not profitable

            logger.info(f"\n{Fore.GREEN}{'='*80}")
            logger.info(f"🥪 PROFITABLE SANDWICH FOUND!")
            logger.info(f"{'='*80}{Style.RESET_ALL}")
            logger.info(f"   Victim: ${opportunity['victim_value_usd']:,.0f}")
            logger.info(f"   Net profit: ${opportunity['net_profit_usd']:.2f}")
            logger.info(f"   Path: {opportunity['token_in_symbol']} → {opportunity['token_out_symbol']}")

            # Build and submit sandwich bundle
            success = await self._execute_sandwich(opportunity, victim_swap)

            if success:
                self.sandwiches_successful += 1
                self.total_profit += opportunity['net_profit_usd']
                logger.info(f"{Fore.GREEN}✅ SANDWICH SUCCESSFUL!{Style.RESET_ALL}")
                logger.info(f"   Total profit: ${self.total_profit:.2f}")
            else:
                logger.info(f"{Fore.RED}❌ Sandwich failed{Style.RESET_ALL}")

        except Exception as e:
            logger.error(f"Sandwich attempt error: {e}")

    async def _get_pool_reserves(self, victim_swap: Dict) -> Optional[Dict]:
        """
        Get current pool reserves
        TODO: Implement real pool data fetching
        """
        # This is a placeholder - implement real reserve fetching
        return {
            'reserve0': 1000000 * 1e6,  # 1M USDC
            'reserve1': 500 * 1e18,     # 500 WETH
            'pool_address': '0x...',
            'dex': victim_swap['dex']
        }

    async def _execute_sandwich(
        self,
        opportunity: Dict,
        victim_swap: Dict
    ) -> bool:
        """
        Execute sandwich attack via Flashbots

        Bundle structure:
        1. Our frontrun tx (buy)
        2. Victim's tx
        3. Our backrun tx (sell)
        """
        try:
            self.sandwiches_attempted += 1

            logger.info(f"\n{Fore.YELLOW}🚀 Building sandwich bundle...{Style.RESET_ALL}")

            # TODO: Build actual transactions
            # 1. Frontrun: Buy token_out with token_in
            # 2. Include victim's tx hash
            # 3. Backrun: Sell token_out for token_in

            # TODO: Submit to Flashbots
            # bundle = [frontrun_tx, victim_tx_hash, backrun_tx]
            # flashbots.submit_bundle(bundle, target_block)

            logger.info(f"{Fore.YELLOW}⚠️  Flashbots submission not yet implemented{Style.RESET_ALL}")
            logger.info(f"   (Would submit bundle with bribe: ${opportunity['flashbots_bribe_usd']:.2f})")

            return False  # Not implemented yet

        except Exception as e:
            logger.error(f"Sandwich execution error: {e}")
            return False

    def get_stats(self) -> str:
        """Get bot statistics"""
        success_rate = (self.sandwiches_successful / max(self.sandwiches_attempted, 1)) * 100

        return f"""
{Fore.CYAN}{'='*80}
🥪 SANDWICH BOT STATISTICS
{'='*80}{Style.RESET_ALL}
   Pending swaps seen: {self.pending_swaps_seen:,}
   Sandwiches attempted: {self.sandwiches_attempted}
   Sandwiches successful: {self.sandwiches_successful}
   Success rate: {success_rate:.1f}%
   Total profit: ${self.total_profit:.2f}
{Fore.CYAN}{'='*80}{Style.RESET_ALL}
"""


# Example usage
if __name__ == "__main__":
    import os
    from rpc_mgr import RPCManager

    CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')
    PRIVATE_KEY = os.getenv('PRIVATE_KEY')

    rpc_mgr = RPCManager()

    bot = SandwichBot(
        rpc_manager=rpc_mgr,
        contract_address=CONTRACT_ADDRESS,
        private_key=PRIVATE_KEY,
        flashbots_relay_url="https://relay.flashbots.net"
    )

    # Start monitoring
    asyncio.run(bot.monitor_mempool())
