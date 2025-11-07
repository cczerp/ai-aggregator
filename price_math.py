"""
Price Calculation Module - PRODUCTION READY
Uses actual DEX router/quoter contracts for accurate quotes
No more broken approximation formulas
"""

from web3 import Web3
from typing import Optional, Tuple, Dict, Any
import time


class PriceCalculator:
    """Production-ready price calculator using actual DEX contracts"""
    
    # Uniswap V3 Quoter (Polygon)
    UNISWAP_V3_QUOTER = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"
    
    # QuickSwap Router (Polygon)
    QUICKSWAP_ROUTER = "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff"
    
    # SushiSwap Router (Polygon)
    SUSHISWAP_ROUTER = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"
    
    def __init__(self, w3: Web3, debug: bool = False):
        """
        Initialize with Web3 instance
        
        Args:
            w3: Web3 instance connected to Polygon
            debug: Enable debug output
        """
        self.w3 = w3
        self.debug = debug
        self.cache = {}
        self.cache_duration = 3  # 3 seconds cache
        
        # Initialize quoter contracts
        self._init_contracts()
    
    def _init_contracts(self):
        """Initialize DEX quoter/router contracts"""
        
        # Uniswap V3 Quoter ABI (just the quoteExactInputSingle function)
        v3_quoter_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "name": "quoteExactInputSingle",
                "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        # V2 Router ABI (getAmountsOut function)
        v2_router_abi = [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        try:
            # Uniswap V3 Quoter
            self.v3_quoter = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.UNISWAP_V3_QUOTER),
                abi=v3_quoter_abi
            )
            
            # QuickSwap Router
            self.quickswap_router = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.QUICKSWAP_ROUTER),
                abi=v2_router_abi
            )
            
            # SushiSwap Router
            self.sushiswap_router = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.SUSHISWAP_ROUTER),
                abi=v2_router_abi
            )
            
            if self.debug:
                print("✅ Initialized DEX contracts:")
                print(f"   • Uniswap V3 Quoter: {self.UNISWAP_V3_QUOTER}")
                print(f"   • QuickSwap Router: {self.QUICKSWAP_ROUTER}")
                print(f"   • SushiSwap Router: {self.SUSHISWAP_ROUTER}")
        
        except Exception as e:
            print(f"❌ Error initializing contracts: {e}")
            raise
    
    def get_quote_v3(self, pool_info: Dict[str, Any], token_in: str, token_out: str, 
                     amount_in: int) -> Optional[int]:
        """
        Get accurate quote from Uniswap V3 using Quoter contract
        
        Args:
            pool_info: Dict with 'fee', 'token0', 'token1'
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount in wei
        
        Returns:
            Output amount in wei, or None if failed
        """
        cache_key = f"v3_{pool_info['token0']}_{pool_info['token1']}_{amount_in}_{int(time.time()/self.cache_duration)}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            token_in = Web3.to_checksum_address(token_in)
            token_out = Web3.to_checksum_address(token_out)
            fee = pool_info['fee']
            
            if self.debug:
                print(f"\n[V3 QUOTE] Calling Uniswap V3 Quoter...")
                print(f"  Token In:  {token_in}")
                print(f"  Token Out: {token_out}")
                print(f"  Amount In: {amount_in:,}")
                print(f"  Fee Tier:  {fee} ({fee/10000}%)")
            
            # Call quoter contract with static call
            amount_out = self.v3_quoter.functions.quoteExactInputSingle(
                token_in,
                token_out,
                fee,
                amount_in,
                0  # sqrtPriceLimitX96 = 0 means no limit
            ).call()
            
            if self.debug:
                print(f"  Amount Out: {amount_out:,}")
                if amount_in > 0:
                    ratio = amount_out / amount_in
                    print(f"  Ratio: {ratio:.6f}x")
            
            self.cache[cache_key] = amount_out
            return amount_out
            
        except Exception as e:
            if self.debug:
                print(f"❌ V3 quote failed: {e}")
            return None
    
    def get_quote_v2(self, dex: str, token_in: str, token_out: str, 
                     amount_in: int) -> Optional[int]:
        """
        Get accurate quote from V2-style DEX using router contract
        
        Args:
            dex: DEX name ('quickswap' or 'sushiswap')
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount in wei
        
        Returns:
            Output amount in wei, or None if failed
        """
        cache_key = f"v2_{dex}_{token_in}_{token_out}_{amount_in}_{int(time.time()/self.cache_duration)}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            token_in = Web3.to_checksum_address(token_in)
            token_out = Web3.to_checksum_address(token_out)
            path = [token_in, token_out]
            
            # Select router
            if dex.lower() == 'quickswap':
                router = self.quickswap_router
            elif dex.lower() == 'sushiswap':
                router = self.sushiswap_router
            else:
                if self.debug:
                    print(f"❌ Unknown DEX: {dex}")
                return None
            
            if self.debug:
                print(f"\n[V2 QUOTE] Calling {dex.upper()} Router...")
                print(f"  Token In:  {token_in}")
                print(f"  Token Out: {token_out}")
                print(f"  Amount In: {amount_in:,}")
            
            # Call router getAmountsOut
            amounts = router.functions.getAmountsOut(amount_in, path).call()
            amount_out = amounts[-1]  # Last element is output amount
            
            if self.debug:
                print(f"  Amount Out: {amount_out:,}")
                if amount_in > 0:
                    ratio = amount_out / amount_in
                    print(f"  Ratio: {ratio:.6f}x")
            
            self.cache[cache_key] = amount_out
            return amount_out
            
        except Exception as e:
            if self.debug:
                print(f"❌ V2 quote failed: {e}")
            return None
    
    def get_quote(self, pool_info: Dict[str, Any], token_in: str, token_out: str,
                  amount_in: int) -> Optional[int]:
        """
        Universal quote function - automatically uses correct method based on DEX type
        
        Args:
            pool_info: Pool information dict with 'dex' field
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount in wei
        
        Returns:
            Output amount in wei, or None if failed
        """
        dex = pool_info.get('dex', '').lower()
        
        if 'uniswap' in dex and 'v3' in dex:
            return self.get_quote_v3(pool_info, token_in, token_out, amount_in)
        elif dex in ['quickswap', 'sushiswap']:
            return self.get_quote_v2(dex, token_in, token_out, amount_in)
        else:
            if self.debug:
                print(f"⚠️  Unknown DEX type: {dex}")
            return None
    
    def verify_opportunity(self, buy_pool: Dict, sell_pool: Dict, 
                          token_in: str, intermediate_token: str, token_out: str,
                          amount_in: int) -> Optional[Dict[str, Any]]:
        """
        Verify an arbitrage opportunity using actual quotes
        
        Args:
            buy_pool: Pool to buy from
            sell_pool: Pool to sell to
            token_in: Starting token
            intermediate_token: Middle token
            token_out: Final token (should equal token_in for arb)
            amount_in: Starting amount
        
        Returns:
            Dict with verified amounts and profit, or None if failed
        """
        try:
            # Step 1: Buy intermediate token
            amount_intermediate = self.get_quote(
                buy_pool, 
                token_in, 
                intermediate_token, 
                amount_in
            )
            
            if not amount_intermediate or amount_intermediate <= 0:
                return None
            
            # Step 2: Sell intermediate token
            amount_out = self.get_quote(
                sell_pool,
                intermediate_token,
                token_out,
                amount_intermediate
            )
            
            if not amount_out or amount_out <= 0:
                return None
            
            # Calculate profit
            profit = amount_out - amount_in
            profit_pct = (profit / amount_in * 100) if amount_in > 0 else 0
            
            if self.debug:
                print(f"\n{'='*60}")
                print(f"[VERIFICATION]")
                print(f"{'='*60}")
                print(f"  Start:        {amount_in:,}")
                print(f"  After Buy:    {amount_intermediate:,}")
                print(f"  After Sell:   {amount_out:,}")
                print(f"  Profit:       {profit:,} ({profit_pct:.2f}%)")
                print(f"{'='*60}\n")
            
            return {
                'amount_in': amount_in,
                'amount_intermediate': amount_intermediate,
                'amount_out': amount_out,
                'profit': profit,
                'profit_pct': profit_pct,
                'verified': True
            }
            
        except Exception as e:
            if self.debug:
                print(f"❌ Verification failed: {e}")
            return None
    
    def clear_cache(self):
        """Clear quote cache"""
        self.cache = {}
    
    def set_debug_mode(self, enabled: bool):
        """Enable/disable debug output"""
        self.debug = enabled
        print(f"{'✅' if enabled else '❌'} Debug mode {'ENABLED' if enabled else 'DISABLED'}")


# ============================================================================
# PURE CALCULATION FUNCTIONS (no blockchain calls)
# ============================================================================

def calculate_v2_output_amount(
    amount_in: int,
    reserve_in: int,
    reserve_out: int,
    fee_bps: int = 30
) -> int:
    """
    Calculate V2 output using constant product formula: x * y = k
    Pure math - no blockchain calls

    Args:
        amount_in: Input amount
        reserve_in: Input token reserve
        reserve_out: Output token reserve
        fee_bps: Fee in basis points (30 = 0.3%)

    Returns:
        Output amount
    """
    if amount_in == 0 or reserve_in == 0 or reserve_out == 0:
        return 0

    # Apply fee
    amount_in_with_fee = amount_in * (10000 - fee_bps)

    # Constant product formula: (x + Δx) * (y - Δy) = x * y
    numerator = amount_in_with_fee * reserve_out
    denominator = (reserve_in * 10000) + amount_in_with_fee

    if denominator == 0:
        return 0

    return numerator // denominator


def calculate_v3_output_amount(
    amount_in: int,
    sqrt_price_x96: int,
    liquidity: int,
    fee_bps: int,
    token_in_is_token0: bool,
    decimals0: int = 18,
    decimals1: int = 18
) -> int:
    """
    Calculate V3 output (simplified approximation)
    Pure math - no blockchain calls

    Note: This is a simplified calculation. Real V3 math involves tick math
    and liquidity distribution, which is complex. For precise quotes, use
    the V3 quoter contract.

    Args:
        amount_in: Input amount
        sqrt_price_x96: Current sqrt price
        liquidity: Pool liquidity
        fee_bps: Fee in basis points
        token_in_is_token0: True if swapping token0 for token1
        decimals0: Token0 decimals
        decimals1: Token1 decimals

    Returns:
        Output amount (approximate)
    """
    if amount_in == 0 or liquidity == 0 or sqrt_price_x96 == 0:
        return 0

    # Apply fee
    amount_in_with_fee = amount_in * (10000 - fee_bps) // 10000

    # Calculate price from sqrt_price_x96
    price = (sqrt_price_x96 / (2 ** 96)) ** 2

    # Adjust for decimals
    price_adjusted = price * (10 ** decimals0) / (10 ** decimals1)

    if token_in_is_token0:
        # Swapping token0 -> token1
        amount_out = int(amount_in_with_fee * price_adjusted)
    else:
        # Swapping token1 -> token0
        amount_out = int(amount_in_with_fee / price_adjusted) if price_adjusted > 0 else 0

    return amount_out


def get_price_from_v2_reserves(
    reserve0: int,
    reserve1: int,
    decimals0: int = 18,
    decimals1: int = 18
) -> float:
    """
    Get price of token0 in terms of token1 from V2 reserves
    Pure math - no blockchain calls

    Args:
        reserve0: Reserve of token0
        reserve1: Reserve of token1
        decimals0: Token0 decimals
        decimals1: Token1 decimals

    Returns:
        Price of token0 in terms of token1
    """
    if reserve0 == 0:
        return 0.0

    # Adjust for decimals
    adjusted_reserve0 = reserve0 / (10 ** decimals0)
    adjusted_reserve1 = reserve1 / (10 ** decimals1)

    # Price: token1 per token0
    return adjusted_reserve1 / adjusted_reserve0


def get_price_from_v3_sqrt_price(
    sqrt_price_x96: int,
    decimals0: int = 18,
    decimals1: int = 18
) -> float:
    """
    Get price of token0 in terms of token1 from V3 sqrt price
    Pure math - no blockchain calls

    Args:
        sqrt_price_x96: Sqrt price X96 from V3 pool
        decimals0: Token0 decimals
        decimals1: Token1 decimals

    Returns:
        Price of token0 in terms of token1
    """
    if sqrt_price_x96 == 0:
        return 0.0

    # Decode sqrt_price_x96 to actual price
    price = (sqrt_price_x96 / (2 ** 96)) ** 2

    # Adjust for decimals
    price_adjusted = price * (10 ** decimals0) / (10 ** decimals1)

    return price_adjusted