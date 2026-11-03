param([switch]$IncludeDqn)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        py -3 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Install Python and retry.' }
    }
    $extras = if ($IncludeDqn) { '.[dev,dqn]' } else { '.[dev]' }
    & '.\.venv\Scripts\python.exe' -m pip install -e $extras
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Write-Host 'Ready. Run .\Start.ps1'
} finally {
    Pop-Location
}
