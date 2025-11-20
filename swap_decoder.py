"""
Swap Function ABI Decoder
Decodes transaction input data for DEX swap functions to extract:
- Swap amounts (amountIn, amountOutMin)
- Token paths
- Recipient addresses
- Deadlines

Supports:
- Uniswap V2-style: swapExactTokensForTokens, swapTokensForExactTokens, etc.
- Uniswap V3-style: exactInputSingle, exactInput
"""

from typing import Dict, List, Optional, Tuple
from web3 import Web3
from eth_abi import decode as abi_decode
from colorama import Fore, Style, init
import logging

init(autoreset=True)
logger = logging.getLogger(__name__)


class SwapDecoder:
    """Decode swap function calls from transaction input data"""

    # Function signatures (4-byte selectors)
    SIGNATURES = {
        # Uniswap V2 / QuickSwap / SushiSwap
        '0x38ed1739': {
            'name': 'swapExactTokensForTokens',
            'params': ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
            'param_names': ['amountIn', 'amountOutMin', 'path', 'to', 'deadline']
        },
        '0x8803dbee': {
            'name': 'swapTokensForExactTokens',
            'params': ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
            'param_names': ['amountOut', 'amountInMax', 'path', 'to', 'deadline']
        },
        '0x7ff36ab5': {
            'name': 'swapExactETHForTokens',
            'params': ['uint256', 'address[]', 'address', 'uint256'],
            'param_names': ['amountOutMin', 'path', 'to', 'deadline']
        },
        '0x18cbafe5': {
            'name': 'swapExactTokensForETH',
            'params': ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
            'param_names': ['amountIn', 'amountOutMin', 'path', 'to', 'deadline']
        },
        '0x4a25d94a': {
            'name': 'swapTokensForExactETH',
            'params': ['uint256', 'uint256', 'address[]', 'address', 'uint256'],
            'param_names': ['amountOut', 'amountInMax', 'path', 'to', 'deadline']
        },
        '0xfb3bdb41': {
            'name': 'swapETHForExactTokens',
            'params': ['uint256', 'address[]', 'address', 'uint256'],
            'param_names': ['amountOut', 'path', 'to', 'deadline']
        },

        # Uniswap V3
        '0x414bf389': {
            'name': 'exactInputSingle',
            'params': ['(address,address,uint24,address,uint256,uint256,uint256,uint160)'],
            'param_names': ['params'],  # Tuple: tokenIn, tokenOut, fee, recipient, deadline, amountIn, amountOutMin, sqrtPriceLimitX96
            'is_tuple': True
        },
        '0xc04b8d59': {
            'name': 'exactInput',
            'params': ['(bytes,address,uint256,uint256,uint256)'],
            'param_names': ['params'],  # Tuple: path (encoded), recipient, deadline, amountIn, amountOutMin
            'is_tuple': True
        },
        '0xdb3e2198': {
            'name': 'exactOutputSingle',
            'params': ['(address,address,uint24,address,uint256,uint256,uint256,uint160)'],
            'param_names': ['params'],
            'is_tuple': True
        },
        '0x5023b4df': {
            'name': 'exactOutput',
            'params': ['(bytes,address,uint256,uint256,uint256)'],
            'param_names': ['params'],
            'is_tuple': True
        }
    }

    def __init__(self):
        logger.info(f"{Fore.GREEN}✅ Swap Decoder initialized{Style.RESET_ALL}")
        logger.info(f"   Supported signatures: {len(self.SIGNATURES)}")

    def decode_input(self, input_data: str) -> Optional[Dict]:
        """
        Decode transaction input data

        Args:
            input_data: Transaction input data (0x prefixed hex string)

        Returns:
            Dict with decoded parameters, or None if not a known swap function
        """
        if not input_data or len(input_data) < 10:
            return None

        # Extract function signature (first 4 bytes = 8 hex chars + 0x)
        sig = input_data[:10].lower()

        if sig not in self.SIGNATURES:
            return None

        func_info = self.SIGNATURES[sig]
        func_name = func_info['name']

        try:
            # Remove signature, leaving just parameters
            encoded_params = input_data[10:]

            if not encoded_params:
                return None

            # Decode based on function type
            if func_info.get('is_tuple'):
                decoded = self._decode_tuple_params(encoded_params, func_info)
            else:
                decoded = self._decode_simple_params(encoded_params, func_info)

            if decoded:
                decoded['function'] = func_name
                decoded['signature'] = sig
                return decoded

        except Exception as e:
            logger.debug(f"Failed to decode {func_name}: {e}")
            return None

    def _decode_simple_params(self, encoded_params: str, func_info: Dict) -> Optional[Dict]:
        """Decode simple (non-tuple) function parameters"""
        try:
            # Decode using eth_abi
            decoded_values = abi_decode(
                func_info['params'],
                bytes.fromhex(encoded_params)
            )

            # Map to parameter names
            result = {}
            for i, param_name in enumerate(func_info['param_names']):
                value = decoded_values[i]

                # Convert address arrays to checksummed addresses
                if param_name == 'path' and isinstance(value, list):
                    result[param_name] = [Web3.to_checksum_address(addr) for addr in value]
                elif param_name in ['to', 'from'] and isinstance(value, str):
                    result[param_name] = Web3.to_checksum_address(value)
                else:
                    result[param_name] = value

            return result

        except Exception as e:
            logger.debug(f"Simple decode failed: {e}")
            return None

    def _decode_tuple_params(self, encoded_params: str, func_info: Dict) -> Optional[Dict]:
        """Decode tuple-style function parameters (Uniswap V3)"""
        try:
            func_name = func_info['name']

            # Decode the tuple
            decoded_tuple = abi_decode(
                func_info['params'],
                bytes.fromhex(encoded_params)
            )[0]  # First element is the tuple

            result = {}

            if func_name == 'exactInputSingle':
                # (tokenIn, tokenOut, fee, recipient, deadline, amountIn, amountOutMin, sqrtPriceLimitX96)
                result['tokenIn'] = Web3.to_checksum_address(decoded_tuple[0])
                result['tokenOut'] = Web3.to_checksum_address(decoded_tuple[1])
                result['fee'] = decoded_tuple[2]
                result['recipient'] = Web3.to_checksum_address(decoded_tuple[3])
                result['deadline'] = decoded_tuple[4]
                result['amountIn'] = decoded_tuple[5]
                result['amountOutMin'] = decoded_tuple[6]
                result['sqrtPriceLimitX96'] = decoded_tuple[7]
                result['path'] = [result['tokenIn'], result['tokenOut']]

            elif func_name == 'exactInput':
                # (path, recipient, deadline, amountIn, amountOutMin)
                path_encoded = decoded_tuple[0]
                result['path'] = self._decode_v3_path(path_encoded)
                result['recipient'] = Web3.to_checksum_address(decoded_tuple[1])
                result['deadline'] = decoded_tuple[2]
                result['amountIn'] = decoded_tuple[3]
                result['amountOutMin'] = decoded_tuple[4]

                if result['path']:
                    result['tokenIn'] = result['path'][0]
                    result['tokenOut'] = result['path'][-1]

            elif func_name == 'exactOutputSingle':
                # Similar to exactInputSingle but with amountOut/amountInMax
                result['tokenIn'] = Web3.to_checksum_address(decoded_tuple[0])
                result['tokenOut'] = Web3.to_checksum_address(decoded_tuple[1])
                result['fee'] = decoded_tuple[2]
                result['recipient'] = Web3.to_checksum_address(decoded_tuple[3])
                result['deadline'] = decoded_tuple[4]
                result['amountOut'] = decoded_tuple[5]
                result['amountInMax'] = decoded_tuple[6]
                result['sqrtPriceLimitX96'] = decoded_tuple[7]
                result['path'] = [result['tokenIn'], result['tokenOut']]

            elif func_name == 'exactOutput':
                path_encoded = decoded_tuple[0]
                result['path'] = self._decode_v3_path(path_encoded)
                result['recipient'] = Web3.to_checksum_address(decoded_tuple[1])
                result['deadline'] = decoded_tuple[2]
                result['amountOut'] = decoded_tuple[3]
                result['amountInMax'] = decoded_tuple[4]

                if result['path']:
                    result['tokenIn'] = result['path'][0]
                    result['tokenOut'] = result['path'][-1]

            return result

        except Exception as e:
            logger.debug(f"Tuple decode failed: {e}")
            return None

    def _decode_v3_path(self, path_bytes: bytes) -> List[str]:
        """
        Decode Uniswap V3 encoded path
        Format: [token0 (20 bytes), fee0 (3 bytes), token1 (20 bytes), fee1 (3 bytes), token2 (20 bytes), ...]
        """
        try:
            path = []
            i = 0

            while i < len(path_bytes):
                # Extract token address (20 bytes)
                if i + 20 > len(path_bytes):
                    break

                token = Web3.to_checksum_address('0x' + path_bytes[i:i+20].hex())
                path.append(token)
                i += 20

                # Skip fee (3 bytes) if present
                if i + 3 <= len(path_bytes):
                    i += 3

            return path

        except Exception as e:
            logger.debug(f"V3 path decode failed: {e}")
            return []

    def get_swap_summary(self, decoded: Dict, token_symbols: Optional[Dict[str, str]] = None) -> str:
        """
        Generate human-readable summary of decoded swap

        Args:
            decoded: Decoded swap parameters
            token_symbols: Optional dict mapping addresses to symbols

        Returns:
            Formatted summary string
        """
        if not decoded:
            return "Unknown swap"

        func = decoded.get('function', 'Unknown')
        path = decoded.get('path', [])

        # Convert addresses to symbols if available
        if token_symbols:
            path_display = ' → '.join([
                token_symbols.get(addr, addr[:6] + '...')
                for addr in path
            ])
        else:
            path_display = ' → '.join([addr[:6] + '...' for addr in path])

        # Extract amounts
        amount_in = decoded.get('amountIn', decoded.get('amountInMax', 0))
        amount_out = decoded.get('amountOutMin', decoded.get('amountOut', 0))

        lines = [
            f"Function: {func}",
            f"Path: {path_display} ({len(path)} hops)",
            f"Amount In: {amount_in:,}",
            f"Amount Out Min: {amount_out:,}",
        ]

        if 'fee' in decoded:
            fee_pct = decoded['fee'] / 10000
            lines.append(f"Fee Tier: {fee_pct}%")

        if 'deadline' in decoded:
            lines.append(f"Deadline: {decoded['deadline']}")

        return '\n'.join(lines)


# Example usage
if __name__ == "__main__":
    decoder = SwapDecoder()

    # Test with example swap transaction input
    # This is swapExactTokensForTokens with 1000 USDC -> WETH
    test_input = "0x38ed17390000000000000000000000000000000000000000000000000000000003b9aca00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000001234567890abcdef1234567890abcdef123456780000000000000000000000000000000000000000000000000000000063d5f0000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"

    result = decoder.decode_input(test_input)

    if result:
        print(f"\n{Fore.GREEN}✅ Decoded successfully:{Style.RESET_ALL}")
        print(f"Function: {result['function']}")
        print(f"Amount In: {result.get('amountIn', 0):,}")
        print(f"Amount Out Min: {result.get('amountOutMin', 0):,}")
        print(f"Path: {result.get('path', [])}")
        print(f"Recipient: {result.get('to', 'N/A')}")
    else:
        print(f"{Fore.RED}❌ Failed to decode{Style.RESET_ALL}")
