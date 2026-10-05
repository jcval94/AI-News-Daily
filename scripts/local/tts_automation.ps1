[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$NoSync
)

$ErrorActionPreference = "Stop"
$TaskName = "AI-News-Daily TTS Library"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if ($Register) {
    $PowerShell = (Get-Command powershell.exe).Source
    $Action = New-ScheduledTaskAction `
        -Execute $PowerShell `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" `
        -WorkingDirectory $RepoRoot
    $Trigger = New-ScheduledTaskTrigger -Daily -At "09:00"
    $Settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew
    $Principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Actualiza main y genera la biblioteca TTS local de episodios aprobados." `
        -Force | Out-Null
    Get-ScheduledTask -TaskName $TaskName
    exit 0
}

$LogDir = Join-Path $RepoRoot ".local\tts\automation"
New-Item -ItemType Directory -Force $LogDir | Out-Null
Start-Transcript -Path (Join-Path $LogDir "latest.log") -Force | Out-Null
try {
    Set-Location $RepoRoot
    $Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) { throw "Falta .venv en $RepoRoot" }

    if (-not $NoSync) {
        $Dirty = & git status --porcelain
        if ($LASTEXITCODE -ne 0) { throw "No se pudo comprobar el estado de Git." }
        if ($Dirty) { throw "El checkout TTS tiene cambios locales; no se actualizó ni renderizó." }

        & git fetch origin main
        if ($LASTEXITCODE -ne 0) { throw "git fetch origin main falló." }
        & git switch main
        if ($LASTEXITCODE -ne 0) { throw "git switch main falló." }
        & git pull --ff-only origin main
        if ($LASTEXITCODE -ne 0) { throw "git pull --ff-only origin main falló." }
    }

    & $Python -m pipeline.local tts render-pending
    if ($LASTEXITCODE -ne 0) { throw "render-pending terminó con código $LASTEXITCODE." }
    Write-Host "Biblioteca: $RepoRoot\.local\tts\library\index.html"
}
finally {
    Stop-Transcript | Out-Null
}
