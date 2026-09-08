@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [桌面悬浮插件] 正在启动...

if exist "C:\Python313\python.exe" (
    "C:\Python313\python.exe" "main.py"
    goto :eof
)
if exist "C:\ProgramData\Anaconda3\python.exe" (
    "C:\ProgramData\Anaconda3\python.exe" "main.py"
    goto :eof
)
python "main.py"
if errorlevel 1 pause
