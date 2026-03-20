@echo off
REM ─────────────────────────────────────────────────────────────────
REM  Build Media Downloader Installer EXE using PyInstaller
REM
REM  Run this on Windows to build locally.
REM  On macOS, use GitHub Actions instead (see README or the workflow
REM  at .github/workflows/build-installer.yml):
REM    1. Push this repo to GitHub
REM    2. Go to Actions → "Build Windows Installer" → Run workflow
REM    3. Download MediaDownloader-Setup.exe from the Artifacts section
REM
REM  Output:  MediaDownloader-Setup.exe  (in this folder)
REM ─────────────────────────────────────────────────────────────────
cd /d "%~dp0"

REM Install PyInstaller if not already present
python -m pip install pyinstaller --upgrade --quiet

echo Building installer...

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "MediaDownloader-Setup" ^
    --distpath . ^
    --workpath build\_pyinstaller ^
    --specpath build ^
    --add-data "server;server" ^
    --add-data "run_server.bat;." ^
    --add-data "stop_server.bat;." ^
    --add-data "requirements.txt;." ^
    installer.pyw

if errorlevel 1 (
    echo.
    echo Build FAILED. Make sure Python and pip are in your PATH.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo  Build complete!
echo  Installer:  MediaDownloader-Setup.exe  (in this folder)
echo  Run it on any Windows machine — no need to extract a zip first.
echo ================================================================
pause
