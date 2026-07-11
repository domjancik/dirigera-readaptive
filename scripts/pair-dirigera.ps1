param(
    [Parameter(Mandatory = $true)]
    [string]$HostAddress,

    [string]$Name = $env:COMPUTERNAME,

    [int]$ButtonWaitSeconds = 30,

    [switch]$PrintToken
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Web

function New-CodeVerifier {
    $alphabet = "_-~.abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes = New-Object byte[] 128
    $rng.GetBytes($bytes)
    -join ($bytes | ForEach-Object { $alphabet[[int]$_ % $alphabet.Length] })
}

function Get-CodeChallenge([string]$Verifier) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Verifier)
    $hash = $sha.ComputeHash($bytes)
    [Convert]::ToBase64String($hash).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

$codeVerifier = New-CodeVerifier
$codeChallenge = Get-CodeChallenge $codeVerifier
$baseUrl = "https://${HostAddress}:8443/v1"

$query = [System.Web.HttpUtility]::ParseQueryString("")
$query["audience"] = "homesmart.local"
$query["response_type"] = "code"
$query["code_challenge"] = $codeChallenge
$query["code_challenge_method"] = "S256"
$authorizeUrl = "$baseUrl/oauth/authorize?$($query.ToString())"

Write-Host "Requesting authorization from $HostAddress..."
$auth = Invoke-RestMethod -Uri $authorizeUrl -Method Get -SkipCertificateCheck -TimeoutSec 10
if (-not $auth.code) {
    throw "Hub did not return an authorization code."
}

Write-Host ""
Write-Host "Press the DIRIGERA action button now. Waiting $ButtonWaitSeconds seconds..."
Start-Sleep -Seconds $ButtonWaitSeconds

$body = @{
    code = $auth.code
    name = $Name
    grant_type = "authorization_code"
    code_verifier = $codeVerifier
}

$tokenResponse = Invoke-RestMethod `
    -Uri "$baseUrl/oauth/token" `
    -Method Post `
    -ContentType "application/x-www-form-urlencoded" `
    -Body $body `
    -SkipCertificateCheck `
    -TimeoutSec 10

if (-not $tokenResponse.access_token) {
    throw "Hub did not return an access token."
}

$envPath = Join-Path (Get-Location) ".env"
$envContent = @(
    "DIRIGERA_HOST=$HostAddress"
    "DIRIGERA_TOKEN=$($tokenResponse.access_token)"
) -join [Environment]::NewLine

Set-Content -LiteralPath $envPath -Value $envContent -Encoding utf8NoBOM
Write-Host "Token saved to $envPath"

if ($PrintToken) {
    Write-Host $tokenResponse.access_token
}
