"""
Config Diagnostic Tool
Checks your config.json and tells you what's wrong
"""

import json
from colorama import Fore, Style, init

init(autoreset=True)


def check_config():
    """Check config.json for issues"""
    
    print(f"\n{Fore.CYAN}{'='*70}")
    print("CONFIG.JSON DIAGNOSTIC")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"{Fore.RED}❌ config.json NOT FOUND!{Style.RESET_ALL}")
        return
    except json.JSONDecodeError as e:
        print(f"{Fore.RED}❌ config.json has INVALID JSON: {e}{Style.RESET_ALL}")
        return
    
    print(f"{Fore.GREEN}✓ config.json found and valid{Style.RESET_ALL}\n")
    
    # Check RPC
    rpc = config.get('rpc_url', 'NOT SET')
    print(f"RPC URL: {rpc}")
    
    # Check tokens
    tokens = config.get('tokens', {})
    print(f"\n{Fore.CYAN}TOKENS:{Style.RESET_ALL}")
    print(f"  Count: {len(tokens)}")
    
    if len(tokens) < 20:
        print(f"  {Fore.YELLOW}⚠️  WARNING: You have {len(tokens)} tokens but need 20{Style.RESET_ALL}")
    else:
        print(f"  {Fore.GREEN}✓ Enough tokens{Style.RESET_ALL}")
    
    for addr, info in list(tokens.items())[:5]:
        symbol = info.get('symbol', 'UNKNOWN')
        decimals = info.get('decimals', '?')
        print(f"  • {symbol} ({decimals} decimals)")
    
    if len(tokens) > 5:
        print(f"  ... and {len(tokens) - 5} more")
    
    # Check DEXes and pools
    dexes = config.get('dexes', {})
    print(f"\n{Fore.CYAN}DEXES AND POOLS:{Style.RESET_ALL}")
    
    total_pools = 0
    token_pairs = set()
    
    for dex_name, dex_config in dexes.items():
        pools = dex_config.get('pools', [])
        pool_count = len(pools)
        total_pools += pool_count
        dex_type = dex_config.get('type', 'v2')
        
        print(f"\n  {dex_name.upper()} ({dex_type}):")
        print(f"    Pools: {pool_count}")
        
        # Track token pairs
        for pool in pools:
            t0 = pool.get('token0', '').lower()
            t1 = pool.get('token1', '').lower()
            if t0 and t1:
                pair = tuple(sorted([t0, t1]))
                token_pairs.add(pair)
        
        # Show first 3 pools
        for pool in pools[:3]:
            addr = pool.get('address', 'NO ADDRESS')[:10]
            t0 = pool.get('token0', '')
            t1 = pool.get('token1', '')
            
            # Get symbols
            t0_symbol = tokens.get(t0, {}).get('symbol', 'UNKNOWN')
            t1_symbol = tokens.get(t1, {}).get('symbol', 'UNKNOWN')
            
            print(f"    • {addr}... {t0_symbol}/{t1_symbol}")
        
        if pool_count > 3:
            print(f"    ... and {pool_count - 3} more")
    
    # Summary
    print(f"\n{Fore.CYAN}{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    print(f"Total pools: {total_pools}")
    print(f"Unique token pairs: {len(token_pairs)}")
    
    # Assessment
    print(f"\n{Fore.CYAN}ASSESSMENT:{Style.RESET_ALL}\n")
    
    if total_pools < 20:
        print(f"{Fore.RED}❌ CRITICAL: Only {total_pools} pools!{Style.RESET_ALL}")
        print(f"   You need at least 60 pools for 20 token pairs")
        print(f"   Add {60 - total_pools} more pools to config.json")
    elif total_pools < 60:
        print(f"{Fore.YELLOW}⚠️  WARNING: Only {total_pools} pools{Style.RESET_ALL}")
        print(f"   For 20 token pairs, you should have 60+ pools")
        print(f"   Add {60 - total_pools} more pools for better coverage")
    else:
        print(f"{Fore.GREEN}✓ Good pool coverage: {total_pools} pools{Style.RESET_ALL}")
    
    if len(token_pairs) < 20:
        print(f"\n{Fore.YELLOW}⚠️  Only {len(token_pairs)} unique token pairs{Style.RESET_ALL}")
        print(f"   You wanted to trade 20 pairs")
        print(f"   Add pools for {20 - len(token_pairs)} more pairs")
    else:
        print(f"\n{Fore.GREEN}✓ Good pair coverage: {len(token_pairs)} pairs{Style.RESET_ALL}")
    
    # Check scan amount
    scan_amount = config.get('scan_amount_usd', 'NOT SET')
    print(f"\n{Fore.CYAN}SCAN AMOUNT:{Style.RESET_ALL}")
    print(f"  Current: ${scan_amount}")
    
    if scan_amount == 100:
        print(f"  {Fore.YELLOW}⚠️  Only testing $100{Style.RESET_ALL}")
        print(f"  You wanted to test $1k, $10k, $100k")
        print(f"  Use multi_amount_scanner.py to test all amounts")
    
    # Recommendations
    print(f"\n{Fore.CYAN}{'='*70}")
    print("RECOMMENDATIONS")
    print(f"{'='*70}{Style.RESET_ALL}\n")
    
    if total_pools < 60:
        print(f"1. {Fore.YELLOW}Add more pools to config.json{Style.RESET_ALL}")
        print(f"   - Find pools on Uniswap, QuickSwap, SushiSwap info pages")
        print(f"   - Need at least 3 pools per token pair")
        print(f"   - Target: 60-100 total pools")
    
    if scan_amount == 100:
        print(f"\n2. {Fore.YELLOW}Test multiple amounts{Style.RESET_ALL}")
        print(f"   - Replace arb_scanner.py with multi_amount_scanner.py")
        print(f"   - Will test $1k, $10k, $100k automatically")
    
    print(f"\n{Fore.GREEN}Run 'python ai_bridge.py' after fixes{Style.RESET_ALL}\n")


if __name__ == "__main__":
    check_config()