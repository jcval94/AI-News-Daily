[CmdletBinding()]
param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    $Py = Get-Command py -ErrorAction SilentlyContinue
    if ($Py) {
        & $Py.Source -3.12 -m venv ".venv"
    } else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Python) { throw "Python 3.12+ no encontrado." }
        & $Python.Source -m venv ".venv"
    }
}

if (-not (Test-Path $VenvPython)) { throw "No se pudo crear .venv." }

if (-not $SkipInstall) {
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $VenvPython -m pip install -c requirements.lock .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $VenvPython -m pipeline.local init
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Bootstrap listo."
Write-Host "Siguiente: .\scripts\local\doctor.ps1 -Resolve -Deep"
