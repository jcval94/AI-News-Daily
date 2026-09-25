[CmdletBinding()]
param(
    [ValidateSet("P0","P1")][string]$Tier = "P0",
    [switch]$Resolve
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Falta .venv. Ejecuta bootstrap.ps1 primero." }
Set-Location $RepoRoot

$DoctorArgs = @("-Deep")
if ($Resolve) { $DoctorArgs += @("-Resolve","-OtioSmoke") }
& ".\scripts\local\doctor.ps1" @DoctorArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m unittest discover -s tests\local -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Tier -eq "P1") {
    Write-Host "P1 requiere media real: usa local_job.json + run_job.ps1."
}
Write-Host "Acceptance $Tier completado."
exit 0
