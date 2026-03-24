@echo off
setlocal
title Media Downloader -- Dev Mode
set SCRIPT_DIR=%~dp0

echo.
echo  Media Downloader -- Dev Mode
echo  ================================
echo  Backend: http://localhost:8000  (FastAPI + uvicorn --reload)
echo  Frontend: http://localhost:5173  (Vite dev server with HMR)
echo.

:: ── Python venv ────────────────────────────────────────────────────────────
if not exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    echo  Creating virtual environment...
    python -m venv "%SCRIPT_DIR%.venv"
)
set VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe

echo  Installing Python packages...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r "%SCRIPT_DIR%requirements.txt" --quiet

:: ── .env ───────────────────────────────────────────────────────────────────
if not exist "%SCRIPT_DIR%.env" (
    if exist "%SCRIPT_DIR%.env.example" (
        copy "%SCRIPT_DIR%.env.example" "%SCRIPT_DIR%.env" >nul
        echo  [NOTE] Created .env from .env.example -- fill in your API keys!
        pause
    )
)

:: ── Node modules ───────────────────────────────────────────────────────────
if not exist "%SCRIPT_DIR%frontend\node_modules" (
    echo  Installing frontend dependencies...
    cd /d "%SCRIPT_DIR%frontend"
    call npm install
    cd /d "%SCRIPT_DIR%"
)

:: ── Start backend (background) ─────────────────────────────────────────────
echo.
echo  Starting backend on http://localhost:8000 ...
start "MediaDownloader-Backend" cmd /c "cd /d "%SCRIPT_DIR%" && "%VENV_PY%" -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload"

:: ── Start frontend (foreground) ────────────────────────────────────────────
echo  Starting frontend on http://localhost:5173 ...
echo  Press Ctrl+C to stop the frontend. Close the backend window separately.
echo.
cd /d "%SCRIPT_DIR%frontend"
call npx vite
