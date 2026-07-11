param(
    [string]$PiHost = "raspberrypi.local",
    [string]$PiUser = "dirigera",
    [string]$EnvPath = ".env",
    [string]$TokenPath = "/etc/dirigera-readaptive/token"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw "Missing env file: $EnvPath"
}

$tokenLine = Get-Content -LiteralPath $EnvPath |
    Where-Object { $_ -match "^DIRIGERA_TOKEN=" } |
    Select-Object -First 1

if (-not $tokenLine) {
    throw "DIRIGERA_TOKEN was not found in $EnvPath"
}

$token = $tokenLine -replace "^DIRIGERA_TOKEN=", ""
if (-not $token) {
    throw "DIRIGERA_TOKEN in $EnvPath is empty"
}

$target = "$PiUser@$PiHost"
ssh $target "sudo install -d -m 750 -o $PiUser -g $PiUser /etc/dirigera-readaptive"
$token | ssh $target "umask 177; cat > /tmp/dirigera.token; sudo install -m 600 -o $PiUser -g $PiUser /tmp/dirigera.token $TokenPath; rm /tmp/dirigera.token"

Write-Host "Seeded DIRIGERA token at $TokenPath on $target"
