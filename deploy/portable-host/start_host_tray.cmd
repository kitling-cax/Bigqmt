@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0provision_and_start.ps1" -Root "%~dp0"
if errorlevel 1 pause
endlocal
