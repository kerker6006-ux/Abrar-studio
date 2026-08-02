@echo off
setlocal
cd /d "%~dp0\.."
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  echo Install it from Microsoft Store or python.org, then run this file again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\pythonw.exe" (
  py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "Abrar Studio" .venv\Scripts\pythonw.exe app.py
