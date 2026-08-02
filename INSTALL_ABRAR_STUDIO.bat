@echo off
setlocal
cd /d "%~dp0"
title Abrar Studio Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
if errorlevel 1 (
  echo.
  echo Installation did not complete. Read the message above.
  pause
  exit /b 1
)
echo.
echo Abrar Studio installed successfully.
pause
