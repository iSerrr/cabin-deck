@echo off
rem Start the Cab Deck Console: it runs the server, shows the QR codes and controls the dash overlay.
rem Needs Node.js 18+ (https://nodejs.org) and, for the server, run.bat once to create .venv.
cd /d "%~dp0overlay"

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js is not installed. Get the LTS version from https://nodejs.org and run this again.
    pause
    exit /b 1
)

if not exist node_modules goto install
if not exist node_modules\qrcode goto install
goto start

:install
echo Installing Electron and QR code support, first start only...
call npm install --no-audit --no-fund
if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
)

:start
call npm start
