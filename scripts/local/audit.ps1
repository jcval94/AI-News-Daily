[CmdletBinding()]
param(
    [string]$JsonOut = ".local\harness-audit.latest.json"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Falta .venv. Ejecuta .\scripts\local\bootstrap.ps1 primero."
}

Set-Location $RepoRoot
& $Python -m pipeline.local audit --json-out $JsonOut
exit $LASTEXITCODE
