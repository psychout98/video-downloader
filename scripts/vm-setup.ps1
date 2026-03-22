# vm-setup.ps1 — Run inside the Windows 11 VM to set up the dev environment
# Usage: powershell -ExecutionPolicy Bypass -File vm-setup.ps1

param(
    [string]$RepoUrl = "",
    [string]$RepoDir = "$HOME\video-downloader"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Media Downloader VM Setup ===" -ForegroundColor Cyan

# Check for required tools
$missing = @()
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $missing += "Python" }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { $missing += "Node.js" }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { $missing += "Git" }

if ($missing.Count -gt 0) {
    Write-Host "Missing: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Install with: winget install Python.Python.3.12 OpenJS.NodeJS.LTS Git.Git"
    exit 1
}

Write-Host "Python: $(python --version)" -ForegroundColor Green
Write-Host "Node:   $(node --version)" -ForegroundColor Green
Write-Host "Git:    $(git --version)" -ForegroundColor Green

# Clone or update repo
if (Test-Path $RepoDir) {
    Write-Host "`nUpdating repo at $RepoDir..." -ForegroundColor Yellow
    Push-Location $RepoDir
    git pull
    Pop-Location
} elseif ($RepoUrl) {
    Write-Host "`nCloning repo to $RepoDir..." -ForegroundColor Yellow
    git clone $RepoUrl $RepoDir
} else {
    Write-Host "`nRepo dir not found and no URL provided. Specify -RepoUrl." -ForegroundColor Red
    exit 1
}

# Install backend deps
Write-Host "`nInstalling Python dependencies..." -ForegroundColor Yellow
Push-Location $RepoDir
pip install -r server/requirements.txt
Pop-Location

# Install frontend deps
Write-Host "`nInstalling Node dependencies..." -ForegroundColor Yellow
Push-Location "$RepoDir\frontend"
npm install
Pop-Location

Write-Host "`n=== Setup complete! ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start the app, open two terminals:" -ForegroundColor White
Write-Host "  Terminal 1 (backend):  cd $RepoDir && uvicorn server.main:app --host 0.0.0.0 --port 8000"
Write-Host "  Terminal 2 (frontend): cd $RepoDir\frontend && npm run dev -- --host 0.0.0.0"
Write-Host ""
Write-Host "Then find this VM's IP with: ipconfig" -ForegroundColor White
Write-Host "Run tests from Mac: E2E_BASE_URL=http://<vm-ip>:5173 npm run test:e2e" -ForegroundColor White
