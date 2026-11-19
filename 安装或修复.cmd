@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 goto failed
echo High_SC is ready. Open the start launcher.
pause
exit /b 0
:failed
echo Setup failed. Check Python and network, then retry.
pause
exit /b 1
