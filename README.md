# AI-Aggregator MEV Bot

A sophisticated Polygon-based MEV arbitrage bot that scans 300+ token pairs across multiple DEXes to find and execute profitable arbitrage opportunities using flashloans.

## Features

### Core Functionality
- **Multi-DEX Arbitrage**: Scans QuickSwap, SushiSwap, Uniswap V3, and Curve
- **Flashloan Integration**: Supports both Aave V3 and Balancer V2 flashloans
- **Accurate Pricing**: Direct DEX contract queries (no approximations)
- **Smart Execution**: Automatic trade execution with profit verification
- **Trade Persistence**: SQLite database for trade history and analytics
- **REST API**: FastAPI server for programmatic access
- **AI-Powered CLI**: Natural language interface with OpenAI integration

### Safety & Reliability
- **RPC Redundancy**: 15+ Polygon RPC endpoints with automatic failover
- **Gas Optimization**: EIP-1559 with dynamic fee calculation
- **Private Transactions**: Alchemy private RPC for MEV protection
- **Error Handling**: Comprehensive logging and error tracking
- **Caching**: Persistent cache for pool data (24h expiration)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interfaces                       │
├─────────────────────────────────────────────────────────┤
│  ai_bridge.py (CLI)    │  REST API Clients              │
│  - Natural language    │  - HTTP requests                │
│  - Keyword parsing     │  - Programmatic access          │
└────────────┬────────────────────────┬────────────────────┘
             │                        │
             └────────┬───────────────┘
                      ↓
         ┌────────────────────────────┐
         │   api_bridge.py (FastAPI)  │
         │   REST API Server          │
         │   - /scan                  │
         │   - /status                │
         │   - /simulate              │
         │   - /propose               │
         └──────────┬─────────────────┘
                    ↓
    ┌───────────────────────────────────────────┐
    │          Core Scanner Layer               │
    ├───────────────────────────────────────────┤
    │  pool_scanner.py  →  arb_scanner.py      │
    │  (find pools)        (detect arbs)       │
    │         ↓                   ↓             │
    │  price_math.py   (calculate prices)      │
    └──────────┬──────────────────┬─────────────┘
               │                  │
    ┌──────────┴──────┐  ┌───────┴──────────┐
    │  rpc_mgr.py     │  │ trade_database.py│
    │  (RPC failover) │  │ (SQLite logging) │
    └─────────────────┘  └──────────────────┘
               │
    ┌──────────┴─────────────────┐
    │   tx_builder.py             │
    │   (build transactions)      │
    │          ↓                  │
    │   flashloan_contract.py     │
    │   (execute flashloans)      │
    └─────────────────────────────┘
```

## Installation

### Prerequisites
- Python 3.8+
- Polygon RPC access (Alchemy, Infura, or public)
- OpenAI API key (optional, for AI features)
- Wallet with MATIC for gas

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/ai-aggregator.git
cd ai-aggregator
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment**
```bash
cp .env.example .env
nano .env  # Edit with your keys
```

Required `.env` variables:
```bash
# API Keys
ALCHEMY_API_KEY=your_alchemy_key
OPENAI_API_KEY=your_openai_key  # Optional

# Wallet (for execution)
WALLET_PRIVATE_KEY=your_private_key

# Bot Settings
ARBIGIRL_MIN_PROFIT_USD=1.0
ARBIGIRL_AUTO_EXECUTE=false  # Set to true for auto-execution

# API Bridge
API_PORT=5050
ARBIGIRL_BRIDGE_URL=http://127.0.0.1:5050
```

4. **Deploy flashloan contract** (optional, for execution)
   - See `flashloan_contract.py` for deployment instructions
   - Or use Remix IDE with `flashloanbot.sol`
   - Update `.env` with `FLASHLOAN_CONTRACT_ADDRESS=0x...`

## Usage

### Quick Start

1. **Start the API server**
```bash
python api_bridge.py
```

2. **Start the CLI (in another terminal)**
```bash
python ai_bridge.py
```

3. **Run a scan**
```
You> scan
```

4. **Enable continuous scanning**
```
You> scan continuous
```

5. **Check status**
```
You> status
```

### Direct Mode (without API server)

If you don't want to run the API server:

```bash
# Set USE_API_MODE=false in .env
python ai_bridge.py
```

The CLI will fall back to direct scanner mode.

### REST API Usage

The API server exposes these endpoints:

#### GET /status
Get bot status and statistics

```bash
curl http://localhost:5050/status
```

#### POST /scan
Trigger an arbitrage scan

```bash
curl -X POST http://localhost:5050/scan \
  -H "Content-Type: application/json" \
  -d '{"min_profit_usd": 1.0, "min_tvl": 10000.0}'
```

#### POST /simulate
Simulate a trade execution

```bash
curl -X POST http://localhost:5050/simulate \
  -H "Content-Type: application/json" \
  -d '{"strategy": {"pair": "WMATIC/USDC", "net_profit_usd": 5.0}}'
```

#### POST /propose
Propose and optionally execute a trade

```bash
curl -X POST http://localhost:5050/propose \
  -H "Content-Type: application/json" \
  -d '{
    "proposal": {
      "strategy_id": "test-1",
      "summary": "WMATIC/USDC arb",
      "profit_usd": 5.0,
      "payload": {}
    },
    "auto_execute": false
  }'
```

## Configuration

### Supported DEXes
- **QuickSwap** (V2)
- **SushiSwap** (V2)
- **Uniswap V3**
- **Curve** (partial support)

### Supported Tokens
- WMATIC
- WETH
- USDC
- USDT
- WBTC
- And more in `registries.py`

### RPC Endpoints
The bot uses 15+ public and private RPC endpoints with automatic failover:
- Alchemy (preferred)
- Infura
- Ankr
- Nodies
- Public endpoints

See `rpc_mgr.py` for full list.

## Database & Analytics

### Trade Database

All trades are logged to SQLite database (`trades.db`):

```python
from trade_database import get_database

db = get_database()

# Get analytics
stats = db.get_analytics(days=30)
print(f"Total profit: ${stats['total_profit_usd']}")
print(f"Win rate: {stats['win_rate_percent']}%")

# Get recent trades
recent = db.get_recent_trades(limit=10)

# Export to CSV
db.export_to_csv("trades_export.csv", days=30)
```

### Database Schema

- **trades**: Trade execution history
- **opportunities**: All detected opportunities
- **errors**: Error log with context
- **performance_metrics**: Scan times, success rates, etc.

## Development

### Project Structure

```
ai-aggregator/
├── api_bridge.py              # FastAPI REST server
├── ai_bridge.py               # Unified CLI client
├── arb_scanner.py             # Arbitrage detection logic
├── pool_scanner.py            # Pool discovery and scanning
├── price_math.py              # Price calculations (V2/V3)
├── tx_builder.py              # Transaction builder
├── flashloan_contract.py      # Contract ABI and helpers
├── flashloanbot.sol           # Solidity flashloan contract
├── trade_database.py          # SQLite persistence layer
├── rpc_mgr.py                 # RPC manager with failover
├── gas_optimization_manager.py # Gas optimization
├── polygon_arb_bot.py         # Main bot orchestrator
├── registries.py              # Token and DEX registries
├── abis.py                    # Contract ABIs
├── config.json                # Configuration
├── MEV_IMPLEMENTATION_PLAN.md # Full implementation plan
└── requirements.txt           # Python dependencies
```

### Adding a New DEX

1. Add DEX factory address to `registries.py`
2. Add pool discovery logic in `discover_pools.py`
3. Add price calculation in `price_math.py`
4. Add router address to config

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html
```

## Security Considerations

### Before Running in Production

1. **Test on Testnet First**
   - Deploy to Mumbai testnet
   - Test with small amounts
   - Verify all functions work

2. **Secure Your Keys**
   - Never commit `.env` file
   - Use hardware wallet for large amounts
   - Rotate keys regularly

3. **Set Profit Thresholds**
   - Start with conservative thresholds
   - Account for gas costs
   - Monitor slippage

4. **Monitor Execution**
   - Set up alerts (Telegram/Email)
   - Review trade logs daily
   - Track profitability

### Risk Mitigation

- **Maximum Loss Limits**: Set in configuration
- **Circuit Breakers**: Auto-pause after N failures
- **Slippage Protection**: Configured in trade execution
- **Gas Price Ceiling**: Max acceptable gas price

## Troubleshooting

### Common Issues

**"RPC endpoint timeout"**
- Check your RPC API keys
- Try different endpoints in `rpc_mgr.py`
- Increase timeout values

**"No opportunities found"**
- Lower `MIN_PROFIT_USD` threshold
- Check if pools are loaded (`status` command)
- Verify RPC connectivity

**"Execution failed"**
- Ensure wallet has MATIC for gas
- Check contract is deployed
- Verify contract address in `.env`

**"API server not available"**
- Check if `api_bridge.py` is running
- Verify port 5050 is not in use
- Try direct mode: `USE_API_MODE=false`

### Logs

- CLI logs: `arbigirl.log`
- API logs: Console output from `api_bridge.py`
- Database: `trades.db` (use SQLite browser)

## Roadmap

See `MEV_IMPLEMENTATION_PLAN.md` for detailed implementation plan.

### Completed ✅
- Multi-DEX pool scanning
- Accurate price calculations
- Arbitrage detection
- REST API server
- Trade database
- AI-powered CLI

### In Progress 🚧
- Flashloan execution automation
- Slippage protection
- Comprehensive error handling
- Test coverage

### Planned 📋
- Multi-chain support (Ethereum, Arbitrum, Optimism)
- Advanced MEV protection
- Machine learning optimization
- Web dashboard
- Backtesting framework

## Performance

### Benchmarks (Polygon Mainnet)

- **Pool Scan**: 30-60 seconds for 300+ pairs
- **Opportunity Detection**: < 5 seconds
- **RPC Calls**: 15-30 per scan (batched)
- **Cache Hit Rate**: ~85% after first scan

### Optimization Tips

- Use Alchemy or Infura for faster RPC
- Enable caching (default 24h)
- Run on server with good connectivity
- Use direct mode for fastest scanning

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## License

See [LICENSE](LICENSE) file for details.

## Disclaimer

**This software is for educational purposes only.**

- Use at your own risk
- No guarantee of profits
- Test thoroughly before production use
- Comply with all applicable laws
- MEV can be competitive and unprofitable

The authors assume no liability for any losses incurred.

## Support

- GitHub Issues: [Report bugs](https://github.com/yourusername/ai-aggregator/issues)
- Documentation: See `MEV_IMPLEMENTATION_PLAN.md`
- Logs: Check `arbigirl.log` for debugging

## Acknowledgments

- OpenZeppelin for secure contract patterns
- Aave and Balancer for flashloan protocols
- Web3.py for Ethereum interaction
- FastAPI for REST API framework

---

**Happy arbitraging! 🚀💰**
