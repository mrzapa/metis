#Requires -Version 5.1
<#
.SYNOPSIS
    Axiom - combined local API + next-gen web dev launcher (Windows).

.DESCRIPTION
    Starts the existing API dev script and the Next.js dev server together on
    localhost, then stops both when this script exits.
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir
$WebDir = Join-Path $RepoRoot "apps\axiom-web"
$ApiScript = Join-Path $ScriptDir "run_api_dev.ps1"
$ApiHost = "127.0.0.1"
$ApiPort = 8000
$WebHost = "127.0.0.1"
$WebPort = 3000
$ApiUrl = "http://${ApiHost}:${ApiPort}"
$ApiHealthUrl = "${ApiUrl}/healthz"
$WebUrl = "http://${WebHost}:${WebPort}"
$WebNext = Join-Path $WebDir "node_modules\.bin\next.cmd"
$ShellPath = (Get-Process -Id $PID).Path
$ApiProcess = $null
$WebProcess = $null
$ExitCode = 0

function Write-Info {
    param([string]$Message)
    Write-Host "[run_nextgen_dev] $Message"
}

function Fail {
    param([string]$Message)
    throw [System.InvalidOperationException]::new("[run_nextgen_dev] ERROR: $Message")
}

function Get-InstallHint {
    if (Test-Path (Join-Path $WebDir "pnpm-lock.yaml")) {
        return "cd apps/axiom-web; pnpm install"
    }
    return "cd apps/axiom-web; npm install"
}

function Test-PortInUse {
    param(
        [string]$Host,
        [int]$Port
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($Host, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(250)) {
            return $false
        }
        $null = $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Test-UrlReady {
    param([string]$Url)

    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromMilliseconds(500)

    try {
        $response = $client.GetAsync($Url).GetAwaiter().GetResult()
        try {
            return [int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500
        }
        finally {
            $response.Dispose()
        }
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-ForUrl {
    param(
        [string]$Label,
        [string]$Url,
        [System.Diagnostics.Process]$Process,
        [int]$Attempts = 240
    )

    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        if (Test-UrlReady -Url $Url) {
            return $true
        }
        if ($null -ne $Process) {
            $Process.Refresh()
            if ($Process.HasExited) {
                return $false
            }
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Info "$Label did not respond within $($Attempts / 2) seconds."
    return $false
}

function Stop-ChildProcess {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Label
    )

    if ($null -eq $Process) {
        return
    }

    try {
        $Process.Refresh()
    }
    catch {
        return
    }

    if ($Process.HasExited) {
        return
    }

    Write-Info "Stopping $Label..."
    $null = & taskkill /PID $Process.Id /T /F 2>$null
    try {
        $null = $Process.WaitForExit(5000)
    }
    catch {
    }
}

try {
    if (-not (Test-Path (Join-Path $RepoRoot "pyproject.toml"))) {
        Fail "pyproject.toml not found at repo root."
    }
    if (-not (Test-Path (Join-Path $WebDir "package.json"))) {
        Fail "apps/axiom-web/package.json not found."
    }
    if (-not (Test-Path $WebNext)) {
        Fail "Web dependencies are missing. Run '$(Get-InstallHint)' and retry."
    }
    if (Test-PortInUse -Host $ApiHost -Port $ApiPort) {
        Fail "Port $ApiPort is already in use. Stop the process on $ApiUrl or run the API separately."
    }
    if (Test-PortInUse -Host $WebHost -Port $WebPort) {
        Fail "Port $WebPort is already in use. Stop the process on $WebUrl or free the Next dev port."
    }

    Write-Info "API URL: $ApiUrl"
    Write-Info "Web URL: $WebUrl"
    Write-Info "Stop both servers with Ctrl-C."
    Write-Info "Troubleshooting: free ports $ApiPort/$WebPort if occupied; reinstall web deps with '$(Get-InstallHint)'."
    Write-Info "Starting API bootstrap via scripts/run_api_dev.ps1 (first run may take longer while .venv and deps install)..."
    $ApiProcess = Start-Process -FilePath $ShellPath -ArgumentList @("-NoProfile", "-File", $ApiScript) -WorkingDirectory $RepoRoot -NoNewWindow -PassThru

    $PreviousApiBase = $env:NEXT_PUBLIC_AXIOM_API_BASE
    $env:NEXT_PUBLIC_AXIOM_API_BASE = $ApiUrl
    try {
        Write-Info "Starting Next.js dev server in apps/axiom-web..."
        $WebProcess = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "node_modules\\.bin\\next.cmd", "dev", "--hostname", $WebHost, "--port", "$WebPort") -WorkingDirectory $WebDir -NoNewWindow -PassThru
    }
    finally {
        if ($null -eq $PreviousApiBase) {
            Remove-Item Env:NEXT_PUBLIC_AXIOM_API_BASE -ErrorAction SilentlyContinue
        }
        else {
            $env:NEXT_PUBLIC_AXIOM_API_BASE = $PreviousApiBase
        }
    }

    Write-Info "Waiting for API health check at $ApiHealthUrl..."
    if (-not (Wait-ForUrl -Label "API" -Url $ApiHealthUrl -Process $ApiProcess)) {
        Fail "API server did not become ready at $ApiHealthUrl. Check the console output above."
    }
    Write-Info "API is responding."

    Write-Info "Waiting for web UI at $WebUrl..."
    if (-not (Wait-ForUrl -Label "Web UI" -Url $WebUrl -Process $WebProcess)) {
        Fail "Web UI did not become ready at $WebUrl. Check the console output above."
    }
    Write-Info "Web UI is responding."
    Write-Info "Both servers are ready."

    while ($true) {
        Start-Sleep -Seconds 1
        $ApiProcess.Refresh()
        $WebProcess.Refresh()
        if ($ApiProcess.HasExited) {
            Fail "API dev server exited unexpectedly."
        }
        if ($WebProcess.HasExited) {
            Fail "Web dev server exited unexpectedly."
        }
    }
}
catch {
    $ExitCode = 1
    Write-Host $_.Exception.Message -ForegroundColor Red
}
finally {
    Stop-ChildProcess -Process $WebProcess -Label "web dev server"
    Stop-ChildProcess -Process $ApiProcess -Label "API dev server"
}

exit $ExitCode
