"""
ABI Definitions for DEX Interactions
Essential contract interfaces for the arbitrage scanner
"""

# Uniswap V2 Pair ABI (QuickSwap, SushiSwap use this too)
UNISWAP_V2_PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"name": "_reserve0", "type": "uint112"},
            {"name": "_reserve1", "type": "uint112"},
            {"name": "_blockTimestampLast", "type": "uint32"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    }
]

# Uniswap V3 Pool ABI
UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"name": "sqrtPriceX96", "type": "uint160"},
            {"name": "tick", "type": "int24"},
            {"name": "observationIndex", "type": "uint16"},
            {"name": "observationCardinality", "type": "uint16"},
            {"name": "observationCardinalityNext", "type": "uint16"},
            {"name": "feeProtocol", "type": "uint8"},
            {"name": "unlocked", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "fee",
        "outputs": [{"name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Curve Pool ABI (simplified)
CURVE_POOL_ABI = [
    {
        "name": "coins",
        "outputs": [{"type": "address", "name": ""}],
        "inputs": [{"type": "uint256", "name": "arg0"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_dy",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [
            {"type": "int128", "name": "i"},
            {"type": "int128", "name": "j"},
            {"type": "uint256", "name": "dx"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "name": "get_dy_underlying",
        "outputs": [{"type": "uint256", "name": ""}],
        "inputs": [
            {"type": "int128", "name": "i"},
            {"type": "int128", "name": "j"},
            {"type": "uint256", "name": "dx"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Uniswap V2 Router ABI (for actual quotes)
UNISWAP_V2_ROUTER_ABI = [
    {
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [
            {"name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# Uniswap V3 Quoter V2 ABI
QUOTER_V2_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ERC20 Token ABI (minimal)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

# Flashloan Trading Bot Contract ABI
# Contract: remix bot/flashloanbot.sol
FLASHLOAN_CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "_aave", "type": "address"},
            {"internalType": "address", "name": "_balancer", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "address", "name": "tokenIn", "type": "address"},
            {"indexed": False, "internalType": "address", "name": "tokenOut", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "profit", "type": "uint256"}
        ],
        "name": "TradeExecuted",
        "type": "event"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "caller", "type": "address"},
            {"internalType": "bool", "name": "status", "type": "bool"}
        ],
        "name": "authorizeCaller",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "address", "name": "dex1", "type": "address"},
            {"internalType": "address", "name": "dex2", "type": "address"},
            {"internalType": "uint8", "name": "dex1Version", "type": "uint8"},
            {"internalType": "uint8", "name": "dex2Version", "type": "uint8"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "minProfitAmount", "type": "uint256"},
            {"internalType": "bytes", "name": "dex1Data", "type": "bytes"},
            {"internalType": "bytes", "name": "dex2Data", "type": "bytes"}
        ],
        "name": "executeFlashloan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "tokenIn", "type": "address"},
            {"internalType": "address", "name": "tokenOut", "type": "address"},
            {"internalType": "address", "name": "dex1", "type": "address"},
            {"internalType": "address", "name": "dex2", "type": "address"},
            {"internalType": "uint8", "name": "dex1Version", "type": "uint8"},
            {"internalType": "uint8", "name": "dex2Version", "type": "uint8"},
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "minProfitAmount", "type": "uint256"},
            {"internalType": "bytes", "name": "dex1Data", "type": "bytes"},
            {"internalType": "bytes", "name": "dex2Data", "type": "bytes"}
        ],
        "name": "executeBalancerFlashloan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "token", "type": "address"}],
        "name": "withdrawToken",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "withdrawETH",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "newOwner", "type": "address"}],
        "name": "transferOwnership",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]