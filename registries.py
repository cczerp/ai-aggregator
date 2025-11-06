# registries.py
"""
Centralized registry for DEXs, tokens, and aggregators with token decimals
"""

# Token Registry with decimals - POLYGON MAINNET (matches pool_registry.json)
TOKENS = {
    "WPOL": {
        "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "decimals": 18,
        "symbol": "WPOL",
        "name": "Wrapped POL"
    },
    "WMATIC": {  # Alias for WPOL (backward compatibility)
        "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
        "decimals": 18,
        "symbol": "WMATIC",
        "name": "Wrapped Matic"
    },
    "USDT": {
        "address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "decimals": 6,
        "symbol": "USDT",
        "name": "Tether USD"
    },
    "USDC": {
        "address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "decimals": 6,
        "symbol": "USDC",
        "name": "USD Coin"
    },
    "WETH": {
        "address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
        "decimals": 18,
        "symbol": "WETH",
        "name": "Wrapped Ether"
    },
    "DAI": {
        "address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "decimals": 18,
        "symbol": "DAI",
        "name": "Dai Stablecoin"
    },
    "UNI": {
        "address": "0xb33EaAd8d922B1083446DC23f610c2567fB5180f",
        "decimals": 18,
        "symbol": "UNI",
        "name": "Uniswap"
    },
    "AAVE": {
        "address": "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
        "decimals": 18,
        "symbol": "AAVE",
        "name": "Aave Token"
    },
    "LINK": {
        "address": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39",
        "decimals": 18,
        "symbol": "LINK",
        "name": "ChainLink Token"
    },
    "QUICK": {
        "address": "0xB5C064F955D8e7F38fE0460C556a72987494eE17",
        "decimals": 18,
        "symbol": "QUICK",
        "name": "QuickSwap"
    },
    "SUSHI": {
        "address": "0x0b3F868E0BE5597D5DB7fEB59E1CADBb0fdDa50a",
        "decimals": 18,
        "symbol": "SUSHI",
        "name": "SushiToken"
    },
    "WBTC": {
        "address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
        "decimals": 8,
        "symbol": "WBTC",
        "name": "Wrapped BTC"
    },
    "CRV": {
        "address": "0x172370d5Cd63279eFa6d502DAB29171933a610AF",
        "decimals": 18,
        "symbol": "CRV",
        "name": "Curve DAO Token"
    },
    "SNX": {
        "address": "0x50B728D8D964fd00C2d0AAD81718b71311feF68a",
        "decimals": 18,
        "symbol": "SNX",
        "name": "Synthetix Network Token"
    },
    "YFI": {
        "address": "0xDA537104D6A5edd53c6fBba9A898708E465260b6",
        "decimals": 18,
        "symbol": "YFI",
        "name": "yearn.finance"
    }
}

# DEX Registry - POLYGON MAINNET
DEXES = {
    "QuickSwap_V2": {
        "router": "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        "factory": "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.003
    },
    "Uniswap_V3": {
        "router": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "quoter": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
        "version": 1,  # V3
        "type": "v3",
        "fee_tiers": [500, 3000, 10000]
    },
    "SushiSwap": {
        "router": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        "factory": "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.003
    },
    "Algebra": {  # QuickSwap V3
        "router": "0xf5b509bB0909a69B1c207E495f687a596C168E12",
        "factory": "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28",
        "version": 1,  # V3-style
        "type": "v3_algebra",
        "fee_tiers": [100, 500, 3000, 10000]
    },
    "SushiSwap_V3": {
        "router": "0x917933899c6a5F8E37F31E19f92CdBFF7e8FF0e2",  # SushiSwap V3
        "factory": "0x917933899c6a5F8E37F31E19f92CdBFF7e8FF0e2",
        "version": 1,  # V3
        "type": "v3",
        "fee_tiers": [500, 3000, 10000]
    },
    "Retro": {  # Solidly Fork
        "router": "0x8e595470Ed749b85C6F7669de83EAe304C2ec68F",
        "factory": "0x91B5F3b8d815d98C45f9fe35B93E50A66de9D80D",
        "type": "v2",
        "fee": 0.002  # 0.2%
    },
    "Dystopia": {  # Solidly Fork
        "router": "0xbE75Dd16D029c6B32B7aD57A0FD9C1c20Dd2862e",
        "factory": "0x1d21Db6cde1b18c7E47B0F7F42f4b3F68b9beeC9",
        "type": "v2",
        "fee": 0.002
    },
    "Curve_aTriCrypto": {
        "pool": "0x92215849c439E1f8612b6646060B4E3E5ef822cC",
        "type": "curve",
        "tokens": ["USDC", "USDT", "DAI"],  # 3-token pool
        "fee": 0.0004  # 0.04%
    },
    "Balancer_V2": {  # Balancer V2
        "vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
        "type": "balancer",
        "fee": 0.003
    },
    "DODO_V2": {  # DODO V2
        "router": "0xa222e6a71D1A1Dd5F279805fbe38d5329C1d0e70",
        "type": "dodo",
        "version": 2,
        "fee": 0.003
    }
}


# DEX Aggregators - POLYGON
AGGREGATORS = {
    "1inch": {
        "router": "0x1111111254EEB25477B68fb85Ed929f73A960582",
        "api_url": "https://api.1inch.dev/swap/v6.0/137"  # 137 = Polygon chain ID
    },
    "Paraswap": {
        "router": "0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57",
        "api_url": "https://apiv5.paraswap.io"
    }
}

# Flash Loan Providers - POLYGON
FLASHLOAN_PROVIDERS = {
    "AAVE_V3": {
        "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "fee": 0.0009  # 0.09%
    },
    "Balancer": {
        "vault": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
        "fee": 0.0  # 0%
    }
}

def get_token_address(symbol: str) -> str:
    """Get token address by symbol"""
    return TOKENS.get(symbol, {}).get("address", "")

def get_token_decimals(symbol: str) -> int:
    """Get token decimals by symbol"""
    return TOKENS.get(symbol, {}).get("decimals", 18)

def get_token_by_address(address: str) -> dict:
    """Get token info by address"""
    address = address.lower()
    for symbol, info in TOKENS.items():
        if info["address"].lower() == address:
            return {**info, "symbol": symbol}
    return {}

def get_dex_info(dex_name: str) -> dict:
    """Get DEX information"""
    return DEXES.get(dex_name, {})

def get_all_token_symbols() -> list:
    """Get list of all token symbols"""
    # Exclude WMATIC alias
    return [symbol for symbol in TOKENS.keys() if symbol != "WMATIC"]

def get_all_dex_names() -> list:
    """Get list of all DEX names"""
    return list(DEXES.keys())