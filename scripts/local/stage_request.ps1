[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Request
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Falta .venv. Ejecuta bootstrap.ps1 primero." }
Set-Location $RepoRoot
& $Python -m pipeline.local stage-request $Request
exit $LASTEXITCODE
