@echo off
setlocal
cd /d "%~dp0\.."
py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
python -m unittest discover -s tests -v
pause
