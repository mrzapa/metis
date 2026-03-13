#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Invoke-NativeStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Command

    if (-not $?) {
        throw "Step failed: $Label"
    }

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")

Set-Location $repoRoot

Invoke-NativeStep -Label "Running ruff check ." -Command {
    ruff check .
}

Invoke-NativeStep -Label "Running python -m pytest" -Command {
    python -m pytest
}

Invoke-NativeStep -Label "Validating axiom_app/default_settings.json" -Command {
    python -c "import json, pathlib; path = pathlib.Path('axiom_app/default_settings.json'); json.loads(path.read_text(encoding='utf-8')); print(f'Settings JSON OK: {path}')"
}
