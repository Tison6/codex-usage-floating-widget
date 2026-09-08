@echo off
chcp 65001 > nul
cd /d "%~dp0"

if exist "C:\Python313\pythonw.exe" (
    start "" "C:\Python313\pythonw.exe" "main.py"
    goto :eof
)
if exist "C:\ProgramData\Anaconda3\pythonw.exe" (
    start "" "C:\ProgramData\Anaconda3\pythonw.exe" "main.py"
    goto :eof
)
start "" pythonw.exe "main.py"
