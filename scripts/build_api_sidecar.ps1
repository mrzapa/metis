#Requires -Version 5.1
<#
.SYNOPSIS
    Build the metis-api sidecar binary for Tauri desktop bundling (WOR-14).

.DESCRIPTION
    Produces a standalone one-file console binary of metis_app.api and places it
    at apps/metis-desktop/src-tauri/binaries/metis-api-{target-triple}.exe, which
    is the naming convention Tauri v2 requires for externalBin sidecar binaries.

    Prerequisites: Python environment with metis-app[api] installed, Rust toolchain
    Usage: powershell -File scripts/build_api_sidecar.ps1
#>
$ErrorActionPreference = "Stop"

# ── Resolve paths ────────────────────────────────────────────────────────────
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutDir   = Join-Path $RepoRoot "apps" "metis-desktop" "src-tauri" "binaries"

# ── Detect Rust target triple ───────────────────────────────────────────────
try {
    $rustcOutput = rustc -Vv 2>&1
} catch {
    Write-Error "rustc not found. Please install the Rust toolchain and try again."
    exit 1
}

$hostLine = ($rustcOutput | Select-String -Pattern "^host:").Line
if (-not $hostLine) {
    Write-Error "Could not parse target triple from 'rustc -Vv' output."
    exit 1
}
$TargetTriple = ($hostLine -split ":\s*", 2)[1].Trim()

Write-Host "[build_api_sidecar] Target triple: $TargetTriple"
Write-Host "[build_api_sidecar] Output dir:    $OutDir"

# ── Install PyInstaller ──────────────────────────────────────────────────────
pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install PyInstaller."
    exit 1
}

# ── Clean previous build artifacts ─────────────────────────────────────────
$DistDir = Join-Path $RepoRoot "dist"
$BuildDir = Join-Path $RepoRoot "build"

if (Test-Path $DistDir) {
    Write-Host "[build_api_sidecar] Cleaning previous dist folder..."
    Remove-Item -Path $DistDir -Recurse -Force
}
if (Test-Path $BuildDir) {
    Write-Host "[build_api_sidecar] Cleaning previous build folder..."
    Remove-Item -Path $BuildDir -Recurse -Force
}

# ── Build sidecar binary ────────────────────────────────────────────────────
$AssetsData       = "${RepoRoot}\metis_app\assets;metis_app/assets"
$SettingsData     = "${RepoRoot}\metis_app\default_settings.json;metis_app"
$EntryPoint       = Join-Path $RepoRoot "metis_app" "api" "__main__.py"

if (-not (Test-Path $EntryPoint)) {
    Write-Error "Entry point not found: $EntryPoint"
    exit 1
}

Write-Host "[build_api_sidecar] Building sidecar binary..."
pyinstaller `
    --noconfirm `
    --name metis-api `
    --onefile `
    --console `
    --collect-submodules metis_app `
    --add-data $AssetsData `
    --add-data $SettingsData `
    $EntryPoint

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit 1
}

# ── Validate output ─────────────────────────────────────────────────────────
$SourceBinary = Join-Path $DistDir "metis-api.exe"
if (-not (Test-Path $SourceBinary)) {
    Write-Error "PyInstaller did not produce expected output: $SourceBinary"
    exit 1
}

# ── Copy to Tauri binaries directory ─────────────────────────────────────────
if (-not (Test-Path $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}

$DestBinary = Join-Path $OutDir "metis-api-${TargetTriple}.exe"

Copy-Item -Path $SourceBinary -Destination $DestBinary -Force

Write-Host "[build_api_sidecar] Sidecar written to: $DestBinary"
Write-Host "[build_api_sidecar] Build complete!"
