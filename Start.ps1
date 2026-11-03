param([string]$Workspace = (Join-Path $PSScriptRoot 'workspace'))
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run Setup.ps1 first to create the project virtual environment.'
}
& $python -m aero_ai_studio --workspace $Workspace
exit $LASTEXITCODE
