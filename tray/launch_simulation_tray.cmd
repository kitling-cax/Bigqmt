@echo off
setlocal
set "TRAY=%~dp0BigQMT_Simulation_90000001.exe"
if not exist "%TRAY%" (
  echo BigQMT simulation tray EXE is missing: %TRAY%
  pause
  exit /b 2
)
start "BigQMT Simulation Tray" "%TRAY%"
endlocal
