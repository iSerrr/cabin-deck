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

if /i "%~1"=="update" goto update
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
goto :eof

rem Update mode, started by the console after "git pull" changed its packages:
rem   console.bat update <pid of the old console> [dry]
:update
title Cab Deck Console update
echo Waiting for the old console to close...
set /a tries=0
:waitold
tasklist /FI "PID eq %~2" /FI "IMAGENAME eq electron.exe" /NH 2>nul | find /I "electron.exe" >nul
if errorlevel 1 goto oldgone
set /a tries+=1
if %tries% geq 30 (
    echo The old console did not close. Close it, then run console.bat.
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto waitold

:oldgone
timeout /t 2 /nobreak >nul
echo Installing the console's packages...
call npm install --no-save --no-audit --no-fund
if errorlevel 1 echo npm install failed ^(see above^). Trying to start the console anyway...
if /i "%~3"=="dry" (
    call npm run start:dry
) else (
    call npm start
)
if errorlevel 1 (
    echo The console did not start. Run console.bat again; if it fails again, delete overlay\node_modules and run console.bat.
    pause
)
