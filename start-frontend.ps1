$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path "$Root\frontend\node_modules")) {
    npm --prefix "$Root\frontend" install
}

npm --prefix "$Root\frontend" run dev
