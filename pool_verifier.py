#!/usr/bin/env python3
"""
Pool Verifier Script
Verifies pool discovery results using alternate methods
- Tests both token orderings
- Checks pool liquidity
- Uses multiple discovery approaches
- Provides detailed diagnostic information
"""

from web3 import Web3
import json
import os
from dotenv import load_dotenv
from registries import TOKENS, DEXES, get_token_address
import sys

load_dotenv()

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(f"https://polygon-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY')}"))

# Extended ABIs for verification
V2_FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"}
        ],
        "name": "getPair",
        "outputs": [{"internalType": "address", "name": "pair", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "allPairsLength",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "type": "function"
    }
]

V3_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

ALGEBRA_FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"}
        ],
        "name": "poolByPair",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Pool ABI to check reserves/liquidity
PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "type": "function"
    }
]

V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]


def verify_v2_pool_both_orderings(factory_address, token0, token1):
    """Try both token orderings for V2 pool"""
    results = {}
    factory = w3.eth.contract(address=Web3.to_checksum_address(factory_address), abi=V2_FACTORY_ABI)
    
    # Try token0/token1
    try:
        pool1 = factory.functions.getPair(
            Web3.to_checksum_address(get_token_address(token0)),
            Web3.to_checksum_address(get_token_address(token1))
        ).call()
        results['order1'] = pool1 if pool1 != "0x0000000000000000000000000000000000000000" else None
    except Exception as e:
        results['order1_error'] = str(e)
    
    # Try token1/token0
    try:
        pool2 = factory.functions.getPair(
            Web3.to_checksum_address(get_token_address(token1)),
            Web3.to_checksum_address(get_token_address(token0))
        ).call()
        results['order2'] = pool2 if pool2 != "0x0000000000000000000000000000000000000000" else None
    except Exception as e:
        results['order2_error'] = str(e)
    
    return results


def verify_v3_pool_both_orderings(factory_address, token0, token1, fee):
    """Try both token orderings for V3 pool"""
    results = {}
    factory = w3.eth.contract(address=Web3.to_checksum_address(factory_address), abi=V3_FACTORY_ABI)
    
    # Try token0/token1
    try:
        pool1 = factory.functions.getPool(
            Web3.to_checksum_address(get_token_address(token0)),
            Web3.to_checksum_address(get_token_address(token1)),
            fee
        ).call()
        results['order1'] = pool1 if pool1 != "0x0000000000000000000000000000000000000000" else None
    except Exception as e:
        results['order1_error'] = str(e)
    
    # Try token1/token0
    try:
        pool2 = factory.functions.getPool(
            Web3.to_checksum_address(get_token_address(token1)),
            Web3.to_checksum_address(get_token_address(token0)),
            fee
        ).call()
        results['order2'] = pool2 if pool2 != "0x0000000000000000000000000000000000000000" else None
    except Exception as e:
        results['order2_error'] = str(e)
    
    return results


def check_pool_liquidity(pool_address, pool_type="v2"):
    """Check if a pool has liquidity"""
    try:
        if pool_type == "v2":
            pair = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=PAIR_ABI)
            reserves = pair.functions.getReserves().call()
            reserve0, reserve1 = reserves[0], reserves[1]
            
            # Get actual tokens in the pool
            token0 = pair.functions.token0().call()
            token1 = pair.functions.token1().call()
            
            return {
                'reserve0': reserve0,
                'reserve1': reserve1,
                'has_liquidity': reserve0 > 0 and reserve1 > 0,
                'token0': token0,
                'token1': token1
            }
        
        elif pool_type in ["v3", "v3_algebra"]:
            pool = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=V3_POOL_ABI)
            liquidity = pool.functions.liquidity().call()
            
            # Get actual tokens in the pool
            token0 = pool.functions.token0().call()
            token1 = pool.functions.token1().call()
            
            return {
                'liquidity': liquidity,
                'has_liquidity': liquidity > 0,
                'token0': token0,
                'token1': token1
            }
    except Exception as e:
        return {'error': str(e)}


def verify_missing_pairs(registry_file="pool_registry.json", focus_pairs=None):
    """
    Verify pairs that were marked as missing
    focus_pairs: List of (token0, token1) tuples to verify, or None for all missing
    """
    
    # Load registry
    try:
        with open(registry_file, 'r') as f:
            registry = json.load(f)
    except FileNotFoundError:
        print(f"❌ Registry file {registry_file} not found. Run discover_pools.py first.")
        return
    
    print("=" * 80)
    print("POOL VERIFICATION - ALTERNATE METHODS")
    print("=" * 80)
    
    # If no focus pairs specified, find all missing pairs
    if focus_pairs is None:
        # Generate expected pairs from discover script
        from discover_pools import generate_trading_pairs, get_all_token_symbols
        token_symbols = get_all_token_symbols()
        all_pairs = generate_trading_pairs(token_symbols)
        
        # Find which pairs are missing from registry
        found_pairs = set()
        for dex_name, pairs_dict in registry.items():
            for pair_name in pairs_dict.keys():
                found_pairs.add(pair_name)
        
        all_pair_names = {f"{t0}/{t1}" for t0, t1 in all_pairs}
        missing_pair_names = all_pair_names - found_pairs
        
        # Convert back to tuples
        focus_pairs = []
        for pair_name in missing_pair_names:
            t0, t1 = pair_name.split('/')
            focus_pairs.append((t0, t1))
        
        print(f"🔍 Found {len(focus_pairs)} missing pairs to verify\n")
    else:
        print(f"🔍 Verifying {len(focus_pairs)} specified pairs\n")
    
    if not focus_pairs:
        print("✅ No missing pairs to verify!")
        return
    
    # Verify each missing pair on each DEX
    verification_results = {}
    
    for token0, token1 in focus_pairs:
        pair_name = f"{token0}/{token1}"
        print(f"\n{'=' * 80}")
        print(f"Verifying: {pair_name}")
        print(f"{'=' * 80}")
        
        verification_results[pair_name] = {}
        
        for dex_name, dex_config in DEXES.items():
            dex_type = dex_config.get("type", "")
            
            # Skip special types
            if dex_type in ["curve", "balancer", "dodo"]:
                continue
            
            print(f"\n  {dex_name} ({dex_type}):")
            
            if dex_type == "v2":
                results = verify_v2_pool_both_orderings(dex_config["factory"], token0, token1)
                
                if results.get('order1'):
                    print(f"    ✅ Found with ordering {token0}/{token1}: {results['order1']}")
                    liquidity_info = check_pool_liquidity(results['order1'], "v2")
                    if liquidity_info.get('has_liquidity'):
                        print(f"       💰 Has liquidity: R0={liquidity_info['reserve0']}, R1={liquidity_info['reserve1']}")
                    else:
                        print(f"       ⚠️  Pool exists but has NO liquidity")
                    verification_results[pair_name][dex_name] = results['order1']
                    
                elif results.get('order2'):
                    print(f"    ✅ Found with ordering {token1}/{token0}: {results['order2']}")
                    liquidity_info = check_pool_liquidity(results['order2'], "v2")
                    if liquidity_info.get('has_liquidity'):
                        print(f"       💰 Has liquidity: R0={liquidity_info['reserve0']}, R1={liquidity_info['reserve1']}")
                    else:
                        print(f"       ⚠️  Pool exists but has NO liquidity")
                    verification_results[pair_name][dex_name] = results['order2']
                    
                else:
                    print(f"    ❌ Confirmed: No pool exists")
                    if 'order1_error' in results or 'order2_error' in results:
                        print(f"       Errors: {results}")
            
            elif dex_type == "v3":
                fee_tiers = dex_config.get("fee_tiers", [500, 3000, 10000])
                found_any = False
                
                for fee in fee_tiers:
                    results = verify_v3_pool_both_orderings(dex_config["factory"], token0, token1, fee)
                    
                    if results.get('order1') or results.get('order2'):
                        pool_addr = results.get('order1') or results.get('order2')
                        print(f"    ✅ Found pool (fee={fee}): {pool_addr}")
                        liquidity_info = check_pool_liquidity(pool_addr, "v3")
                        if liquidity_info.get('has_liquidity'):
                            print(f"       💰 Has liquidity: {liquidity_info['liquidity']}")
                        else:
                            print(f"       ⚠️  Pool exists but has NO liquidity")
                        found_any = True
                        
                        if dex_name not in verification_results[pair_name]:
                            verification_results[pair_name][dex_name] = {}
                        verification_results[pair_name][dex_name][fee] = pool_addr
                
                if not found_any:
                    print(f"    ❌ Confirmed: No pools exist for any fee tier")
            
            elif dex_type == "v3_algebra":
                results = verify_v2_pool_both_orderings(dex_config["factory"], token0, token1)
                
                if results.get('order1'):
                    print(f"    ✅ Found: {results['order1']}")
                    liquidity_info = check_pool_liquidity(results['order1'], "v3_algebra")
                    if liquidity_info.get('has_liquidity'):
                        print(f"       💰 Has liquidity: {liquidity_info['liquidity']}")
                    else:
                        print(f"       ⚠️  Pool exists but has NO liquidity")
                    verification_results[pair_name][dex_name] = results['order1']
                    
                elif results.get('order2'):
                    print(f"    ✅ Found: {results['order2']}")
                    liquidity_info = check_pool_liquidity(results['order2'], "v3_algebra")
                    if liquidity_info.get('has_liquidity'):
                        print(f"       💰 Has liquidity: {liquidity_info['liquidity']}")
                    else:
                        print(f"       ⚠️  Pool exists but has NO liquidity")
                    verification_results[pair_name][dex_name] = results['order2']
                    
                else:
                    print(f"    ❌ Confirmed: No pool exists")
    
    # Summary
    print(f"\n{'=' * 80}")
    print("VERIFICATION SUMMARY")
    print(f"{'=' * 80}")
    
    newly_found = {}
    truly_missing = []
    
    for pair_name, dexes in verification_results.items():
        if dexes:
            newly_found[pair_name] = dexes
        else:
            truly_missing.append(pair_name)
    
    if newly_found:
        print(f"\n🎉 NEWLY DISCOVERED POOLS: {len(newly_found)}")
        for pair_name, dexes in newly_found.items():
            print(f"\n  {pair_name}:")
            for dex_name, pool_info in dexes.items():
                if isinstance(pool_info, dict):
                    print(f"    - {dex_name}: {len(pool_info)} fee tiers")
                else:
                    print(f"    - {dex_name}: {pool_info}")
        
        # Save newly found pools
        save_file = "newly_discovered_pools.json"
        with open(save_file, 'w') as f:
            json.dump(newly_found, f, indent=2)
        print(f"\n💾 Saved newly discovered pools to {save_file}")
    
    if truly_missing:
        print(f"\n❌ CONFIRMED MISSING: {len(truly_missing)}")
        for pair_name in truly_missing:
            print(f"  - {pair_name}")
        print("\nThese pairs genuinely don't have pools on Polygon")
    
    if not newly_found and not truly_missing:
        print("\n✅ All pools verified! Discovery script is accurate.")


def verify_specific_pair(token0, token1):
    """Verify a specific pair across all DEXes"""
    print(f"\n🔍 Verifying specific pair: {token0}/{token1}\n")
    verify_missing_pairs(focus_pairs=[(token0, token1)])


if __name__ == "__main__":
    if not os.getenv('ALCHEMY_API_KEY'):
        print("❌ ERROR: ALCHEMY_API_KEY not found in .env file")
        sys.exit(1)
    
    # Check command line arguments
    if len(sys.argv) == 3:
        # Verify specific pair
        token0, token1 = sys.argv[1].upper(), sys.argv[2].upper()
        verify_specific_pair(token0, token1)
    else:
        # Verify all missing pairs
        print("\n🔬 Starting pool verification with alternate methods...")
        print("This will verify all pairs that were marked as missing\n")
        verify_missing_pairs()
        
        print("\n💡 TIP: To verify a specific pair, run:")
        print("   python pool_verifier.py TOKEN0 TOKEN1")
        print("   Example: python pool_verifier.py WPOL SNX\n")