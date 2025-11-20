@echo off
REM Stop the automation

echo ========================================
echo   Stopping Automation
echo ========================================
echo.

REM Try to kill python.exe running our script
taskkill /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq run_graph_automation.py" >nul 2>&1
if %errorlevel% equ 0 (
    echo Automation stopped!
    goto :done
)

REM Try to kill pythonw.exe (background process)
taskkill /FI "IMAGENAME eq pythonw.exe" >nul 2>&1
if %errorlevel% equ 0 (
    echo Background automation stopped!
    goto :done
)

echo Automation was not running.

:done
echo.
pause
