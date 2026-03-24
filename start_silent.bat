@echo off
REM Starts the Media Downloader server in the background (no console window).
REM The server keeps running after you close this window.
REM Output goes to logs\server.log.
REM
REM Use this when the Task Scheduler task is not set up, or you need to
REM restart the server manually without keeping a terminal window open.
REM For debugging / watching live output use run_server.bat instead.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Please run MediaDownloader-Setup.exe to install the application.
    pause
    exit /b 1
)

if not exist "silent_launch.vbs" (
    echo ERROR: silent_launch.vbs not found.
    echo Please run MediaDownloader-Setup.exe first.
    pause
    exit /b 1
)

echo Starting server in background...
wscript //nologo "%~dp0silent_launch.vbs"
echo Server started. Check logs\server.log for output.
timeout /t 2 /nobreak >nul
