@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_dashboard.ps1" %*
exit /b %errorlevel%
