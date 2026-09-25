[CmdletBinding()]
param(
    [switch]$Resolve,
    [switch]$Deep,
    [switch]$OtioSmoke,
    [string]$Config = ".local\local_config.json"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Falta .venv. Ejecuta bootstrap.ps1 primero." }

$Args = @("-m","pipeline.local","doctor","--config",$Config,"--json-out",".local\preflight.latest.json")
if ($Resolve) { $Args += "--resolve" }
if ($Deep) { $Args += "--deep" }
if ($OtioSmoke) { $Args += "--otio-smoke" }

Set-Location $RepoRoot
& $Python @Args
exit $LASTEXITCODE
