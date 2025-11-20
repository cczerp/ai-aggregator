@echo off
REM Check if automation is running

echo ========================================
echo   Automation Status
echo ========================================
echo.

REM Check for running Python process with our script
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq run_graph_automation.py" 2>nul | find /I "python.exe" >nul
if %errorlevel% equ 0 (
    echo Status: RUNNING
    echo.
    echo Process info:
    tasklist /FI "IMAGENAME eq python.exe" | findstr python
    echo.
) else (
    tasklist /FI "IMAGENAME eq pythonw.exe" 2>nul | find /I "pythonw.exe" >nul
    if %errorlevel% equ 0 (
        echo Status: RUNNING in background
        echo.
        echo Process info:
        tasklist /FI "IMAGENAME eq pythonw.exe" | findstr pythonw
        echo.
    ) else (
        echo Status: NOT RUNNING
        echo.
        echo To start: run start-automation.bat
        echo.
    )
)

REM Show latest log file
if exist logs\automation-*.log (
    echo Latest log file:
    for /f %%i in ('dir /b /od logs\automation-*.log') do set latest=%%i
    echo logs\%latest%
    echo.
    echo Last 10 lines:
    echo ----------------------------------------
    powershell -Command "Get-Content logs\%latest% -Tail 10"
    echo ----------------------------------------
    echo.
)

pause
