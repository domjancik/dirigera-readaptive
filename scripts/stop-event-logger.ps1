$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidPath = Join-Path $root "captures\event-logger.pid"

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Host "No event logger PID file found."
    exit 0
}

$loggerPid = Get-Content -LiteralPath $pidPath
$process = Get-Process -Id $loggerPid -ErrorAction SilentlyContinue

if ($process) {
    Stop-Process -Id $loggerPid
    Write-Host "Stopped DIRIGERA event logger PID $loggerPid."
} else {
    Write-Host "Event logger PID $loggerPid is not running."
}

Remove-Item -LiteralPath $pidPath -Force
