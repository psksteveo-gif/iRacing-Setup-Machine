<#
.SYNOPSIS
    Build iRacing Setup Advisor into a standalone Windows application.

.DESCRIPTION
    This script installs dependencies and uses PyInstaller to create
    a distributable folder with the .exe. Optionally builds a Windows
    installer using Inno Setup if it's installed.

.NOTES
    Run from the 'files' directory:
        .\build.ps1
#>

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  iRacing Setup Advisor - Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Install/upgrade build dependencies ─────────────────────────────
Write-Host "[1/5] Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pyinstaller
if (Test-Path "requirements-lock.txt") {
    python -m pip install -r requirements-lock.txt
} else {
    python -m pip install -r requirements.txt
}

# ── Step 1.5: Run tests ────────────────────────────────────────────────────
Write-Host "[1.5/5] Running tests..." -ForegroundColor Yellow
python -m pytest tests/ --tb=short -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "TESTS FAILED — aborting build." -ForegroundColor Red
    exit 1
}

# ── Step 2: Sync version into installer.iss ────────────────────────────────
Write-Host "[2/5] Syncing version to installer..." -ForegroundColor Yellow
$ver = (python -c "from version import VERSION; print(VERSION)")
if ($ver) {
    (Get-Content installer.iss) -replace 'AppVersion=.*', "AppVersion=$ver" `
        -replace 'VersionInfoVersion=.*', "VersionInfoVersion=$ver.0" |
        Set-Content installer.iss
    Write-Host "  Version set to $ver" -ForegroundColor White
}

# ── Step 3: Clean previous builds ──────────────────────────────────────────
Write-Host "[3/5] Cleaning previous builds..." -ForegroundColor Yellow
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# ── Step 4: Run PyInstaller ────────────────────────────────────────────────
Write-Host "[4/5] Building executable with PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller iRacingSetupAdvisor.spec --noconfirm

if (-not (Test-Path "dist\iRacingSetupAdvisor\iRacingSetupAdvisor.exe")) {
    Write-Host "BUILD FAILED - exe not found!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "BUILD SUCCESSFUL!" -ForegroundColor Green
Write-Host "  Executable: dist\iRacingSetupAdvisor\iRacingSetupAdvisor.exe" -ForegroundColor White
Write-Host ""

# ── Step 5: Optionally build installer with Inno Setup ────────────────────
$innoPath = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $innoPath) {
    Write-Host "[5/5] Building Windows installer with Inno Setup..." -ForegroundColor Yellow
    & $innoPath "installer.iss"
    Write-Host ""
    Write-Host "INSTALLER CREATED!" -ForegroundColor Green
    Write-Host "  Installer: dist\iRacingSetupAdvisor_Setup.exe" -ForegroundColor White
} else {
    Write-Host "[5/5] Inno Setup not found - skipping installer creation." -ForegroundColor DarkGray
    Write-Host "  To create a proper installer, install Inno Setup 6 from:" -ForegroundColor DarkGray
    Write-Host "  https://jrsoftware.org/isinfo.php" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  You can still run the app directly from:" -ForegroundColor White
    Write-Host "  dist\iRacingSetupAdvisor\iRacingSetupAdvisor.exe" -ForegroundColor White
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Cyan
