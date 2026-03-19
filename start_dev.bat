@echo off
setlocal
title Media Downloader -- Dev Server
set SCRIPT_DIR=%~dp0

echo.
echo  Media Downloader -- Dev Server
echo  ================================
echo.

:: Create .venv if it doesn't exist
if not exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    python -m venv "%SCRIPT_DIR%.venv"
)
set VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe

:: Install / update packages
echo  Installing packages...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r "%SCRIPT_DIR%requirements.txt" --quiet

:: Copy .env from example if missing
if not exist "%SCRIPT_DIR%.env" (
    if exist "%SCRIPT_DIR%.env.example" (
        copy "%SCRIPT_DIR%.env.example" "%SCRIPT_DIR%.env" >nul
        echo  [NOTE] Created .env from .env.example -- fill in your API keys!
        pause
    )
)

:: Start server with auto-reload
echo.
echo  Starting on http://localhost:8000
echo  Press Ctrl+C to stop.
echo.
cd /d "%SCRIPT_DIR%"
"%VENV_PY%" -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
pause
