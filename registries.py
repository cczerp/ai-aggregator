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
    },
    # NEW TOKENS - Expanded coverage
    "GRT": {
        "address": "0x5fe2B58c013d7601147DcdD68C143A77499f5531",
        "decimals": 18,
        "symbol": "GRT",
        "name": "The Graph"
    },
    "BAL": {
        "address": "0x9a71012B13CA4d3D0Cdc72A177DF3ef03b0E76A3",
        "decimals": 18,
        "symbol": "BAL",
        "name": "Balancer"
    },
    "GHST": {
        "address": "0x385Eeac5cB85A38A9a07A70c73e0a3271CfB54A7",
        "decimals": 18,
        "symbol": "GHST",
        "name": "Aavegotchi"
    },
    "SAND": {
        "address": "0xBbba073C31bF03b8ACf7c28EF0738DeCF3695683",
        "decimals": 18,
        "symbol": "SAND",
        "name": "The Sandbox"
    },
    "MANA": {
        "address": "0xA1c57f48F0Deb89f569dFbE6E2B7f46D33606fD4",
        "decimals": 18,
        "symbol": "MANA",
        "name": "Decentraland"
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
    },
    # NEW DEXES - Expanded coverage
    "ApeSwap": {  # ApeSwap V2
        "router": "0xC0788A3aD43d79aa53B09c2EaCc313A787d1d607",
        "factory": "0xCf083Be4164828f00cAE704EC15a36D711491284",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.002  # 0.2%
    },
    "Dfyn": {  # Dfyn V2
        "router": "0xA102072A4C07F06EC3B4900FDC4C7B80b6c57429",
        "factory": "0xE7Fb3e833eFE5F9c441105EB65Ef8b261266423B",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.003
    },
    "Polycat": {  # Polycat V2
        "router": "0x94930a328162957FF1dd48900aF67B5439336cBD",
        "factory": "0x477Ce834Ae6b7aB003cCe4BC4d8697763FF456FA",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.002
    },
    "JetSwap": {  # JetSwap V2
        "router": "0x5C6EC38fb0e2609672BDf628B1fD605A523E5923",
        "factory": "0x668ad0ed2622C62E24f0d5ab6B6Ac1b9D2cD4AC7",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.003
    },
    "WaultSwap": {  # WaultSwap V2
        "router": "0x3a1D87f206D12415f5b0A33E786967680AAb4f6d",
        "factory": "0xa98ea6356A316b44Bf710D5f9b6b4eA0081409Ef",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.002
    },
    "Kyber_DMM": {  # Kyber Dynamic Market Maker
        "router": "0x546C79662E028B661dFB4767664d0273184E4dD1",
        "factory": "0x5F1fe642060B5B9658C15721Ea22E982643c095c",
        "type": "kyber_dmm",
        "fee": 0.0008  # Dynamic, 0.08% typical
    },
    "Meshswap": {  # Meshswap V2
        "router": "0x10f4A785F458Bc144e3706575924889954946639",
        "factory": "0x9F3044f7F9FC8bC9eD615d54845b4577B833282d",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.003
    },
    "Polydex": {  # Polydex V2
        "router": "0xC6a28f9a04FbE65390e614714F7a8Cd3e5bC6655",
        "factory": "0x26cc089b5859c3C6170b84e9E49194E2401e62dE",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.003
    },
    "DinoSwap": {  # DinoSwap V2 (Fossil Farms)
        "router": "0x6AC823102CB347e4f2858B4c5b1b7462da1596eD",
        "factory": "0x624Ccf581371F8A4493e6AbDE46412002555A1b6",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.0025  # 0.25%
    },
    "MM_Finance": {  # MM Finance (Cronos origin, also on Polygon)
        "router": "0x145677FC4d9b8F19B5D56d1820c48e0443049a30",
        "factory": "0xd590cC180601AEcD6eeADD9B7f2B7611519544f4",
        "version": 0,  # V2
        "type": "v2",
        "fee": 0.0017  # 0.17%
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