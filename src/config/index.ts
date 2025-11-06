import { Token, DexInfo, FlashloanProvider } from '../types';

// Common tokens on Ethereum mainnet with their decimal precision
export const TOKENS: Record<string, Token> = {
  WETH: {
    address: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
    symbol: 'WETH',
    decimals: 18,
    name: 'Wrapped Ether'
  },
  USDC: {
    address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
    symbol: 'USDC',
    decimals: 6,
    name: 'USD Coin'
  },
  USDT: {
    address: '0xdAC17F958D2ee523a2206206994597C13D831ec7',
    symbol: 'USDT',
    decimals: 6,
    name: 'Tether USD'
  },
  DAI: {
    address: '0x6B175474E89094C44Da98b954EedeAC495271d0F',
    symbol: 'DAI',
    decimals: 18,
    name: 'Dai Stablecoin'
  },
  WBTC: {
    address: '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',
    symbol: 'WBTC',
    decimals: 8,
    name: 'Wrapped BTC'
  },
  UNI: {
    address: '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
    symbol: 'UNI',
    decimals: 18,
    name: 'Uniswap'
  },
  LINK: {
    address: '0x514910771AF9Ca656af840dff83E8264EcF986CA',
    symbol: 'LINK',
    decimals: 18,
    name: 'ChainLink Token'
  },
  AAVE: {
    address: '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9',
    symbol: 'AAVE',
    decimals: 18,
    name: 'Aave Token'
  },
  MATIC: {
    address: '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0',
    symbol: 'MATIC',
    decimals: 18,
    name: 'Matic Token'
  },
  CRV: {
    address: '0xD533a949740bb3306d119CC777fa900bA034cd52',
    symbol: 'CRV',
    decimals: 18,
    name: 'Curve DAO Token'
  }
};

// DEX configurations
export const DEXS: Record<string, DexInfo> = {
  UNISWAP_V2: {
    name: 'Uniswap V2',
    routerAddress: '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
    factoryAddress: '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
    fee: 0.3
  },
  SUSHISWAP: {
    name: 'SushiSwap',
    routerAddress: '0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F',
    factoryAddress: '0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac',
    fee: 0.3
  },
  UNISWAP_V3: {
    name: 'Uniswap V3',
    routerAddress: '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    factoryAddress: '0x1F98431c8aD98523631AE4a59f267346ea31F984',
    fee: 0.3 // V3 has multiple fee tiers, using 0.3% as default
  },
  CURVE: {
    name: 'Curve',
    routerAddress: '0x8e764bE4288B842791989DB5b8ec067279829809',
    factoryAddress: '0xB9fC157394Af804a3578134A6585C0dc9cc990d4',
    fee: 0.04 // Curve typically has lower fees
  }
};

// Flashloan providers
export const FLASHLOAN_PROVIDERS: Record<string, FlashloanProvider> = {
  AAVE: {
    name: 'aave',
    address: '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2', // Aave V3 Pool
    feePercentage: 0.09 // 0.09%
  },
  BALANCER: {
    name: 'balancer',
    address: '0xBA12222222228d8Ba445958a75a0704d566BF2C8', // Balancer Vault
    feePercentage: 0.0 // Balancer has no flashloan fee
  }
};

// Generate token pairs for scanning
export function generateTokenPairs(): Array<{ tokenA: Token; tokenB: Token }> {
  const pairs: Array<{ tokenA: Token; tokenB: Token }> = [];
  const tokenList = Object.values(TOKENS);
  
  // Generate all unique pairs
  for (let i = 0; i < tokenList.length; i++) {
    for (let j = i + 1; j < tokenList.length; j++) {
      pairs.push({
        tokenA: tokenList[i],
        tokenB: tokenList[j]
      });
    }
  }
  
  return pairs;
}

// Configuration settings
export const CONFIG = {
  RPC_URL: process.env.RPC_URL || 'https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY',
  ALCHEMY_BUNDLER_URL: process.env.ALCHEMY_BUNDLER_URL || '',
  PRIVATE_KEY: process.env.PRIVATE_KEY || '',
  MIN_PROFIT_THRESHOLD_USD: 50, // Minimum profit in USD
  GAS_PRICE_MULTIPLIER: 1.1, // Multiply gas price by this for faster execution
  MAX_SLIPPAGE: 0.5, // Maximum slippage percentage
  SCAN_INTERVAL_MS: 5000, // How often to scan for opportunities
};
