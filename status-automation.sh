#!/bin/bash
# Check automation status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/automation.pid"
LOG_DIR="$SCRIPT_DIR/logs"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Automation Status${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

if [ ! -f "$PID_FILE" ]; then
    echo -e "${RED}Status: NOT RUNNING${NC}"
    echo ""
    echo -e "${CYAN}To start: ./start-automation.sh${NC}"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${GREEN}Status: RUNNING ✓${NC}"
    echo -e "PID: $PID"

    # Get process info
    if command -v ps &> /dev/null; then
        START_TIME=$(ps -p "$PID" -o lstart= 2>/dev/null)
        CPU=$(ps -p "$PID" -o %cpu= 2>/dev/null)
        MEM=$(ps -p "$PID" -o %mem= 2>/dev/null)

        echo -e "Started: $START_TIME"
        echo -e "CPU: ${CPU}%"
        echo -e "Memory: ${MEM}%"
    fi

    echo ""

    # Show recent log activity
    LATEST_LOG=$(ls -t "$LOG_DIR"/automation-*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo -e "${CYAN}Latest Log: $LATEST_LOG${NC}"
        echo ""
        echo -e "${CYAN}Last 5 lines:${NC}"
        tail -5 "$LATEST_LOG" 2>/dev/null | sed 's/^/  /'
        echo ""
        echo -e "${CYAN}To view full logs: tail -f $LATEST_LOG${NC}"
    fi

    echo ""
    echo -e "${CYAN}Commands:${NC}"
    echo -e "  ./stop-automation.sh   - Stop the automation"
    echo -e "  tail -f $LATEST_LOG   - Follow logs"
else
    echo -e "${RED}Status: NOT RUNNING (stale PID file)${NC}"
    rm "$PID_FILE"
    echo ""
    echo -e "${CYAN}To start: ./start-automation.sh${NC}"
fi
