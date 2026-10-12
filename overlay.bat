@echo off
rem Start the Alpha Gen dash overlay over the game. Run run.bat (the server) first.
rem Needs Node.js 18+ (https://nodejs.org). The first start installs Electron (~100 MB).
cd /d "%~dp0overlay"

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js is not installed. Get the LTS version from https://nodejs.org and run this again.
    pause
    exit /b 1
)

if not exist node_modules (
    echo Installing Electron, first start only...
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo npm install failed.
        pause
        exit /b 1
    )
)

call npm start
