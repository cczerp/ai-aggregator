#!/usr/bin/env python3
"""
Pool Discovery Script
Scans DEX factory contracts for PairCreated events to discover all active pools
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, List
from web3 import Web3
from colorama import Fore, Style, init

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from registries import DEXES, TOKENS
from rpc_mgr import RPCManager

init(autoreset=True)

# Uniswap V2 Factory ABI (PairCreated event)
FACTORY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "token0", "type": "address"},
            {"indexed": True, "name": "token1", "type": "address"},
            {"indexed": False, "name": "pair", "type": "address"},
            {"indexed": False, "name": "", "type": "uint256"}
        ],
        "name": "PairCreated",
        "type": "event"
    }
]


class PoolDiscoverer:
    """Discovers pools by scanning factory contracts for PairCreated events"""

    def __init__(self, rpc_manager: RPCManager):
        self.rpc_manager = rpc_manager
        endpoint = rpc_manager.get_available_endpoint("primary")
        if not endpoint:
            raise Exception("No RPC endpoint available")
        self.w3 = rpc_manager.get_web3(endpoint)

        # Token address -> symbol mapping
        self.address_to_symbol = {}
        for symbol, info in TOKENS.items():
            self.address_to_symbol[info["address"].lower()] = symbol

        print(f"{Fore.GREEN}✅ Pool Discoverer initialized{Style.RESET_ALL}")
        print(f"   Tracking {len(TOKENS)} tokens across {len(DEXES)} DEXes")

    def get_token_symbol(self, address: str) -> str:
        """Get token symbol from address, or return shortened address if unknown"""
        addr_lower = address.lower()
        if addr_lower in self.address_to_symbol:
            return self.address_to_symbol[addr_lower]
        return f"{address[:6]}...{address[-4:]}"

    def discover_v2_pools(
        self,
        dex_name: str,
        factory_address: str,
        from_block: int = 0,
        to_block: str = 'latest',
        chunk_size: int = 10000
    ) -> List[Dict]:
        """
        Discover V2 pools by scanning PairCreated events
        """
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"🔍 DISCOVERING POOLS: {dex_name}")
        print(f"{'='*80}{Style.RESET_ALL}")
        print(f"   Factory: {factory_address}")
        print(f"   Blocks: {from_block} → {to_block}")

        factory = self.w3.eth.contract(
            address=Web3.to_checksum_address(factory_address),
            abi=FACTORY_ABI
        )

        # Get current block if using 'latest'
        if to_block == 'latest':
            to_block = self.w3.eth.block_number

        discovered_pools = []
        tracked_pools = []

        # Scan in chunks
        current_block = from_block

        while current_block < to_block:
            chunk_end = min(current_block + chunk_size, to_block)

            try:
                events = factory.events.PairCreated.get_logs(
                    fromBlock=current_block,
                    toBlock=chunk_end
                )

                for event in events:
                    token0 = event['args']['token0']
                    token1 = event['args']['token1']
                    pair = event['args']['pair']

                    token0_symbol = self.get_token_symbol(token0)
                    token1_symbol = self.get_token_symbol(token1)

                    pool_data = {
                        'dex': dex_name,
                        'pair_address': pair,
                        'token0': token0,
                        'token1': token1,
                        'token0_symbol': token0_symbol,
                        'token1_symbol': token1_symbol,
                        'block_number': event['blockNumber'],
                    }

                    discovered_pools.append(pool_data)

                    # Only track if both tokens are in our registry
                    if (token0.lower() in self.address_to_symbol and
                        token1.lower() in self.address_to_symbol):
                        tracked_pools.append(pool_data)
                        print(f"  ✅ {token0_symbol}/{token1_symbol} → {pair[:10]}...")

                progress = ((chunk_end - from_block) / (to_block - from_block)) * 100
                print(f"  📊 Progress: {progress:.1f}%", end='\r')

                current_block = chunk_end + 1

            except Exception as e:
                print(f"\n  ⚠️  Error at block {current_block}: {str(e)[:80]}")
                current_block = chunk_end + 1

        print(f"\n\n{Fore.GREEN}✅ Discovery complete!{Style.RESET_ALL}")
        print(f"   Total pools found: {len(discovered_pools)}")
        print(f"   Tracked pools: {len(tracked_pools)}")

        return tracked_pools


if __name__ == "__main__":
    rpc_mgr = RPCManager()
    discoverer = PoolDiscoverer(rpc_mgr)

    # Example: Discover QuickSwap pools from last 10000 blocks
    current_block = discoverer.w3.eth.block_number
    pools = discoverer.discover_v2_pools(
        dex_name='QuickSwap_V2',
        factory_address=DEXES['QuickSwap_V2']['factory'],
        from_block=current_block - 10000
    )

    print(f"\n💾 Discovered {len(pools)} QuickSwap pools")
