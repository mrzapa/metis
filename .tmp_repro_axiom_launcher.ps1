$ErrorActionPreference = 'Stop'
$axiomDir = "$env:USERPROFILE\axiom"
$tempFile = [System.IO.Path]::GetTempFileName()
$tempErrFile = [System.IO.Path]::GetTempFileName()
$apiProcess = Start-Process -FilePath "$env:USERPROFILE\axiom\.venv\Scripts\python.exe" `
    -ArgumentList '-m', 'axiom_app.api' `
    -WorkingDirectory $axiomDir `
    -PassThru -WindowStyle Minimized `
    -RedirectStandardOutput $tempFile -RedirectStandardError $tempErrFile
Start-Sleep -Seconds 3
"PID=$($apiProcess.Id)"
"STDOUT_EXISTS=$(Test-Path $tempFile)"
"STDERR_EXISTS=$(Test-Path $tempErrFile)"
'STDOUT_CONTENT_START'
if (Test-Path $tempFile) { Get-Content $tempFile -Raw -ErrorAction SilentlyContinue }
'STDOUT_CONTENT_END'
'STDERR_CONTENT_START'
if (Test-Path $tempErrFile) { Get-Content $tempErrFile -Raw -ErrorAction SilentlyContinue }
'STDERR_CONTENT_END'
try { Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
Remove-Item $tempFile, $tempErrFile -ErrorAction SilentlyContinue
