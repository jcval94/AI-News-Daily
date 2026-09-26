[CmdletBinding()]
param(
    [switch]$Resolve,
    [string]$Config = ".local\local_config.json"
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Falta .venv. Ejecuta bootstrap.ps1 primero." }
$Args = @("-m","pipeline.local","toolchain","--config",$Config,"--json-out",".local\toolchain.latest.json")
if ($Resolve) { $Args += "--resolve" }
Set-Location $RepoRoot
& $Python @Args
exit $LASTEXITCODE
