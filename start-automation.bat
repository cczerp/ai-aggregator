@echo off
REM ArbiGirl Automation - Windows Starter
REM Just double-click this file to start!

echo ========================================
echo   Starting Graph Arbitrage Automation
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

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python 3.8+ from python.org
    echo.
    pause
    exit /b 1
)

echo Starting automation...
echo Press Ctrl+C to stop
echo.

REM Run the automation
python run_graph_automation.py

pause
