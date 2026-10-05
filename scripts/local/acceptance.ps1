[CmdletBinding()]
param(
    [ValidateSet("P0","P1")]
    [string]$Tier = "P0",
    [switch]$Resolve,
    [string]$TargetDate = "",
    [string]$Config = ".local\local_config.json"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Falta .venv. Ejecuta bootstrap.ps1 primero."
}

if ($Tier -eq "P1" -and [string]::IsNullOrWhiteSpace($TargetDate)) {
    throw "P1 requiere -TargetDate YYYY-MM-DD para verificar receipts del episodio."
}

$Args = @(
    "-m", "pipeline.local", "accept",
    "--config", $Config,
    "--json-out", ".local\acceptance.latest.json"
)

if ($Resolve) {
    $Args += @("--resolve", "--otio-smoke")
}
if ($Tier -eq "P1") {
    $Args += @("--target-date", $TargetDate)
}

Set-Location $RepoRoot
& $Python @Args
$Code = $LASTEXITCODE

Write-Host ""
Write-Host "Reporte: .local\acceptance.latest.json"
if ($Code -eq 0) {
    Write-Host "Acceptance $Tier completado sin blockers."
} else {
    Write-Host "Acceptance $Tier incompleto o bloqueado. Revisa el JSON antes de continuar."
}
exit $Code
