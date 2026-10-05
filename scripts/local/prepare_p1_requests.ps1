[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$TargetDate,

    [ValidateSet("human", "assistant", "automation")]
    [string]$RequestedBy = "human",

    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ExamplesRoot = Join-Path $RepoRoot "local_handoff\examples"
$RequestsRoot = Join-Path $RepoRoot "local_handoff\requests"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Falta .venv. Ejecuta .\scripts\local\bootstrap.ps1 primero."
}

$Compact = $TargetDate.Replace("-", "")
$CreatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$Plan = @(
    @{ Order = "01"; Name = "ingest"; Example = "example-ingest.json" },
    @{ Order = "02"; Name = "transcribe"; Example = "example-transcribe.json" },
    @{ Order = "03"; Name = "align"; Example = "example-align.json" },
    @{ Order = "04"; Name = "resolve-sync"; Example = "example-resolve-sync-audio.json" },
    @{ Order = "05"; Name = "timeline-validate"; Example = "example-timeline-validate.json" },
    @{ Order = "06"; Name = "resolve-import"; Example = "example-resolve-import.json" }
)

New-Item -ItemType Directory -Force -Path $RequestsRoot | Out-Null
$Created = @()

try {
    foreach ($Item in $Plan) {
        $Source = Join-Path $ExamplesRoot $Item.Example
        if (-not (Test-Path $Source)) {
            throw "Falta template P1: $($Item.Example)"
        }

        $Raw = Get-Content -Raw -Encoding UTF8 $Source
        $Raw = $Raw.Replace("2026-09-25", $TargetDate).Replace("20260925", $Compact)
        $Job = $Raw | ConvertFrom-Json
        $Job.job_id = "p1-$($Item.Order)-$($Item.Name)-$Compact"
        $Job.target_date = $TargetDate
        $Job.requested_by = $RequestedBy
        $Job.created_at = $CreatedAt
        $Job.mode = "execute"

        $Destination = Join-Path $RequestsRoot ("p1-$($Item.Order)-$($Item.Name)-$Compact.json")
        if ((Test-Path $Destination) -and -not $Force) {
            throw "Ya existe $Destination. Usa -Force sólo si realmente quieres regenerarlo."
        }

        $Json = $Job | ConvertTo-Json -Depth 12
        [System.IO.File]::WriteAllText(
            $Destination,
            $Json + [Environment]::NewLine,
            [System.Text.UTF8Encoding]::new($false)
        )

        & $Python -m pipeline.local validate-job $Destination | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "El request generado no pasó schema: $Destination"
        }
        $Created += $Destination
    }
}
catch {
    foreach ($Path in $Created) {
        Remove-Item -Force -ErrorAction SilentlyContinue $Path
    }
    throw
}

Write-Host ""
Write-Host "P1 request kit generado para $TargetDate:"
foreach ($Path in $Created) {
    Write-Host ("  " + (Resolve-Path -Relative $Path))
}
Write-Host ""
Write-Host "NO se hizo git add/commit, staging ni ejecución."
Write-Host "Siguiente frontera de confianza:"
Write-Host "  git diff -- local_handoff/requests"
Write-Host "  git add local_handoff/requests"
Write-Host "  git commit -m \"local: request P1 $TargetDate\""
Write-Host "Después stagea y ejecuta cada request en orden con stage_request.ps1 / run_staged.ps1."
