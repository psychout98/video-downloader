@echo off
setlocal
title Media Downloader -- Setup
set SCRIPT_DIR=%~dp0

:: Strip trailing backslash for use in PowerShell strings
set WD=%SCRIPT_DIR%
if "%WD:~-1%"=="\" set WD=%WD:~0,-1%

echo.
echo  ==========================================
echo    Media Downloader -- Setup
echo  ==========================================
echo.

:: Admin check
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Right-click this file and choose "Run as administrator".
    pause & exit /b 1
)
echo  [OK] Running as Administrator

:: .env check
if not exist "%SCRIPT_DIR%.env" (
    echo.
    echo  [ERROR] No .env file found.
    echo  Copy .env.example to .env and fill in your API keys.
    pause & exit /b 1
)
echo  [OK] .env found

:: Find Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python not found. Install from https://python.org
    echo  Check "Add Python to PATH" during install.
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('where python') do ( set PYTHON=%%i & goto :py_found )
:py_found
echo  [OK] Python: %PYTHON%

:: Create .venv
echo.
echo  [1/4] Setting up virtual environment...
if not exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    "%PYTHON%" -m venv "%SCRIPT_DIR%.venv"
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create .venv
        pause & exit /b 1
    )
)
set PY=%SCRIPT_DIR%.venv\Scripts\python.exe
set PYW=%SCRIPT_DIR%.venv\Scripts\pythonw.exe
echo  [OK] .venv ready

:: Install packages
echo.
echo  [2/4] Installing packages...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install -r "%SCRIPT_DIR%requirements.txt"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] pip install failed. See errors above.
    pause & exit /b 1
)
echo  [OK] Packages installed

:: Register with Task Scheduler
:: run_server.bat handles logging to logs\server.log
:: wscript launches it silently (no console window flash)
echo.
echo  [3/4] Registering startup task...
set PS1=%TEMP%\setup_media_downloader.ps1

echo $a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '"%WD%\silent_launch.vbs"' -WorkingDirectory '%WD%' > "%PS1%"
echo $t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME >> "%PS1%"
echo Register-ScheduledTask -TaskName 'MediaDownloader' -Action $a -Trigger $t -Description 'Media Downloader web server' -Force >> "%PS1%"
echo Write-Host '[OK] Task registered' >> "%PS1%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Task Scheduler registration failed. See errors above.
    pause & exit /b 1
)
del "%PS1%" >nul 2>&1

:: Firewall
echo.
echo  [4/4] Configuring firewall...
netsh advfirewall firewall delete rule name="MediaDownloader" >nul 2>&1
netsh advfirewall firewall add rule name="MediaDownloader" dir=in action=allow protocol=TCP localport=8000 profile=private description="Media Downloader web UI"
echo  [OK] Firewall rule added for port 8000

:: Start it now without waiting for next login
echo.
echo  Starting server...
schtasks /run /tn "MediaDownloader"
if %errorlevel% neq 0 (
    echo  [WARNING] Could not start task right now. It will start on next login.
) else (
    timeout /t 3 /nobreak >nul
    echo  [OK] Server started
)

echo.
echo  ==========================================
echo    Done!
echo.
echo    Web UI:  http://localhost:8000
echo.
echo    Starts automatically when you log in.
echo  ==========================================
echo.
pause
