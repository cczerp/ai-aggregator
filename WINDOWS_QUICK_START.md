# Windows Quick Start 🪟

**Super simple setup for Windows users!**

## Three Ways to Run on Windows

### 🎯 Option 1: Direct Python (Simplest)

Just run Python directly in your terminal:

```cmd
python run_graph_automation.py
```

Press `Ctrl+C` to stop. That's it!

### 📁 Option 2: Double-Click BAT File

Even simpler - just double-click:

**`start-automation.bat`** - Runs in visible window
**`start-automation-background.bat`** - Runs hidden in background

To manage:
- **`status-automation.bat`** - Check if running + view logs
- **`stop-automation.bat`** - Stop the automation

### 🔧 Option 3: PowerShell/CMD Commands

Open PowerShell or Command Prompt:

```cmd
# Foreground (press Ctrl+C to stop)
python run_graph_automation.py

# Background (runs hidden)
start /B pythonw run_graph_automation.py

# Check if running
tasklist | findstr python

# Stop it
taskkill /IM pythonw.exe /F
```

## Configuration (One Time Setup)

1. **Copy the example config:**
   ```cmd
   copy .env.example .env
   ```

2. **Edit `.env` with Notepad:**
   ```cmd
   notepad .env
   ```

3. **Set these 4 things:**
   ```bash
   ALCHEMY_API_KEY=your_key_here
   PRIVATE_KEY=your_wallet_key_here
   CONTRACT_ADDRESS=your_contract_address_here
   AUTO_EXECUTE=false   # Set to "true" to auto-execute trades
   ```

4. **Save and close**

## Running It

### To Just Watch (Observe Mode):
```cmd
# In .env, make sure:
AUTO_EXECUTE=false

# Then run:
start-automation.bat
```

Watch the output. If you see good opportunities, move to auto-execute mode.

### To Auto-Execute Trades:
```cmd
# In .env, set:
AUTO_EXECUTE=true

# Then run:
start-automation-background.bat
```

This runs in the background. Check logs with `status-automation.bat`

## Viewing Logs

Logs are saved in `logs\` folder:

```cmd
# View latest log
dir /od logs\automation-*.log
notepad logs\automation-YYYYMMDD-HHMMSS.log

# Or use PowerShell to follow live:
Get-Content logs\automation-*.log -Wait -Tail 20
```

## Troubleshooting

**"Python not found"**
- Install Python from https://python.org (check "Add to PATH")
- Restart Command Prompt after installing

**"Module not found" errors**
- Install requirements: `pip install -r requirements.txt`
- Make sure you're in the ai-aggregator folder

**Can't find the bot in Task Manager**
- Look for `python.exe` or `pythonw.exe`
- Filter by "Description" to see script name

**How do I know if it's working?**
- Run `status-automation.bat`
- Or check `logs\automation-*.log` file
- Should see "RUNNING SCAN #X" messages

## Common Commands

```cmd
# Start (foreground)
start-automation.bat

# Start (background)
start-automation-background.bat

# Check status
status-automation.bat

# Stop
stop-automation.bat

# View all logs
dir logs

# Install dependencies
pip install -r requirements.txt

# Test Python connection
python -c "from web3 import Web3; print('Web3 OK!')"
```

## WSL Alternative (Advanced)

If you have Windows Subsystem for Linux (WSL), you can use the Linux scripts:

```bash
# In WSL terminal:
./start-automation.sh
./status-automation.sh
./stop-automation.sh
```

## Does It Use Private Transactions?

**YES!** Already automatic. All transactions go through Alchemy's private transaction API to prevent MEV attacks. No extra setup needed.

## Is This Profitable?

See `QUICK_START.md` for honest discussion. Short answer:
- **Competitive** - Many bots hunting same trades
- **Low margins** - 0.1% - 0.5% typical
- **Graph method helps** - Finds multi-hop paths others miss
- **Start observing first** - Run with `AUTO_EXECUTE=false` for 1-2 days

## Ready?

1. Edit `.env` (copy from `.env.example`)
2. Double-click `start-automation.bat`
3. Watch for opportunities
4. If good ones show up, enable `AUTO_EXECUTE=true`

Good luck! 🚀
