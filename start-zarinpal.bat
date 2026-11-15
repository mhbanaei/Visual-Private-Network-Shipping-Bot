@echo off
setlocal
title Visual Private Network - Zarinpal Version
cd /d "%~dp0"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
    echo [ERROR] Python was not found.
    echo Install Python 3.10+ and enable "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer is required.
    %PY% --version
    echo.
    pause
    exit /b 1
)

echo Checking required packages (only missing ones are installed)...
%PY% -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo   - requests is missing, installing...
    %PY% -m pip install requests
    %PY% -c "import requests" >nul 2>&1 || %PY% -m pip install --user requests
)

%PY% -c "import telegram" >nul 2>&1
if errorlevel 1 (
    echo   - python-telegram-bot is missing, installing...
    %PY% -m pip install "python-telegram-bot>=20.7"
    %PY% -c "import telegram" >nul 2>&1 || %PY% -m pip install --user "python-telegram-bot>=20.7"
)

%PY% -c "import qrcode" >nul 2>&1
if errorlevel 1 (
    echo   - qrcode is missing, installing QR support...
    %PY% -m pip install "qrcode[pil]"
    %PY% -c "import qrcode" >nul 2>&1 || %PY% -m pip install --user "qrcode[pil]"
)

%PY% -c "import requests, telegram" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Could not install the required packages.
    echo Try running this file as Administrator.
    echo.
    pause
    exit /b 1
)

echo Starting Visual Private Network - Zarinpal Version...
echo.
%PY% "Visual-Private-Network-Shipping.py"
echo.
echo Bot stopped.
pause
