$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $Pwsh) {
    $Pwsh = (Get-Command powershell -ErrorAction Stop).Source
}

Start-Process -FilePath $Pwsh -WorkingDirectory $Root -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "$Root\start-backend.ps1"
)

Start-Process -FilePath $Pwsh -WorkingDirectory $Root -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "$Root\start-frontend.ps1"
)

Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "Frontend: http://127.0.0.1:5173"
