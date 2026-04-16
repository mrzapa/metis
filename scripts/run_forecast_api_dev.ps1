#Requires -Version 5.1
<#
.SYNOPSIS
    METIS Forecast API dev server (Windows, Python 3.11).

.DESCRIPTION
    Creates .venv311-forecast\ if absent, installs .[dev,api], pins the
    validated TimesFM source revision with torch extras, installs XReg
    dependencies, and starts the Litestar forecast backend on
    http://127.0.0.1:8000.

    Run from the repo root:
        .\scripts\run_forecast_api_dev.ps1

    Override the Python executable:
        $env:METIS_FORECAST_PYTHON = "C:\Path\To\python.exe"
        .\scripts\run_forecast_api_dev.ps1
#>

$ErrorActionPreference = "Stop"

$TimesFmRef = "f085b9079918092aa5e3917a4e135f87f91a7f03"
$PythonExe = if ($env:METIS_FORECAST_PYTHON) { $env:METIS_FORECAST_PYTHON } else { "py" }
$PythonArgs = if ($env:METIS_FORECAST_PYTHON) { @() } else { @("-3.11") }
$VenvDir = ".venv311-forecast"
$VenvPython = Join-Path $VenvDir "Scripts" "python.exe"
$VenvPip = Join-Path $VenvDir "Scripts" "pip.exe"

if (-not (Test-Path "pyproject.toml")) {
    Write-Host "[run_forecast_api_dev] ERROR: pyproject.toml not found." -ForegroundColor Red
    Write-Host "[run_forecast_api_dev] Run this script from the repo root." -ForegroundColor Red
    exit 1
}

$versionOutput = & $PythonExe @PythonArgs -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to execute the requested Python interpreter."
}
if ($versionOutput.Trim() -ne "3.11") {
    throw "Forecast dev uses Python 3.11. Set METIS_FORECAST_PYTHON to a Python 3.11 executable if needed."
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "[run_forecast_api_dev] Creating Python 3.11 forecast environment..."
    & $PythonExe @PythonArgs -m venv $VenvDir
}

Write-Host "[run_forecast_api_dev] Installing .[dev,api] into $VenvDir ..."
& $VenvPython -m pip install --quiet --upgrade pip setuptools wheel
& $VenvPip install --quiet -e ".[dev,api]"

Write-Host "[run_forecast_api_dev] Installing TimesFM torch runtime from pinned upstream revision..."
& $VenvPip install --quiet "timesfm[torch] @ git+https://github.com/google-research/timesfm.git@$TimesFmRef"

Write-Host "[run_forecast_api_dev] Installing XReg dependencies (jax + scikit-learn)..."
& $VenvPip install --quiet jax scikit-learn

Write-Host "[run_forecast_api_dev] Starting Litestar forecast backend at http://127.0.0.1:8000 (Ctrl-C to stop)"
& $VenvPython -m uvicorn metis_app.api_litestar.app:app --reload --host 127.0.0.1 --port 8000
