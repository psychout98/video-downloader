# run-integration.ps1 — Run Windows integration tests
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run-integration.ps1 [options]
#
# Options:
#   -Suite <name>     Run a specific suite: "installer", "wpf", "mpc", or "all" (default: "all")
#   -InstallerPath    Path to MediaDownloader-Setup.exe (default: dist/MediaDownloader-Setup.exe)
#   -AppExePath       Path to built MediaDownloader.exe (default: build/publish/MediaDownloader.exe)
#   -MediaFile        Path to a test media file for MPC-BE tests
#   -BackendUrl       Backend API URL (default: http://127.0.0.1:8000)

param(
    [ValidateSet("all", "installer", "wpf", "mpc")]
    [string]$Suite = "all",
    [string]$InstallerPath = "",
    [string]$AppExePath = "",
    [string]$MediaFile = "",
    [string]$BackendUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# If running from the scripts dir, adjust
if (-not (Test-Path "$RepoRoot\tests")) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
if (-not (Test-Path "$RepoRoot\tests")) {
    $RepoRoot = (Get-Location).Path
}

Write-Host "=== Media Downloader Integration Tests ===" -ForegroundColor Cyan
Write-Host "Repo root: $RepoRoot" -ForegroundColor Gray
Write-Host ""

# ── Check Python ──────────────────────────────────────────────────
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.12+." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $(python --version)" -ForegroundColor Green

# ── Install test dependencies ─────────────────────────────────────
Write-Host "`nInstalling integration test dependencies..." -ForegroundColor Yellow
pip install -r "$RepoRoot\requirements-integration.txt" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "Dependencies installed." -ForegroundColor Green

# ── Set environment variables ─────────────────────────────────────
if ($InstallerPath) { $env:MD_INSTALLER_PATH = $InstallerPath }
if ($AppExePath) { $env:MD_APP_EXE_PATH = $AppExePath }
if ($MediaFile) { $env:TEST_MEDIA_FILE = $MediaFile }
$env:MD_BACKEND_URL = $BackendUrl

# ── Build test path ───────────────────────────────────────────────
$testPath = "$RepoRoot\tests\integration"
$testArgs = @("-v", "--tb=short")

switch ($Suite) {
    "installer" { $testPath = "$testPath\test_installer.py" }
    "wpf"       { $testPath = "$testPath\test_wpf_app.py" }
    "mpc"       { $testPath = "$testPath\test_mpc_integration.py" }
    "all"       { } # run entire directory
}

# ── Run tests ─────────────────────────────────────────────────────
Write-Host "`nRunning: pytest $testPath $($testArgs -join ' ')" -ForegroundColor Yellow
Write-Host ""

Push-Location $RepoRoot
python -m pytest $testPath @testArgs
$exitCode = $LASTEXITCODE
Pop-Location

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "=== All tests passed! ===" -ForegroundColor Green
} elseif ($exitCode -eq 5) {
    Write-Host "=== No tests collected (prerequisites not met) ===" -ForegroundColor Yellow
} else {
    Write-Host "=== Some tests failed (exit code: $exitCode) ===" -ForegroundColor Red
}

exit $exitCode
