import { UniswapV2Dex } from './uniswapV2';
import { DexInfo } from '../types';
import { IDex } from './interface';

/**
 * Factory to create DEX instances
 */
export class DexFactory {
  static createDex(dexInfo: DexInfo): IDex {
    // For V2-style DEXs (Uniswap V2, SushiSwap, etc.)
    return new UniswapV2Dex(dexInfo);
  }

  static createAllDexes(dexInfos: Record<string, DexInfo>): IDex[] {
    return Object.values(dexInfos).map(info => this.createDex(info));
  }
}
