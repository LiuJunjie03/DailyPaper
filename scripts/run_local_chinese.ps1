$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

Set-Location -LiteralPath $projectRoot
# Unattended runs use public journal pages plus previously exported files.
# Run collect_chinese_papers.py --portals manually while an authenticated browser is open.
& $python "scripts\collect_chinese_papers.py"
if ($LASTEXITCODE -ne 0) {
    throw "Chinese literature collection failed with exit code $LASTEXITCODE"
}
