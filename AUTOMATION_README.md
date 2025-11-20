# ArbiGirl Graph-Based Arbitrage Automation

Automated background arbitrage bot using graph-based pathfinding for multi-hop opportunities.

## Features

- **Graph-Based Detection**: Uses advanced graph algorithms to find multi-hop arbitrage paths
- **Continuous Background Execution**: Runs as a systemd service
- **Auto-Execution**: Optional flash loan execution (zero capital risk)
- **Comprehensive Logging**: Detailed logs for monitoring and debugging
- **Graceful Shutdown**: Handles signals properly for clean shutdowns
- **Resource Efficient**: Optimized for long-running background operation

## Quick Start

### 1. Configure Environment

Make sure your `.env` file is properly configured:

```bash
# Required
ALCHEMY_API_KEY=your_alchemy_key
PRIVATE_KEY=your_private_key
CONTRACT_ADDRESS=your_flashloan_contract_address

# Optional Configuration
MIN_TVL_USD=3000                    # Minimum pool liquidity
SCAN_INTERVAL_SECONDS=60            # Seconds between scans
AUTO_EXECUTE=false                  # Enable auto-execution (true/false)
BASE_TOKENS=USDC,WETH,WPOL,DAI      # Base tokens for graph paths
TEST_AMOUNTS=1000,5000,10000        # Test amounts in USD
LOG_DIR=./logs                      # Log directory
```

### 2. Run in Foreground (Testing)

Test the automation without installing as a service:

```bash
./automation-manager.sh run
```

Or directly:

```bash
python3 run_graph_automation.py
```

### 3. Install as Background Service

Install and enable the systemd service:

```bash
sudo ./automation-manager.sh install
```

### 4. Start the Service

```bash
sudo ./automation-manager.sh start
```

### 5. Monitor the Service

Check status:
```bash
./automation-manager.sh status
```

View logs:
```bash
./automation-manager.sh logs
```

## Management Commands

The `automation-manager.sh` script provides easy management:

| Command | Description | Requires Sudo |
|---------|-------------|---------------|
| `install` | Install systemd service | Yes |
| `uninstall` | Remove systemd service | Yes |
| `start` | Start the automation | Yes |
| `stop` | Stop the automation | Yes |
| `restart` | Restart the automation | Yes |
| `status` | Show service status | No |
| `logs` | View and follow logs | No |
| `run` | Run in foreground (testing) | No |
| `help` | Show help message | No |

## How It Works

### Graph-Based Arbitrage

The automation uses the `GraphArbitrageFinder` class from `advanced_mev_module.py`:

1. **Build Graph**: Creates a directed graph of all token pairs
2. **Find Paths**: Uses DFS to find profitable cycles (A → B → C → A)
3. **Calculate Profit**: Simulates each path accounting for fees and slippage
4. **Execute**: Optionally executes via flash loans (zero capital risk)

### Scanning Process

Each scan cycle:

1. Fetches all pool data from DEXes (QuickSwap, SushiSwap, Uniswap V3, etc.)
2. Builds a trading graph from the pool data
3. Finds profitable multi-hop arbitrage paths
4. Evaluates opportunities using configured test amounts
5. Optionally auto-executes profitable trades via flash loans

### Auto-Execution (Optional)

When `AUTO_EXECUTE=true`:

- Uses flash loans for zero capital risk
- Only executes if profit > gas + fees
- Implements safety limits and kill switches
- Transactions auto-revert on failure (only cost is gas)

## Configuration Details

### Environment Variables

#### Core Settings
- `MIN_TVL_USD`: Minimum pool TVL to consider (default: 3000)
- `SCAN_INTERVAL_SECONDS`: Seconds between scans (default: 60)
- `AUTO_EXECUTE`: Enable auto-execution (default: false)

#### Graph Settings
- `BASE_TOKENS`: Starting tokens for path finding (default: USDC,WETH,WPOL,DAI)
- `TEST_AMOUNTS`: Trade sizes to test (default: 1000,5000,10000)

#### Execution Limits (when AUTO_EXECUTE=true)
- `MIN_TRADE_SIZE_USD`: Minimum flash loan size (default: 1000)
- `MAX_TRADE_SIZE_USD`: Maximum flash loan size (default: 100000)
- `OPTIMAL_TRADE_SIZE_USD`: Optimal trade size (default: 15000)
- `MIN_PROFIT_AFTER_GAS`: Minimum profit after gas (default: 0.75)
- `MIN_PROFIT_AFTER_FEES`: Minimum profit after all fees (default: 1.00)
- `MAX_SLIPPAGE_PCT`: Maximum slippage tolerance (default: 3.0)
- `MIN_POOL_TVL`: Minimum pool liquidity (default: 5000)
- `MAX_TRADES_PER_MINUTE`: Rate limit (default: 10)
- `MAX_GAS_SPENT_PER_HOUR`: Gas spending limit (default: 5.0)
- `COOLDOWN_SECONDS`: Cooldown between trades (default: 0.1)
- `KILL_ON_CONSECUTIVE_FAILURES`: Kill switch threshold (default: 10)
- `PREFER_BALANCER`: Use Balancer for 0% fees (default: true)

### Logging

Logs are stored in the `logs/` directory:

- `graph_automation_TIMESTAMP.log`: Main application log
- `automation.log`: Systemd service stdout
- `automation-error.log`: Systemd service stderr

## Architecture

```
run_graph_automation.py
├── GraphArbitrageAutomation (Main class)
│   ├── PolygonArbBot (Core bot)
│   │   ├── RPCManager (RPC failover)
│   │   ├── Cache (Persistent caching)
│   │   ├── PriceDataFetcher (Pool data)
│   │   ├── ArbFinder (2-hop arbitrage)
│   │   └── AutoExecutor (Flash loans)
│   └── GraphArbitrageFinder (Multi-hop paths)
│       └── Graph pathfinding algorithms
```

## Safety Features

1. **Kill Switch**: Automatically stops after consecutive failures
2. **Rate Limiting**: Max trades per minute and gas per hour
3. **Cooldown**: Minimum time between trades
4. **TVL Checks**: Only trades on liquid pools
5. **Slippage Protection**: Max slippage tolerance
6. **Flash Loans**: Zero capital risk (auto-revert on failure)
7. **Signal Handling**: Graceful shutdown on SIGINT/SIGTERM

## Troubleshooting

### Service won't start

Check logs:
```bash
sudo journalctl -u arbigirl-automation -n 50
```

Check service status:
```bash
systemctl status arbigirl-automation
```

### No opportunities found

- Increase `SCAN_INTERVAL_SECONDS` for more thorough scanning
- Lower `MIN_TVL_USD` to include more pools
- Add more `BASE_TOKENS` to find more paths
- Check that RPC endpoints are working

### Import errors

Make sure all dependencies are installed:
```bash
pip3 install -r requirements.txt
```

### Permission errors

The service file assumes user `user`. Update the `User=` line in `arbigirl-automation.service` if needed.

## Performance Tips

1. **Scan Interval**: Start with 60s, adjust based on network conditions
2. **Base Tokens**: Focus on liquid stablecoins and major assets
3. **Test Amounts**: Use realistic trade sizes for your pools
4. **RPC Endpoints**: Configure multiple endpoints in `rpc_endpoints.json`
5. **Caching**: The system uses persistent caching to reduce RPC calls

## Monitoring

### Check if running
```bash
./automation-manager.sh status
```

### Live logs
```bash
./automation-manager.sh logs
```

### Statistics

The automation prints statistics every 10 scans:
- Total scans completed
- Graph opportunities found
- Regular opportunities found
- Total executions (if auto-execute enabled)
- Errors encountered
- Average opportunities per scan

## Advanced Usage

### Custom Configuration

Create a custom `.env` file:
```bash
cp .env .env.production
# Edit .env.production with your settings
```

Update service file to use it:
```ini
EnvironmentFile=/home/user/ai-aggregator/.env.production
```

### Multiple Instances

Run multiple instances with different configurations:
1. Copy service file: `cp arbigirl-automation.service arbigirl-automation-2.service`
2. Update service name and environment file
3. Install both services
4. Start both instances

### Integration with External Systems

The automation logs in JSON-compatible format. You can:
- Parse logs with `jq` or similar tools
- Send to monitoring systems (Grafana, Prometheus, etc.)
- Trigger alerts on errors or opportunities

## Security Considerations

1. **Private Keys**: Never commit `.env` file or private keys
2. **RPC URLs**: Use private RPC endpoints to avoid rate limits
3. **Gas Limits**: Set reasonable limits to prevent excessive spending
4. **Auto-Execute**: Test thoroughly before enabling
5. **Monitoring**: Always monitor the service in production

## Support

For issues or questions:
1. Check logs first
2. Review configuration
3. Test in foreground mode
4. Check RPC endpoint health

## License

See main project LICENSE file.
