$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

python -m pip install -r "$Root\requirements.txt"
python "$Root\run_backend.py" --no-reload
