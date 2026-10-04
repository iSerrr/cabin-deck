@echo off
rem Pull the latest code, refresh dependencies and start the server.
rem Usage: run.bat [server args]
cd /d "%~dp0"

echo [1/3] Pulling latest code...
git pull --ff-only
if errorlevel 1 (
    echo git pull failed. Fix the repository state and try again.
    pause
    exit /b 1
)

echo [2/3] Installing dependencies...
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 (
        echo Cannot create virtual environment. Is Python 3.10+ installed and on PATH?
        pause
        exit /b 1
    )
)
.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo pip install failed.
    pause
    exit /b 1
)

echo [3/3] Starting server...
if not exist server.py (
    echo server.py does not exist yet. Nothing to run.
    pause
    exit /b 0
)
.venv\Scripts\python server.py %*
pause
