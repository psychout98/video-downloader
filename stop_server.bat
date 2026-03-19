@echo off
cd /d "%~dp0"

echo Stopping Media Downloader server...

REM ── Method 1: PID file (most reliable) ───────────────────────────────────
if exist "server.pid" (
    set /p SERVER_PID=<server.pid
    echo Found PID file: %SERVER_PID%
    taskkill /PID %SERVER_PID% /F >nul 2>&1
    if errorlevel 1 (
        echo Process %SERVER_PID% not found ^(already stopped^).
    ) else (
        echo Server stopped successfully.
    )
    del "server.pid" >nul 2>&1
    goto :done
)

REM ── Method 2: Fallback — find python process on port 8000 ─────────────────
echo server.pid not found — trying port scan fallback...
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr " :8000 " ^| findstr "LISTENING"') do (
    echo Killing PID %%p on port 8000...
    taskkill /PID %%p /F >nul 2>&1
    if not errorlevel 1 (
        echo Server stopped.
        goto :done
    )
)
echo No server process found — it may already be stopped.

:done
pause
