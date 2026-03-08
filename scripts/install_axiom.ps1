#Requires -Version 5.1
<#
.SYNOPSIS
    Axiom Installer for Windows — install, reinstall, or uninstall the Axiom app.

.DESCRIPTION
    Downloads (or updates) the Axiom repository, creates a Python virtual
    environment, installs dependencies, and generates a launcher script.

    The launcher auto-pulls the latest code on every run.

.PARAMETER Action
    install   — Fresh install (default)
    reinstall — Remove venv and reinstall from scratch
    uninstall — Remove Axiom completely
    update    — Pull latest code and update deps

.EXAMPLE
    .\install_axiom.ps1
    .\install_axiom.ps1 -Action reinstall
    .\install_axiom.ps1 -Action uninstall

.NOTES
    Environment overrides:
      AXIOM_INSTALL_DIR  — where to clone  (default: ~\axiom)
      AXIOM_REPO         — git clone URL   (default: https://github.com/mrzapa/axiom.git)
      AXIOM_BRANCH       — branch          (default: main)
      AXIOM_PYTHON       — python binary   (default: python)
#>
[CmdletBinding()]
param(
    [ValidateSet("install", "reinstall", "uninstall", "update")]
    [string]$Action = "install"
)

$ErrorActionPreference = "Stop"

# ── Defaults ─────────────────────────────────────────────────────────────────
$InstallDir  = if ($env:AXIOM_INSTALL_DIR) { $env:AXIOM_INSTALL_DIR } else { Join-Path $HOME "axiom" }
$RepoUrl     = if ($env:AXIOM_REPO)        { $env:AXIOM_REPO }        else { "https://github.com/mrzapa/axiom.git" }
$Branch      = if ($env:AXIOM_BRANCH)      { $env:AXIOM_BRANCH }      else { "main" }
$PythonBin   = if ($env:AXIOM_PYTHON)      { $env:AXIOM_PYTHON }      else { "python" }
$VenvDir     = Join-Path $InstallDir ".venv"
$InstallSpec = "{0}[runtime-all]" -f $InstallDir
$LauncherDir = Join-Path $HOME ".local" "bin"
$LauncherPs1 = Join-Path $LauncherDir "axiom.ps1"
$LauncherCmd = Join-Path $LauncherDir "axiom.cmd"

# ── Helpers ──────────────────────────────────────────────────────────────────
function Write-Info  { param([string]$Msg) Write-Host "[axiom] $Msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "[axiom] $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "[axiom] $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "[axiom] $Msg" -ForegroundColor Red }

function Write-Launchers {
    param([string]$VenvPython)

    if (-not (Test-Path $LauncherDir)) {
        New-Item -ItemType Directory -Path $LauncherDir -Force | Out-Null
    }

    # PowerShell launcher
    @"
# Auto-generated Axiom launcher - do not edit.
`$ErrorActionPreference = "Stop"
`$axiomDir = "$InstallDir"
`$branch   = "$Branch"

# Pull latest code silently
if (Test-Path (Join-Path `$axiomDir ".git")) {
    try { git -C `$axiomDir pull origin `$branch --ff-only 2>`$null } catch {}
}

# Run Axiom (MVC is the default path in main.py)
& "$VenvPython" (Join-Path `$axiomDir "main.py") @args
"@ | Set-Content -Path $LauncherPs1 -Encoding UTF8

    # CMD wrapper so `axiom` works from cmd.exe too
    @"
@echo off
REM Auto-generated Axiom launcher - do not edit.
cd /d "$InstallDir"
git pull origin $Branch --ff-only >nul 2>&1
"$VenvPython" "$InstallDir\main.py" %*
"@ | Set-Content -Path $LauncherCmd -Encoding ASCII
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Err "Required command '$Name' not found. Please install it and try again."
        exit 1
    }
}

function Assert-PythonVersion {
    try {
        $ver = & $PythonBin -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>&1
        $parts = $ver -split "\."
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Err "Python >= 3.10 is required (found $ver)."
            exit 1
        }
        Write-Ok "Python $ver detected."
    } catch {
        Write-Err "Could not determine Python version. Is '$PythonBin' installed?"
        exit 1
    }
}

# ── Uninstall ────────────────────────────────────────────────────────────────
function Invoke-Uninstall {
    Write-Info "Uninstalling Axiom..."

    foreach ($f in @($LauncherPs1, $LauncherCmd)) {
        if (Test-Path $f) {
            Remove-Item $f -Force
            Write-Ok "Removed launcher: $f"
        }
    }

    if (Test-Path $InstallDir) {
        Remove-Item $InstallDir -Recurse -Force
        Write-Ok "Removed install directory: $InstallDir"
    } else {
        Write-Warn "Install directory not found: $InstallDir (already removed?)"
    }

    Write-Ok "Axiom has been uninstalled."
}

# ── Install / Reinstall ─────────────────────────────────────────────────────
function Invoke-Install {
    param([bool]$IsReinstall = $false)

    Assert-Command "git"
    Assert-Command $PythonBin
    Assert-PythonVersion

    # ── Clone or pull ────────────────────────────────────────────────────
    $gitDir = Join-Path $InstallDir ".git"
    if (Test-Path $gitDir) {
        if ($IsReinstall) {
            Write-Info "Reinstall requested - pulling latest code..."
            git -C $InstallDir fetch origin $Branch
            git -C $InstallDir checkout $Branch 2>$null
            git -C $InstallDir reset --hard "origin/$Branch"
            Write-Ok "Repository updated to latest origin/$Branch."
        } else {
            Write-Info "Existing installation found - pulling latest code..."
            git -C $InstallDir fetch origin $Branch
            git -C $InstallDir checkout $Branch 2>$null
            try {
                git -C $InstallDir pull origin $Branch --ff-only
            } catch {
                Write-Warn "Fast-forward pull failed. Running hard reset to origin/$Branch."
                git -C $InstallDir reset --hard "origin/$Branch"
            }
            Write-Ok "Repository up to date."
        }
    } else {
        Write-Info "Cloning repository from $RepoUrl (branch: $Branch)..."
        git clone --branch $Branch --single-branch $RepoUrl $InstallDir
        Write-Ok "Repository cloned."
    }

    # ── Virtual environment ──────────────────────────────────────────────
    if ($IsReinstall -and (Test-Path $VenvDir)) {
        Write-Info "Reinstall: removing old virtual environment..."
        Remove-Item $VenvDir -Recurse -Force
    }

    if (-not (Test-Path $VenvDir)) {
        Write-Info "Creating virtual environment..."
        & $PythonBin -m venv $VenvDir
        Write-Ok "Virtual environment created."
    }

    $VenvPython = Join-Path $VenvDir "Scripts" "python.exe"
    $VenvPip    = Join-Path $VenvDir "Scripts" "pip.exe"

    Write-Info "Installing dependencies..."
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPip install -e $InstallSpec --quiet
    Write-Ok "Dependencies installed."

    # ── Launcher scripts ─────────────────────────────────────────────────
    Write-Launchers -VenvPython $VenvPython

    Write-Ok "Launchers installed:"
    Write-Ok "  PowerShell : $LauncherPs1"
    Write-Ok "  CMD        : $LauncherCmd"

    # ── Summary ──────────────────────────────────────────────────────────
    Write-Host ""
    Write-Host "Axiom installed successfully!" -ForegroundColor Green -BackgroundColor Black
    Write-Host ""
    Write-Info "Install directory : $InstallDir"
    Write-Info "Virtual env       : $VenvDir"
    Write-Host ""
    Write-Info "Run Axiom:"
    Write-Host "  axiom                            # GUI mode"
    Write-Host "  axiom --cli index --file f.txt   # CLI mode"
    Write-Host ""

    # Check PATH
    $pathDirs = $env:PATH -split ";"
    if ($pathDirs -notcontains $LauncherDir) {
        Write-Warn "$LauncherDir is not in your PATH."
        Write-Warn "Add it via: [Environment]::SetEnvironmentVariable('PATH', `"$LauncherDir;`$env:PATH`", 'User')"
    }
}

# ── Update ───────────────────────────────────────────────────────────────────
function Invoke-Update {
    Assert-Command "git"

    $gitDir = Join-Path $InstallDir ".git"
    if (-not (Test-Path $gitDir)) {
        Write-Err "Axiom is not installed at $InstallDir. Run install first."
        exit 1
    }

    Write-Info "Pulling latest code..."
    git -C $InstallDir fetch origin $Branch
    git -C $InstallDir checkout $Branch 2>$null
    try {
        git -C $InstallDir pull origin $Branch --ff-only
    } catch {
        Write-Warn "Fast-forward pull failed. Running hard reset to origin/$Branch."
        git -C $InstallDir reset --hard "origin/$Branch"
    }

    $VenvPython = Join-Path $VenvDir "Scripts" "python.exe"
    $VenvPip    = Join-Path $VenvDir "Scripts" "pip.exe"

    Write-Info "Updating dependencies..."
    & $VenvPython -m pip install --upgrade pip --quiet
    & $VenvPip install -e $InstallSpec --quiet
    Write-Launchers -VenvPython $VenvPython

    Write-Ok "Axiom updated to latest."
}

# ── Main ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Axiom Installer ===" -ForegroundColor Cyan
Write-Host ""

switch ($Action) {
    "install"   { Invoke-Install -IsReinstall $false }
    "reinstall" { Invoke-Install -IsReinstall $true  }
    "uninstall" { Invoke-Uninstall }
    "update"    { Invoke-Update }
}
