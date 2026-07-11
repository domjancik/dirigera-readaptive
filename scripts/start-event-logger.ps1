param(
    [string]$Label = "continuous",
    [int]$RotateMb = 25
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidPath = Join-Path $root "captures\event-logger.pid"
New-Item -ItemType Directory -Force -Path (Join-Path $root "captures") | Out-Null

if (Test-Path -LiteralPath $pidPath) {
    $existingPid = Get-Content -LiteralPath $pidPath -ErrorAction SilentlyContinue
    if ($existingPid -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        throw "Event logger already appears to be running as PID $existingPid."
    }
}

$python = "python"
$arguments = @(
    ".\scripts\capture_dirigera_events.py",
    "--label", $Label,
    "--seconds", "0",
    "--rotate-mb", "$RotateMb"
)

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -PassThru

Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding utf8NoBOM
Write-Host "Started DIRIGERA event logger as PID $($process.Id)."
Write-Host "Logs: $root\captures\*-$Label-events.jsonl"
