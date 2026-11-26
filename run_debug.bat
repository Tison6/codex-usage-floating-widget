@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo [codex-usage-floating-widget] Starting in Console Debug Mode
echo ========================================================
echo.

python "main.py"
if errorlevel 1 (
    echo.
    echo ========================================================
    echo [Error] Startup failed.
    echo If dependencies are missing, run:
    echo     pip install -r requirements.txt
    echo ========================================================
    echo.
    pause
)
