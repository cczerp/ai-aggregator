#!/bin/bash
# Simple Background Automation Runner (No Sudo Required)
# Just run: ./start-automation.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/automation.pid"
LOG_DIR="$SCRIPT_DIR/logs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Create logs directory
mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Automation already running (PID: $PID)${NC}"
        echo -e "${CYAN}Use ./stop-automation.sh to stop it first${NC}"
        exit 1
    else
        # Stale PID file
        rm "$PID_FILE"
    fi
fi

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Starting Graph Arbitrage Automation${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Check .env file
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo -e "${YELLOW}Please create .env file with your configuration${NC}"
    exit 1
fi

# Source .env to check AUTO_EXECUTE setting
source "$SCRIPT_DIR/.env"

echo -e "${GREEN}Configuration:${NC}"
echo -e "  MIN_TVL_USD: ${MIN_TVL_USD:-3000}"
echo -e "  SCAN_INTERVAL_SECONDS: ${SCAN_INTERVAL_SECONDS:-60}"
echo -e "  AUTO_EXECUTE: ${AUTO_EXECUTE:-false}"
echo ""

if [ "${AUTO_EXECUTE}" = "true" ]; then
    echo -e "${YELLOW}⚡ AUTO-EXECUTION ENABLED!${NC}"
    echo -e "${YELLOW}   Bot will automatically execute profitable trades via Alchemy private bundles${NC}"
    echo ""
    read -p "Continue? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Aborted${NC}"
        exit 0
    fi
fi

# Start automation in background
echo -e "${GREEN}🚀 Starting automation in background...${NC}"

cd "$SCRIPT_DIR"

nohup python3 run_graph_automation.py > "$LOG_DIR/automation-$(date +%Y%m%d-%H%M%S).log" 2>&1 &

PID=$!
echo $PID > "$PID_FILE"

# Wait a moment to check if it started successfully
sleep 2

if ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Automation started successfully!${NC}"
    echo -e "${GREEN}   PID: $PID${NC}"
    echo -e "${GREEN}   Log: $LOG_DIR/automation-*.log${NC}"
    echo ""
    echo -e "${CYAN}Management commands:${NC}"
    echo -e "  ./stop-automation.sh    - Stop the automation"
    echo -e "  ./status-automation.sh  - Check if running"
    echo -e "  tail -f $LOG_DIR/automation-*.log  - View logs"
    echo ""
else
    echo -e "${RED}❌ Failed to start automation${NC}"
    rm "$PID_FILE"
    exit 1
fi
