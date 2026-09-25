[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Job,
    [switch]$Execute,
    [string]$Config = ".local\local_config.json"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Falta .venv. Ejecuta bootstrap.ps1 primero." }

$Args = @("-m","pipeline.local","run-job",$Job,"--config",$Config)
if ($Execute) { $Args += "--execute" }
Set-Location $RepoRoot
& $Python @Args
exit $LASTEXITCODE
