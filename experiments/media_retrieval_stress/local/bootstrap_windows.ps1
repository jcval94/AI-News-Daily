param(
  [string]$LabHome = $env:AI_NEWS_MEDIA_LAB_HOME
)

$ErrorActionPreference = "Stop"

if (-not $LabHome) {
  $LabHome = Join-Path $env:LOCALAPPDATA "AI-News-Daily\media-lab"
}

$dirs = @("cache","jobs","results","clips","logs")
foreach ($dir in $dirs) {
  New-Item -ItemType Directory -Force -Path (Join-Path $LabHome $dir) | Out-Null
}

Write-Host "Media lab home: $LabHome"

$checks = @(
  @{ Name = "python"; Args = @("--version") },
  @{ Name = "ffmpeg"; Args = @("-version") },
  @{ Name = "ffprobe"; Args = @("-version") },
  @{ Name = "yt-dlp"; Args = @("--version") }
)

foreach ($check in $checks) {
  try {
    $first = & $check.Name @($check.Args) 2>&1 | Select-Object -First 1
    Write-Host "[OK] $($check.Name): $first"
  } catch {
    Write-Warning "[MISSING] $($check.Name)"
  }
}

Write-Host ""
Write-Host "Recommended Python packages:"
Write-Host "  pip install jsonschema pydantic requests playwright"
Write-Host "  playwright install chromium"
Write-Host ""
Write-Host "Do not store browser cookie exports inside the repository."
