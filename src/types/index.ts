import BigNumber from 'bignumber.js';

export interface Token {
  address: string;
  symbol: string;
  decimals: number;
  name: string;
}

export interface TokenPair {
  tokenA: Token;
  tokenB: Token;
}

export interface DexInfo {
  name: string;
  routerAddress: string;
  factoryAddress: string;
  fee: number; // Fee percentage (e.g., 0.3 for 0.3%)
}

export interface Price {
  tokenIn: Token;
  tokenOut: Token;
  price: BigNumber; // How much tokenOut per 1 tokenIn
  amountIn: BigNumber; // Raw amount
  amountOut: BigNumber; // Raw amount
  dex: string;
  timestamp: number;
}

export interface ArbitrageOpportunity {
  tokenA: Token;
  tokenB: Token;
  buyDex: string;
  sellDex: string;
  buyPrice: BigNumber;
  sellPrice: BigNumber;
  amountIn: BigNumber; // Raw amount
  expectedProfit: BigNumber; // Raw amount in tokenA
  profitPercentage: BigNumber;
  route: string[]; // DEX names in order
}

export interface FlashloanProvider {
  name: 'aave' | 'balancer';
  address: string;
  feePercentage: number;
}

export interface FlashloanParams {
  token: Token;
  amount: BigNumber; // Raw amount
  provider: FlashloanProvider;
  estimatedCost: BigNumber; // Raw amount
}

export interface ExecutionResult {
  success: boolean;
  txHash?: string;
  profit?: BigNumber; // Raw amount
  gasUsed?: BigNumber;
  error?: string;
}
