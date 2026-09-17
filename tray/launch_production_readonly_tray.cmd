@echo off
setlocal
set "TRAY=%~dp0BigQMT_Production_ReadOnly.exe"
if not exist "%TRAY%" (
  echo BigQMT production readonly tray EXE is missing: %TRAY%
  pause
  exit /b 2
)
start "BigQMT Production Readonly Tray" "%TRAY%"
endlocal
