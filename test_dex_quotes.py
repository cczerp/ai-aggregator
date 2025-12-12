#!/usr/bin/env python3
"""Quick test to check which DEXes have working quotes"""

from web3 import Web3
from registries import DEXES, TOKENS
from rpc_mgr import RPCManager
from abis import UNISWAP_V2_ROUTER_ABI

rpc_mgr = RPCManager()
endpoint = rpc_mgr.get_available_endpoint("primary")
w3 = rpc_mgr.get_web3(endpoint)

# Test with 1 WETH
amount_in = 1 * 10**18

print("\n🔍 Testing DEX routers for WETH → USDC quotes...\n")

for dex_name, dex_info in DEXES.items():
    if dex_info.get('type') != 'v2':
        continue

    router_address = dex_info.get('router')
    if not router_address:
        print(f"❌ {dex_name:20s} - No router configured")
        continue

    try:
        router = w3.eth.contract(
            address=Web3.to_checksum_address(router_address),
            abi=UNISWAP_V2_ROUTER_ABI
        )

        path = [
            Web3.to_checksum_address(TOKENS['WETH']['address']),
            Web3.to_checksum_address(TOKENS['USDC']['address'])
        ]

        amounts_out = router.functions.getAmountsOut(amount_in, path).call()
        usdc_out = amounts_out[1] / 10**6  # USDC has 6 decimals

        print(f"✅ {dex_name:20s} - 1 WETH = {usdc_out:,.2f} USDC")

    except Exception as e:
        error_msg = str(e)[:60]
        print(f"❌ {dex_name:20s} - {error_msg}")

print("\n✅ Test complete\n")
