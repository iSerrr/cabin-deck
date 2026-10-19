@echo off
rem Start the Cab Deck Console (it includes the dash overlay over the game). Same app as console.bat.
rem Needs Node.js 18+ (https://nodejs.org). The first start installs Electron (~100 MB).
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
call npm install --no-save --no-audit --no-fund
if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
)

:start
call npm start
