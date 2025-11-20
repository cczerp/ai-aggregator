#!/bin/bash
# Stop the automation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/automation.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

if [ ! -f "$PID_FILE" ]; then
    echo -e "${YELLOW}⚠️  Automation is not running (no PID file found)${NC}"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Automation is not running (stale PID file)${NC}"
    rm "$PID_FILE"
    exit 0
fi

echo -e "${CYAN}🛑 Stopping automation (PID: $PID)...${NC}"

# Send SIGTERM for graceful shutdown
kill -TERM "$PID"

# Wait up to 10 seconds for graceful shutdown
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Automation stopped gracefully${NC}"
        rm "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running
echo -e "${YELLOW}⚠️  Forcing shutdown...${NC}"
kill -KILL "$PID" 2>/dev/null

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Automation stopped${NC}"
    rm "$PID_FILE"
else
    echo -e "${RED}❌ Failed to stop automation${NC}"
    exit 1
fi
