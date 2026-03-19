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
REM  Output:  dist\MediaDownloader-Setup.exe
REM ─────────────────────────────────────────────────────────────────
cd /d "%~dp0"

REM Install PyInstaller if not already present
python -m pip install pyinstaller --upgrade --quiet

echo Building installer...

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "MediaDownloader-Setup" ^
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
echo  Installer:  dist\MediaDownloader-Setup.exe
echo ================================================================
pause
