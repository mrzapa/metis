#Requires -Version 5.1
<#
.SYNOPSIS
    METIS — local API dev server (Windows).

.DESCRIPTION
    Creates .venv\ if absent, installs .[dev,api], then starts uvicorn with
    hot-reload on http://127.0.0.1:8000.

    Run from the repo root:
        .\scripts\run_api_dev.ps1

    Override the Python binary:
        $env:METIS_PYTHON = "python3.12"; .\scripts\run_api_dev.ps1
#>

$ErrorActionPreference = "Stop"

$PythonBin = if ($env:METIS_PYTHON) { $env:METIS_PYTHON } else { "python" }
$VenvDir   = ".venv"
$VenvPython = Join-Path $VenvDir "Scripts" "python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts" "pip.exe"

# ── Sanity check ──────────────────────────────────────────────────────────────
if (-not (Test-Path "pyproject.toml")) {
    Write-Host "[run_api_dev] ERROR: pyproject.toml not found." -ForegroundColor Red
    Write-Host "[run_api_dev] Run this script from the repo root." -ForegroundColor Red
    exit 1
}

# ── Virtual environment ───────────────────────────────────────────────────────
if (-not (Test-Path $VenvDir)) {
    Write-Host "[run_api_dev] Creating virtual environment..."
    & $PythonBin -m venv $VenvDir
}

Write-Host "[run_api_dev] Installing .[dev,api]..."
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPip install --quiet -e ".[dev,api]"

# ── Start dev server ──────────────────────────────────────────────────────────
Write-Host "[run_api_dev] Starting uvicorn at http://127.0.0.1:8000 (Ctrl-C to stop)"
& $VenvPython -m uvicorn metis_app.api_litestar.app:app --reload --host 127.0.0.1 --port 8000
