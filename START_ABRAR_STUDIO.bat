@echo off
setlocal
set "INSTALLED=%LOCALAPPDATA%\Programs\AbrarStudio\RUN_ABRAR_STUDIO.bat"
if exist "%INSTALLED%" (
  call "%INSTALLED%"
  exit /b %errorlevel%
)
echo Abrar Studio is not installed yet. Starting the installer...
call "%~dp0INSTALL_ABRAR_STUDIO.bat"
