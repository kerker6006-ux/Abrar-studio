@echo off
setlocal
set "APP=%LOCALAPPDATA%\Programs\AbrarStudio"
if not exist "%APP%\.venv\Scripts\python.exe" (
  echo Abrar Studio is not installed in the expected location.
  pause
  exit /b 1
)
cd /d "%APP%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%APP%\scripts\verify.ps1"
if errorlevel 1 (
  echo.
  echo Abrar Studio verification failed.
  pause
  exit /b 1
)
echo.
echo Abrar Studio passed all three unit and 720p render verification passes.
pause
