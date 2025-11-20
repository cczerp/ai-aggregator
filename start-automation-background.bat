@echo off
REM ArbiGirl Automation - Windows Background Runner
REM Starts in background (no window)

echo ========================================
echo   Starting Automation in Background
echo ========================================
echo.

REM Check if .env exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Please copy .env.example to .env and configure it
    echo.
    pause
    exit /b 1
)

REM Create logs directory
if not exist logs mkdir logs

REM Get timestamp for log file
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "timestamp=%dt:~0,8%-%dt:~8,6%"

echo Starting automation in background...
echo Log file: logs\automation-%timestamp%.log
echo.
echo To stop: Open Task Manager and end "python.exe" or "pythonw.exe"
echo.

REM Start in background (no window)
start /B pythonw run_graph_automation.py > logs\automation-%timestamp%.log 2>&1

echo Automation started!
echo.
echo Commands:
echo   status-automation.bat  - Check if running
echo   stop-automation.bat    - Stop the automation
echo.
pause
