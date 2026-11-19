@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" goto ready
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 goto failed
:ready
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch.py"
exit /b 0
:failed
echo High_SC setup failed. Run the install/repair launcher and check the message.
pause
exit /b 1
