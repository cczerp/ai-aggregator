#!/usr/bin/env python3
"""
Dynamic Pool Discovery Script with Persistent Cache
- Caches "no pool found" results per DEX to avoid re-checking
- Only re-checks failed pairs after 30 days
- Outputs to pool_registry.json and failed_pairs.json
"""

from web3 import Web3
import json
import os
import time
from dotenv import load_dotenv
from itertools import combinations
import sys

# Import from registries
from registries import TOKENS, DEXES, get_token_address, get_all_token_symbols

load_dotenv()

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(f"https://polygon-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY')}"))

# Cache settings
FAILED_PAIRS_FILE = "failed_pairs.json"
RECHECK_AFTER_DAYS = 30  # Re-check failed pairs after 30 days

# ABIs
V2_FACTORY_ABI = [{"constant": True, "inputs": [{"internalType": "address", "name": "tokenA", "type": "address"}, {"internalType": "address", "name": "tokenB", "type": "address"}], "name": "getPair", "outputs": [{"internalType": "address", "name": "pair", "type": "address"}], "type": "function"}]
V3_FACTORY_ABI = [{"inputs": [{"internalType": "address", "name": "tokenA", "type": "address"}, {"internalType": "address", "name": "tokenB", "type": "address"}, {"internalType": "uint24", "name": "fee", "type": "uint24"}], "name": "getPool", "outputs": [{"internalType": "address", "name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"}]
ALGEBRA_FACTORY_ABI = [{"inputs": [{"internalType": "address", "name": "tokenA", "type": "address"}, {"internalType": "address", "name": "tokenB", "type": "address"}], "name": "poolByPair", "outputs": [{"internalType": "address", "name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"}]


def load_failed_pairs():
    """Load the persistent cache of pairs with no pools"""
    if os.path.exists(FAILED_PAIRS_FILE):
        with open(FAILED_PAIRS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_failed_pairs(failed_pairs):
    """Save the cache of pairs with no pools"""
    with open(FAILED_PAIRS_FILE, 'w') as f:
        json.dump(failed_pairs, f, indent=2)


def should_check_pair(failed_pairs, dex_name, pair_name):
    """Check if we should query this DEX+pair combo"""
    if dex_name not in failed_pairs:
        return True
    if pair_name not in failed_pairs[dex_name]:
        return True
    # Check if it's been more than RECHECK_AFTER_DAYS
    last_checked = failed_pairs[dex_name][pair_name]
    days_since = (time.time() - last_checked) / 86400
    return days_since > RECHECK_AFTER_DAYS


def mark_pair_as_failed(failed_pairs, dex_name, pair_name):
    """Mark a DEX+pair combo as having no pool"""
    if dex_name not in failed_pairs:
        failed_pairs[dex_name] = {}
    failed_pairs[dex_name][pair_name] = time.time()


def generate_trading_pairs(token_symbols, focus_tokens=["USDT", "USDC", "WETH", "WPOL"]):
    pairs = set()
    for token in token_symbols:
        for focus_token in focus_tokens:
            if token != focus_token:
                pairs.add(tuple(sorted([token, focus_token])))
    major_tokens = ["WBTC", "DAI", "UNI", "AAVE", "LINK", "SUSHI", "QUICK", "CRV"]
    available_majors = [t for t in major_tokens if t in token_symbols]
    for t1, t2 in combinations(available_majors, 2):
        pairs.add(tuple(sorted([t1, t2])))
    return [(t0, t1) for t0, t1 in sorted(pairs)]


def discover_v2_pool(factory_address, token0, token1):
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(factory_address), abi=V2_FACTORY_ABI)
        pool = factory.functions.getPair(Web3.to_checksum_address(get_token_address(token0)), Web3.to_checksum_address(get_token_address(token1))).call()
        if pool != "0x0000000000000000000000000000000000000000":
            return pool
        return None
    except:
        return None


def discover_v3_pool(factory_address, token0, token1, fee):
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(factory_address), abi=V3_FACTORY_ABI)
        pool = factory.functions.getPool(Web3.to_checksum_address(get_token_address(token0)), Web3.to_checksum_address(get_token_address(token1)), fee).call()
        if pool != "0x0000000000000000000000000000000000000000":
            return pool
        return None
    except:
        return None


def discover_algebra_pool(factory_address, token0, token1):
    try:
        factory = w3.eth.contract(address=Web3.to_checksum_address(factory_address), abi=ALGEBRA_FACTORY_ABI)
        pool = factory.functions.poolByPair(Web3.to_checksum_address(get_token_address(token0)), Web3.to_checksum_address(get_token_address(token1))).call()
        if pool != "0x0000000000000000000000000000000000000000":
            return pool
        return None
    except:
        return None


def discover_pools_for_dex(dex_name, dex_config, pairs, failed_pairs, stats):
    dex_pools = {}
    dex_type = dex_config.get("type", "")
    print(f"\n🔍 {dex_name.upper()} ({dex_type})")
    
    if dex_type in ["curve", "balancer", "dodo"]:
        print(f"   ⏭️ Skipping - requires special handling")
        return dex_pools
    
    for token0, token1 in pairs:
        pair_name = f"{token0}/{token1}"
        if token0 not in TOKENS or token1 not in TOKENS:
            continue
        
        if not should_check_pair(failed_pairs, dex_name, pair_name):
            stats["cache_skipped"] += 1
            continue
        
        print(f"  {pair_name}...", end=" ")
        stats["checked"] += 1
        
        if dex_type == "v2":
            pool = discover_v2_pool(dex_config["factory"], token0, token1)
            if pool:
                dex_pools[pair_name] = {"pool": pool, "token0": get_token_address(token0), "token1": get_token_address(token1), "type": "v2"}
                print(f"✅ {pool[:10]}...")
                stats["found"] += 1
            else:
                print("❌")
                mark_pair_as_failed(failed_pairs, dex_name, pair_name)
        
        elif dex_type == "v3":
            fee_tiers = dex_config.get("fee_tiers", [500, 3000, 10000])
            pair_pools = {}
            for fee in fee_tiers:
                pool = discover_v3_pool(dex_config["factory"], token0, token1, fee)
                if pool:
                    pair_pools[str(fee)] = {"pool": pool, "token0": get_token_address(token0), "token1": get_token_address(token1), "fee": fee, "type": "v3"}
            if pair_pools:
                dex_pools[pair_name] = pair_pools
                print(f"✅ {len(pair_pools)} pools")
                stats["found"] += len(pair_pools)
            else:
                print("❌")
                mark_pair_as_failed(failed_pairs, dex_name, pair_name)
        
        elif dex_type == "v3_algebra":
            pool = discover_algebra_pool(dex_config["factory"], token0, token1)
            if pool:
                dex_pools[pair_name] = {"pool": pool, "token0": get_token_address(token0), "token1": get_token_address(token1), "type": "v3_algebra"}
                print(f"✅ {pool[:10]}...")
                stats["found"] += 1
            else:
                print("❌")
                mark_pair_as_failed(failed_pairs, dex_name, pair_name)
    
    return dex_pools


def discover_all_pools():
    registry = {}
    stats = {"checked": 0, "found": 0, "cache_skipped": 0}
    
    print("=" * 80)
    print("DYNAMIC POOL DISCOVERY (WITH CACHE)")
    print("=" * 80)
    
    failed_pairs = load_failed_pairs()
    print(f"💾 Cache: {sum(len(p) for p in failed_pairs.values())} known failed pairs")
    
    token_symbols = get_all_token_symbols()
    pairs = generate_trading_pairs(token_symbols)
    print(f"🔗 {len(pairs)} pairs to check across DEXes\n")
    
    discoverable_dexes = {n: c for n, c in DEXES.items() if c.get("type") not in ["curve", "balancer", "dodo"]}
    
    for dex_name, dex_config in discoverable_dexes.items():
        registry[dex_name] = discover_pools_for_dex(dex_name, dex_config, pairs, failed_pairs, stats)
    
    save_failed_pairs(failed_pairs)
    return registry, stats, failed_pairs


def save_registry(registry):
    with open("pool_registry.json", 'w') as f:
        json.dump(registry, f, indent=2)


def print_summary(registry, stats, failed_pairs):
    print("\n" + "=" * 80)
    print("DISCOVERY SUMMARY")
    print("=" * 80)
    print(f"📊 Pairs checked:        {stats['checked']:,}")
    print(f"   Pools found:          {stats['found']:,}")
    print(f"   Cache skipped:        {stats['cache_skipped']:,}")
    print(f"   Cache efficiency:     {(stats['cache_skipped'] / max(stats['checked'] + stats['cache_skipped'], 1)) * 100:.1f}%")
    
    print(f"\n🦄 Pools per DEX:")
    total = 0
    for dex, pairs in registry.items():
        count = sum(1 if "pool" in p else len(p) for p in pairs.values())
        if count > 0:
            print(f"   {dex:20s}: {count:3d} pools")
            total += count
    print(f"   {'─' * 40}\n   {'TOTAL':20s}: {total:3d} pools")
    
    print(f"\n💾 Failed Pairs Cache:")
    for dex, pairs in sorted(failed_pairs.items()):
        if pairs:
            print(f"   {dex:20s}: {len(pairs)} failed pairs")
    
    print("\n✅ Files created:")
    print("   • pool_registry.json (valid pools)")
    print("   • failed_pairs.json (cache)")
    print(f"\n💡 Next run will skip {sum(len(p) for p in failed_pairs.values())} cached failures for 30 days")
    print("=" * 80)


if __name__ == "__main__":
    if not os.getenv('ALCHEMY_API_KEY'):
        print("❌ ERROR: ALCHEMY_API_KEY not found in .env")
        sys.exit(1)
    
    registry, stats, failed_pairs = discover_all_pools()
    save_registry(registry)
    print_summary(registry, stats, failed_pairs)