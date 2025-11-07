@echo off
title 🔄 Updating MEV Bot (Claude Branch)
echo.
echo ==========================================
echo   🚀  Syncing with Claude's latest commit
echo   Branch: claude/mev-implementation-plan-011CUtDwRK2eiVe4jtgJoH7L
echo ==========================================
echo.

cd /d "C:\Desktop\projettccs\mev bots\aggregator bot"

echo [1/3] Activating virtual environment...
call venv\Scripts\activate

echo [2/3] Fetching and resetting to latest branch...
git fetch origin
git checkout claude/mev-implementation-plan-011CUtDwRK2eiVe4jtgJoH7L
git reset --hard origin/claude/mev-implementation-plan-011CUtDwRK2eiVe4jtgJoH7L

echo.
echo [3/3] Running ai_bridge.py...
echo ==========================================
python ai_bridge.py

echo.
echo Done! Press any key to close...
pause >nul