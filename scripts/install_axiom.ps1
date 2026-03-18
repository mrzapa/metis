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
$InstallSpec = "{0}[runtime-all,api]" -f $InstallDir
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
# Usage:
#   axiom                  -- Web UI (default)
#   axiom --desktop        -- Qt desktop GUI
#   axiom --gui            -- Qt desktop GUI (alias)
#   axiom --web            -- Web UI (legacy no-op, same as default)
#   axiom --cli <args>     -- CLI mode (args forwarded)
`$ErrorActionPreference = "Stop"
`$axiomDir    = "$InstallDir"
`$branch      = "$Branch"
`$venvPython  = "$VenvPython"
`$apiHost     = "127.0.0.1"
`$apiPort     = 8000
`$webHost     = "127.0.0.1"
`$webPort     = 3000
`$apiUrl      = "http://`$(`$apiHost):`$(`$apiPort)"
`$apiHealthUrl = "`$apiUrl/healthz"
`$webUrl      = "http://`$(`$webHost):`$(`$webPort)"
`$webDir      = Join-Path `$axiomDir "apps\axiom-web\out"

function Show-Help {
    Write-Host "Axiom launcher"
    Write-Host ""
    Write-Host "Usage:"
    Write-Host "  axiom                  Start the local API and static web UI"
    Write-Host "  axiom --desktop        Start the legacy Qt desktop shell"
    Write-Host "  axiom --gui            Alias for --desktop"
    Write-Host "  axiom --cli <args>     Run the CLI"
    Write-Host "  axiom --help           Show this help"
}

function Test-PortInUse {
    param(
        [string]`$HostName,
        [int]`$Port
    )

    `$client = [System.Net.Sockets.TcpClient]::new()
    try {
        `$async = `$client.BeginConnect(`$HostName, `$Port, `$null, `$null)
        if (-not `$async.AsyncWaitHandle.WaitOne(250)) {
            return `$false
        }
        `$null = `$client.EndConnect(`$async)
        return `$true
    }
    catch {
        return `$false
    }
    finally {
        `$client.Dispose()
    }
}

function Test-UrlReady {
    param([string]`$Url)

    `$client = [System.Net.Http.HttpClient]::new()
    `$client.Timeout = [TimeSpan]::FromMilliseconds(500)

    try {
        `$response = `$client.GetAsync(`$Url).GetAwaiter().GetResult()
        try {
            return [int]`$response.StatusCode -ge 200 -and [int]`$response.StatusCode -lt 500
        }
        finally {
            `$response.Dispose()
        }
    }
    catch {
        return `$false
    }
    finally {
        `$client.Dispose()
    }
}

function Wait-ForUrl {
    param(
        [string]`$Label,
        [string]`$Url,
        [System.Diagnostics.Process]`$Process,
        [int]`$Attempts = 60
    )

    for (`$attempt = 0; `$attempt -lt `$Attempts; `$attempt++) {
        if (Test-UrlReady -Url `$Url) {
            return `$true
        }
        if (`$null -ne `$Process) {
            try {
                `$Process.Refresh()
                if (`$Process.HasExited) {
                    return `$false
                }
            } catch {
                return `$false
            }
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Host "`$Label did not respond within `$(`$Attempts / 2) seconds." -ForegroundColor Yellow
    return `$false
}

function Get-LogTail {
    param([string]`$Path)

    if (-not (Test-Path `$Path)) {
        return ""
    }

    return ((Get-Content `$Path -Tail 40 -ErrorAction SilentlyContinue) -join "`n").Trim()
}

function Throw-StartupFailure {
    param(
        [string]`$Label,
        [System.Diagnostics.Process]`$Process,
        [string]`$StdOut,
        [string]`$StdErr,
        [string]`$Hint
    )

    `$details = [System.Collections.Generic.List[string]]::new()
    if (`$null -ne `$Process) {
        try {
            `$Process.Refresh()
            if (`$Process.HasExited) {
                `$details.Add("`$Label exited with code `$(`$Process.ExitCode).")
            }
        } catch {
        }
    }

    `$stdoutTail = Get-LogTail -Path `$StdOut
    if (-not [string]::IsNullOrWhiteSpace(`$stdoutTail)) {
        `$details.Add("`$Label stdout:`n`$stdoutTail")
    }

    `$stderrTail = Get-LogTail -Path `$StdErr
    if (-not [string]::IsNullOrWhiteSpace(`$stderrTail)) {
        `$details.Add("`$Label stderr:`n`$stderrTail")
    }

    if (-not [string]::IsNullOrWhiteSpace(`$Hint)) {
        `$details.Add(`$Hint)
    }

    throw [System.InvalidOperationException]::new((`$details -join "`n`n"))
}

function Stop-ChildProcess {
    param(
        [System.Diagnostics.Process]`$Process,
        [string]`$Label
    )

    if (`$null -eq `$Process) {
        return
    }

    try {
        `$Process.Refresh()
    }
    catch {
        return
    }

    if (`$Process.HasExited) {
        return
    }

    Write-Host "Stopping `$Label..." -ForegroundColor DarkGray
    `$null = & taskkill /PID `$Process.Id /T /F 2>`$null
    try {
        `$null = `$Process.WaitForExit(5000)
    }
    catch {
    }
}

if (Test-Path (Join-Path `$axiomDir ".git")) {
    try { git -C `$axiomDir pull origin `$branch --ff-only 2>`$null } catch {}
}

`$showHelp = (`$args -contains "-h") -or (`$args -contains "--help")
`$desktopMode = (`$args -contains "--desktop") -or (`$args -contains "--gui")
`$cliMode = `$args -contains "--cli"
`$launchArgs = @(`$args | Where-Object {
    `$_ -ne "--desktop" -and
    `$_ -ne "--gui" -and
    `$_ -ne "--web" -and
    `$_ -ne "--cli" -and
    `$_ -ne "-h" -and
    `$_ -ne "--help"
})

if (`$showHelp) {
    Show-Help
    exit 0
}

if (`$desktopMode -and `$cliMode) {
    throw [System.InvalidOperationException]::new("Choose either --desktop/--gui or --cli, not both.")
}

Push-Location `$axiomDir
try {
    if (`$desktopMode) {
        & `$venvPython (Join-Path `$axiomDir "main.py") @launchArgs
        exit `$LASTEXITCODE
    }

    if (`$cliMode) {
        & `$venvPython (Join-Path `$axiomDir "main.py") "--cli" @launchArgs
        exit `$LASTEXITCODE
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path `$webDir "index.html"))) {
    throw [System.InvalidOperationException]::new("Built web UI not found at `$webDir. Re-run the installer or build apps/axiom-web before launching.")
}

if ((Test-PortInUse -HostName `$apiHost -Port `$apiPort) -or (Test-PortInUse -HostName `$webHost -Port `$webPort)) {
    if ((Test-UrlReady -Url `$apiHealthUrl) -and (Test-UrlReady -Url `$webUrl)) {
        Start-Process `$webUrl
        Write-Host "Axiom is already running at `$webUrl."
        exit 0
    }
    throw [System.InvalidOperationException]::new("Ports `$apiPort/`$webPort are already in use. Stop the existing processes or close the app before starting a new instance.")
}

`$apiProcess = `$null
`$webProcess = `$null
`$apiStdOut = [System.IO.Path]::GetTempFileName()
`$apiStdErr = [System.IO.Path]::GetTempFileName()
`$webStdOut = [System.IO.Path]::GetTempFileName()
`$webStdErr = [System.IO.Path]::GetTempFileName()

try {
    `$apiSplat = @{
        FilePath               = `$venvPython
        ArgumentList           = @("-m", "uvicorn", "axiom_app.api.app:app", "--host", `$apiHost, "--port", "`$apiPort")
        WorkingDirectory       = `$axiomDir
        PassThru               = `$true
        WindowStyle            = "Minimized"
        RedirectStandardOutput = `$apiStdOut
        RedirectStandardError  = `$apiStdErr
    }
    `$apiProcess = Start-Process @apiSplat

    if (-not (Wait-ForUrl -Label "API" -Url `$apiHealthUrl -Process `$apiProcess)) {
        Throw-StartupFailure -Label "API server" -Process `$apiProcess -StdOut `$apiStdOut -StdErr `$apiStdErr -Hint "Verify that FastAPI dependencies are installed and that port `$apiPort is available."
    }

    `$webSplat = @{
        FilePath               = `$venvPython
        ArgumentList           = @("-m", "http.server", "`$webPort", "--bind", `$webHost, "--directory", `$webDir)
        WorkingDirectory       = `$axiomDir
        PassThru               = `$true
        WindowStyle            = "Minimized"
        RedirectStandardOutput = `$webStdOut
        RedirectStandardError  = `$webStdErr
    }
    `$webProcess = Start-Process @webSplat

    if (-not (Wait-ForUrl -Label "Web UI" -Url `$webUrl -Process `$webProcess)) {
        Throw-StartupFailure -Label "Web UI server" -Process `$webProcess -StdOut `$webStdOut -StdErr `$webStdErr -Hint "Verify that the exported web bundle exists at `$webDir and that port `$webPort is available."
    }

    Start-Process `$webUrl
    Write-Host "Axiom running (API PID `$(`$apiProcess.Id), Web PID `$(`$webProcess.Id)) at `$webUrl. Press Ctrl+C to stop."

    while (`$true) {
        Start-Sleep -Seconds 1
        `$apiProcess.Refresh()
        `$webProcess.Refresh()
        if (`$apiProcess.HasExited) {
            Throw-StartupFailure -Label "API server" -Process `$apiProcess -StdOut `$apiStdOut -StdErr `$apiStdErr -Hint "The API server stopped unexpectedly."
        }
        if (`$webProcess.HasExited) {
            Throw-StartupFailure -Label "Web UI server" -Process `$webProcess -StdOut `$webStdOut -StdErr `$webStdErr -Hint "The static web server stopped unexpectedly."
        }
    }
}
finally {
    Stop-ChildProcess -Process `$webProcess -Label "web UI server"
    Stop-ChildProcess -Process `$apiProcess -Label "API server"
    Remove-Item `$apiStdOut, `$apiStdErr, `$webStdOut, `$webStdErr -ErrorAction SilentlyContinue
}
"@ | Set-Content -Path $LauncherPs1 -Encoding UTF8

    # CMD wrapper so `axiom` works from cmd.exe too.
    @"
@echo off
REM Auto-generated Axiom launcher - do not edit.
set "PS_BIN=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not exist "%PS_BIN%" set "PS_BIN=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%PS_BIN%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0axiom.ps1" %*
exit /b %ERRORLEVEL%
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

    # ── Web UI (optional) ────────────────────────────────────────────────
    $WebAppDir = Join-Path $InstallDir "apps" "axiom-web"
    $WebPackageJson = Join-Path $WebAppDir "package.json"

    if (Get-Command "node" -ErrorAction SilentlyContinue) {
        if (Test-Path $WebPackageJson) {
            Write-Info "Node.js detected — building web UI..."
            Push-Location $WebAppDir
            try {
                npm install --silent
                npm run build
                Write-Ok "Web UI built successfully."
            } catch {
                Write-Warn "Web UI build failed: $_"
                Write-Warn "The backend is still usable without the web UI."
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "Web UI package.json not found at $WebPackageJson — skipping web build."
        }
    } else {
        Write-Warn "Node.js not found — skipping web UI build."
        Write-Warn "Install Node.js (https://nodejs.org) to enable the web UI."
    }

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
    Write-Host "  axiom                            # Launch Axiom"
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
