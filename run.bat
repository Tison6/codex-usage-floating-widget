@echo off
chcp 65001 > nul
cd /d "%~dp0"

:: 1. Check pythonw in PATH (clean background launch)
where pythonw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pythonw "main.py"
    goto :eof
)

:: 2. Check pyw launcher in PATH
where pyw >nul 2>nul
if %errorlevel% equ 0 (
    start "" pyw "main.py"
    goto :eof
)

:: 3. Common installation directories
if exist "C:\Python313\pythonw.exe" (
    start "" "C:\Python313\pythonw.exe" "main.py"
    goto :eof
)
if exist "C:\ProgramData\Anaconda3\pythonw.exe" (
    start "" "C:\ProgramData\Anaconda3\pythonw.exe" "main.py"
    goto :eof
)

:: 4. Fallback to standard python
where python >nul 2>nul
if %errorlevel% equ 0 (
    start "" python "main.py"
    goto :eof
)

echo [Error] Python not found. Please ensure Python 3.8+ is installed and added to PATH.
pause
