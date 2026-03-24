@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Please run MediaDownloader-Setup.exe to install the application.
    pause
    exit /b 1
)

if not exist "logs" mkdir logs

REM Read PORT from .env (default 8000)
set PORT=8000
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    if "%%a"=="PORT" set PORT=%%b
)

echo Starting Media Downloader server on port %PORT% (foreground / debug mode)...
echo Press Ctrl+C to stop. For background mode use start_silent.bat instead.
echo.
.venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port %PORT%
pause
