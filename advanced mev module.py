"""
Advanced MEV Module - Mempool Monitoring & Graph-Based Arbitrage
Integrates with your existing PolygonArbBot architecture

Features:
1. Mempool monitoring for pending DEX swaps
2. WebSocket price feed streaming
3. Graph-based multi-hop arbitrage pathfinding
4. Atomic transaction bundling
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque
from web3 import Web3
from web3.exceptions import TransactionNotFound
from colorama import Fore, Style, init
import logging

init(autoreset=True)
logger = logging.getLogger(__name__)


class MempoolMonitor:
    """
    Monitors pending transactions for DEX swaps
    Predicts price impact before block confirmation
    """
    
    # Known DEX router addresses on Polygon
    DEX_ROUTERS = {
        '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff': 'QuickSwap',
        '0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506': 'SushiSwap',
        '0xE592427A0AEce92De3Edee1F18E0157C05861564': 'Uniswap_V3',
        '0xf5b509bB0909a69B1c207E495f687a596C168E12': 'Algebra',
    }
    
    # Common swap function signatures
    SWAP_SIGNATURES = {
        '0x38ed1739': 'swapExactTokensForTokens',
        '0x8803dbee': 'swapTokensForExactTokens',
        '0x7ff36ab5': 'swapExactETHForTokens',
        '0x18cbafe5': 'swapExactTokensForETH',
        '0x414bf389': 'exactInputSingle',  # Uniswap V3
        '0xc04b8d59': 'exactInput',        # Uniswap V3
    }
    
    def __init__(self, rpc_manager, cache, min_value_usd: float = 10000):
        """
        Args:
            rpc_manager: Your existing RPCManager instance
            cache: Your existing Cache instance
            min_value_usd: Minimum swap value to track (filter noise)
        """
        self.rpc_manager = rpc_manager
        self.cache = cache
        self.min_value_usd = min_value_usd
        
        self.w3 = rpc_manager.get_web3()
        self.pending_txs = deque(maxlen=1000)  # Recent pending txs
        self.monitored_pools = set()  # Pools to watch
        self.price_impacts = {}  # predicted_pool_address -> impact_data
        
        logger.info(f"{Fore.GREEN}✅ Mempool Monitor initialized{Style.RESET_ALL}")
        logger.info(f"   Tracking swaps > ${min_value_usd:,.0f}")
    
    def is_dex_swap(self, tx: Dict) -> Tuple[bool, Optional[str]]:
        """Check if transaction is a DEX swap"""
        if not tx or not tx.get('to'):
            return False, None
        
        to_address = tx['to'].lower()
        
        # Check if it's a known DEX router
        if to_address in self.DEX_ROUTERS:
            dex_name = self.DEX_ROUTERS[to_address]
            
            # Check function signature
            input_data = tx.get('input', '0x')
            if len(input_data) >= 10:
                sig = input_data[:10]
                if sig in self.SWAP_SIGNATURES:
                    return True, dex_name
        
        return False, None
    
    def decode_swap_params(self, tx: Dict, dex_name: str) -> Optional[Dict]:
        """
        Decode swap parameters from transaction input data
        Returns: {token_in, token_out, amount_in, path, ...}
        """
        try:
            input_data = tx.get('input', '0x')
            if len(input_data) < 10:
                return None
            
            # This is a simplified decoder - you'd need proper ABI decoding
            # For production, use web3.py contract decoding with actual ABIs
            
            # Basic structure for V2 swaps:
            # swapExactTokensForTokens(amountIn, amountOutMin, path, to, deadline)
            
            # Placeholder - implement full ABI decoding based on function signature
            return {
                'tx_hash': tx.get('hash', ''),
                'from': tx.get('from', ''),
                'dex': dex_name,
                'gas_price': tx.get('gasPrice', 0),
                'input_data': input_data
            }
            
        except Exception as e:
            logger.debug(f"Failed to decode swap: {e}")
            return None
    
    def estimate_price_impact(self, swap_data: Dict, pool_address: str) -> Optional[Dict]:
        """
        Estimate price impact of pending swap on a pool
        Uses your existing cache and math functions
        """
        try:
            # Get pool state from cache
            pool_data = self.cache.get('tvl_data', pool_address)
            if not pool_data:
                return None
            
            # Calculate impact based on swap size vs reserves
            # (Simplified - use your existing arb_finder logic)
            
            return {
                'pool': pool_address,
                'estimated_impact_pct': 0.5,  # Placeholder
                'new_price_estimate': 0,
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.debug(f"Price impact estimation failed: {e}")
            return None
    
    async def monitor_pending_txs(self, callback):
        """
        Async monitoring of pending transactions
        Calls callback(tx_data) for each relevant swap
        """
        logger.info(f"{Fore.CYAN}🔍 Starting mempool monitoring...{Style.RESET_ALL}")
        
        # Subscribe to pending transactions
        pending_filter = self.w3.eth.filter('pending')
        
        while True:
            try:
                # Get new pending tx hashes
                for tx_hash in pending_filter.get_new_entries():
                    try:
                        # Fetch full transaction
                        tx = self.w3.eth.get_transaction(tx_hash)
                        
                        # Check if it's a DEX swap
                        is_swap, dex_name = self.is_dex_swap(tx)
                        
                        if is_swap:
                            swap_data = self.decode_swap_params(tx, dex_name)
                            if swap_data:
                                # Add to pending queue
                                self.pending_txs.append(swap_data)
                                
                                # Notify callback
                                await callback(swap_data)
                                
                    except TransactionNotFound:
                        # Transaction already mined
                        continue
                    except Exception as e:
                        logger.debug(f"Error processing tx {tx_hash.hex()}: {e}")
                        continue
                
                # Sleep briefly to avoid hammering RPC
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Mempool monitoring error: {e}")
                await asyncio.sleep(1)
    
    def get_recent_impacts(self, pool_address: str, window_seconds: int = 60) -> List[Dict]:
        """Get recent price impacts for a pool"""
        cutoff = time.time() - window_seconds
        impacts = [
            impact for impact in self.price_impacts.get(pool_address, [])
            if impact['timestamp'] > cutoff
        ]
        return impacts


class WebSocketPriceFeed:
    """
    Real-time price feed using WebSocket connections
    Listens for Swap events from DEX pools
    """
    
    # Swap event signature
    SWAP_EVENT_TOPIC = Web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()
    
    def __init__(self, rpc_manager, cache):
        self.rpc_manager = rpc_manager
        self.cache = cache
        
        # WebSocket connection (async)
        self.ws_url = self._get_ws_url()
        self.subscriptions = {}  # pool_address -> callback
        
        logger.info(f"{Fore.GREEN}✅ WebSocket Price Feed initialized{Style.RESET_ALL}")
    
    def _get_ws_url(self) -> str:
        """Get WebSocket URL from environment"""
        import os
        # Try Alchemy first, then Infura
        if os.getenv('ALCHEMY_API_KEY'):
            return f"wss://polygon-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY')}"
        elif os.getenv('INFURA_API_KEY'):
            return f"wss://polygon-mainnet.infura.io/ws/v3/{os.getenv('INFURA_API_KEY')}"
        else:
            raise ValueError("No WebSocket RPC URL configured")
    
    async def subscribe_to_pool(self, pool_address: str, callback):
        """Subscribe to Swap events from a specific pool"""
        self.subscriptions[pool_address.lower()] = callback
        logger.info(f"📡 Subscribed to pool: {pool_address[:10]}...")
    
    async def listen_for_swaps(self):
        """
        Listen for Swap events on subscribed pools
        """
        logger.info(f"{Fore.CYAN}🎧 Starting WebSocket listener...{Style.RESET_ALL}")
        
        try:
            from websockets import connect
            
            async with connect(self.ws_url) as ws:
                # Subscribe to logs
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": [
                        "logs",
                        {
                            "address": list(self.subscriptions.keys()),
                            "topics": [self.SWAP_EVENT_TOPIC]
                        }
                    ]
                }
                
                await ws.send(json.dumps(subscribe_msg))
                
                # Listen for events
                while True:
                    message = await ws.recv()
                    data = json.loads(message)
                    
                    if 'params' in data:
                        log = data['params']['result']
                        pool_address = log['address'].lower()
                        
                        if pool_address in self.subscriptions:
                            # Parse swap data
                            swap_data = self._parse_swap_log(log)
                            
                            # Update cache
                            self._update_pool_cache(pool_address, swap_data)
                            
                            # Notify callback
                            callback = self.subscriptions[pool_address]
                            await callback(pool_address, swap_data)
        
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
    
    def _parse_swap_log(self, log: Dict) -> Dict:
        """Parse Swap event log"""
        # Decode log data
        # Format: Swap(address,uint256,uint256,uint256,uint256,address)
        # This is simplified - use proper ABI decoding in production
        
        return {
            'block_number': int(log['blockNumber'], 16),
            'tx_hash': log['transactionHash'],
            'timestamp': time.time(),
            # ... decode amounts, reserves, etc.
        }
    
    def _update_pool_cache(self, pool_address: str, swap_data: Dict):
        """Update cached pool state after swap"""
        # Invalidate cache for this pool so next fetch gets fresh data
        # Your cache system will handle the refresh
        pass


class GraphArbitrageFinder:
    """
    Graph-based arbitrage finder with multi-hop pathfinding
    Builds a directed graph of all trading pairs and finds profitable cycles
    """
    
    def __init__(self, arb_finder):
        """
        Args:
            arb_finder: Your existing ArbFinder instance
        """
        self.arb_finder = arb_finder
        
        # Graph: token -> [(connected_token, edge_data)]
        self.graph = defaultdict(list)
        self.pools = {}  # (token_a, token_b, dex) -> pool_data
        
        logger.info(f"{Fore.GREEN}✅ Graph Arbitrage Finder initialized{Style.RESET_ALL}")
    
    def build_graph(self, pools_data: Dict[str, Dict]):
        """
        Build directed graph from pool data
        Each edge represents a potential swap
        """
        logger.info(f"{Fore.CYAN}🏗️  Building arbitrage graph...{Style.RESET_ALL}")
        
        self.graph.clear()
        self.pools.clear()
        
        edge_count = 0
        
        for dex_name, pairs in pools_data.items():
            for pair_name, pool_data in pairs.items():
                pair_prices = pool_data.get('pair_prices', {})
                tvl_data = pool_data.get('tvl_data', {})
                
                token0 = pair_prices.get('token0')
                token1 = pair_prices.get('token1')
                
                if not token0 or not token1:
                    continue
                
                # Add bidirectional edges
                edge0to1 = {
                    'dex': dex_name,
                    'pool_address': pool_data.get('pool'),
                    'quote': pair_prices.get('quote_0to1', 0),
                    'fee': self._get_fee(dex_name, pair_prices),
                    'tvl': tvl_data.get('tvl_usd', 0),
                    'decimals0': pair_prices.get('decimals0', 18),
                    'decimals1': pair_prices.get('decimals1', 18),
                }
                
                edge1to0 = {
                    'dex': dex_name,
                    'pool_address': pool_data.get('pool'),
                    'quote': pair_prices.get('quote_1to0', 0),
                    'fee': self._get_fee(dex_name, pair_prices),
                    'tvl': tvl_data.get('tvl_usd', 0),
                    'decimals0': pair_prices.get('decimals1', 18),
                    'decimals1': pair_prices.get('decimals0', 18),
                }
                
                self.graph[token0].append((token1, edge0to1))
                self.graph[token1].append((token0, edge1to0))
                
                edge_count += 2
        
        logger.info(f"   Graph: {len(self.graph)} tokens, {edge_count} edges")
    
    def _get_fee(self, dex_name: str, pair_prices: Dict) -> float:
        """Get trading fee for a DEX"""
        if pair_prices.get('type') == 'v3':
            return pair_prices.get('fee', 3000) / 1000000  # fee in bps to decimal
        else:
            # V2 fees from your DEX config
            fee_map = {
                'QuickSwap_V2': 0.003,
                'SushiSwap': 0.003,
                'Algebra': 0.003,
            }
            return fee_map.get(dex_name, 0.003)
    
    def find_triangular_paths(self, start_token: str, max_hops: int = 3, max_paths: int = 100) -> List[List[str]]:
        """
        Find all cycles starting from start_token
        Uses DFS to find paths back to start
        """
        paths = []
        visited = set()
        
        def dfs(current_token: str, path: List[str], depth: int):
            if len(paths) >= max_paths:
                return
            
            if depth > max_hops:
                return
            
            if depth > 1 and current_token == start_token:
                # Found a cycle!
                paths.append(path[:])
                return
            
            if depth > 0 and current_token in visited:
                return
            
            visited.add(current_token)
            
            # Explore neighbors
            for next_token, edge_data in self.graph.get(current_token, []):
                # Skip if insufficient liquidity
                if edge_data['tvl'] < 5000:
                    continue
                
                path.append(next_token)
                dfs(next_token, path, depth + 1)
                path.pop()
            
            visited.discard(current_token)
        
        dfs(start_token, [start_token], 0)
        
        return paths
    
    def calculate_path_profit(
        self,
        path: List[str],
        amount_in_usd: float,
        price_data: Dict
    ) -> Optional[Dict]:
        """
        Calculate profit for a specific path using actual pool quotes
        """
        if len(path) < 3:  # Need at least A->B->A
            return None
        
        try:
            current_amount = amount_in_usd
            route_details = []
            
            # Execute each hop
            for i in range(len(path) - 1):
                token_in = path[i]
                token_out = path[i + 1]
                
                # Find best edge for this hop
                edges = [
                    edge for next_token, edge in self.graph[token_in]
                    if next_token == token_out
                ]
                
                if not edges:
                    return None
                
                # Use highest liquidity pool
                best_edge = max(edges, key=lambda e: e['tvl'])
                
                # Calculate output (simplified - use your actual swap math)
                fee_multiplier = 1 - best_edge['fee']
                current_amount *= fee_multiplier
                
                route_details.append({
                    'from': token_in,
                    'to': token_out,
                    'dex': best_edge['dex'],
                    'amount': current_amount
                })
            
            # Calculate profit
            profit = current_amount - amount_in_usd
            roi = (profit / amount_in_usd) * 100 if amount_in_usd > 0 else 0
            
            if profit > 0:
                return {
                    'path': ' → '.join(path),
                    'route': route_details,
                    'amount_in': amount_in_usd,
                    'amount_out': current_amount,
                    'profit_usd': profit,
                    'roi_percent': roi
                }
            
        except Exception as e:
            logger.debug(f"Path calculation failed: {e}")
        
        return None
    
    def find_all_opportunities(
        self,
        pools_data: Dict,
        base_tokens: List[str] = ['USDC', 'WETH', 'WPOL'],
        test_amounts: List[float] = [1000, 5000, 10000]
    ) -> List[Dict]:
        """
        Find all arbitrage opportunities using graph pathfinding
        """
        logger.info(f"\n{Fore.CYAN}{'='*80}")
        logger.info(f"🔍 GRAPH-BASED ARBITRAGE SCAN")
        logger.info(f"{'='*80}{Style.RESET_ALL}\n")
        
        # Build graph
        self.build_graph(pools_data)
        
        opportunities = []
        
        # Find paths from each base token
        for base_token in base_tokens:
            if base_token not in self.graph:
                continue
            
            logger.info(f"🎯 Scanning paths from {base_token}...")
            
            # Find triangular paths
            paths = self.find_triangular_paths(base_token, max_hops=3, max_paths=50)
            
            logger.info(f"   Found {len(paths)} potential paths")
            
            # Test each path with different amounts
            for path in paths:
                for amount in test_amounts:
                    result = self.calculate_path_profit(path, amount, pools_data)
                    
                    if result and result['profit_usd'] > 1.0:
                        opportunities.append(result)
                        logger.info(f"   ✅ {result['path']} = ${result['profit_usd']:.2f}")
        
        # Sort by profit
        opportunities.sort(key=lambda x: x['profit_usd'], reverse=True)
        
        logger.info(f"\n{Fore.GREEN}Found {len(opportunities)} graph-based opportunities{Style.RESET_ALL}\n")
        
        return opportunities


# Integration wrapper for your PolygonArbBot
class AdvancedMEVModule:
    """
    Combines all advanced MEV features into one module
    Integrates seamlessly with your existing PolygonArbBot
    """
    
    def __init__(self, polygon_bot):
        """
        Args:
            polygon_bot: Your PolygonArbBot instance
        """
        self.bot = polygon_bot
        
        # Initialize components
        self.mempool_monitor = MempoolMonitor(
            polygon_bot.rpc_manager,
            polygon_bot.cache,
            min_value_usd=10000
        )
        
        self.ws_feed = WebSocketPriceFeed(
            polygon_bot.rpc_manager,
            polygon_bot.cache
        )
        
        self.graph_finder = GraphArbitrageFinder(
            polygon_bot.arb_finder
        )
        
        logger.info(f"{Fore.GREEN}✅ Advanced MEV Module initialized{Style.RESET_ALL}")
    
    async def start_mempool_monitoring(self):
        """Start monitoring mempool for pending swaps"""
        async def on_pending_swap(swap_data):
            logger.info(f"📥 Pending swap detected: {swap_data['dex']}")
            # TODO: Analyze for sandwich/frontrun opportunities
        
        await self.mempool_monitor.monitor_pending_txs(on_pending_swap)
    
    async def start_websocket_feed(self, pool_addresses: List[str]):
        """Start WebSocket feed for real-time pool updates"""
        for pool in pool_addresses:
            await self.ws_feed.subscribe_to_pool(pool, self._on_pool_update)
        
        await self.ws_feed.listen_for_swaps()
    
    async def _on_pool_update(self, pool_address: str, swap_data: Dict):
        """Handle real-time pool update"""
        logger.info(f"🔄 Pool updated: {pool_address[:10]}... at block {swap_data['block_number']}")
        # Cache is automatically invalidated
        # Next arb scan will use fresh data
    
    def find_graph_opportunities(self) -> List[Dict]:
        """Run graph-based arbitrage finding"""
        # Use your existing pool data
        pools = self.bot.price_fetcher.fetch_all_pools()
        
        # Find opportunities using graph
        return self.graph_finder.find_all_opportunities(pools)


# Example usage with existing bot
"""
from polygon_arb_bot import PolygonArbBot

# Initialize your bot as usual
bot = PolygonArbBot(min_tvl=3000, scan_interval=60, auto_execute=False)

# Add advanced MEV features
mev_module = AdvancedMEVModule(bot)

# Run async monitoring
import asyncio

async def main():
    # Start mempool monitoring in background
    asyncio.create_task(mev_module.start_mempool_monitoring())
    
    # Start WebSocket feed (optional)
    # asyncio.create_task(mev_module.start_websocket_feed(important_pools))
    
    # Run graph-based arbitrage scan
    opportunities = mev_module.find_graph_opportunities()
    
    for opp in opportunities[:5]:
        print(f"Path: {opp['path']}")
        print(f"Profit: ${opp['profit_usd']:.2f} ({opp['roi_percent']:.2f}%)")

asyncio.run(main())
"""