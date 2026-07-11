param(
    [string]$PiHost = "192.168.1.250",
    [string]$PiUser = "piadmin",
    [string]$RemoteBin = ""
)

$ErrorActionPreference = "Stop"

if (-not $RemoteBin) {
    $RemoteBin = "/home/$PiUser/bin"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$localPiScripts = Join-Path $scriptRoot "pi"
if (-not (Test-Path -LiteralPath $localPiScripts)) {
    throw "Missing local Pi scripts directory: $localPiScripts"
}

$target = "$PiUser@$PiHost"
$remoteTmp = "/tmp/dirigera-status-scripts"

ssh $target "rm -rf $remoteTmp && mkdir -p $remoteTmp"
scp (Join-Path $localPiScripts "dirigera-*") "$target`:$remoteTmp/"
ssh $target "mkdir -p $RemoteBin && install -m 755 $remoteTmp/dirigera-* $RemoteBin/ && rm -rf $remoteTmp"

Write-Host "Installed DIRIGERA status scripts to $target`:$RemoteBin"
Write-Host "Try: ssh $target '$RemoteBin/dirigera-status'"
