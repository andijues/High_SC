@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto fallback
".venv\Scripts\python.exe" stop.py
goto end
:fallback
python stop.py
:end
pause
