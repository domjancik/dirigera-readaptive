param(
    [string]$EnvPath = ".env",
    [string]$Label = "capture",
    [int]$Seconds = 30
)

$ErrorActionPreference = "Stop"

$vars = @{}
Get-Content -LiteralPath $EnvPath | ForEach-Object {
    if ($_ -match "^([^=]+)=(.*)$") {
        $vars[$matches[1]] = $matches[2]
    }
}

if (-not $vars.DIRIGERA_HOST -or -not $vars.DIRIGERA_TOKEN) {
    throw "DIRIGERA_HOST and DIRIGERA_TOKEN must be present in $EnvPath."
}

New-Item -ItemType Directory -Force -Path captures | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safeLabel = $Label -replace "[^A-Za-z0-9_.-]", "-"
$outPath = Join-Path "captures" "$stamp-$safeLabel-events.jsonl"
$uri = [Uri]"wss://$($vars.DIRIGERA_HOST):8443/v1"

$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$ws.Options.SetRequestHeader("Authorization", "Bearer $($vars.DIRIGERA_TOKEN)")
$ws.Options.RemoteCertificateValidationCallback = { $true }

Write-Host "Connecting to $uri"
$ws.ConnectAsync($uri, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
Write-Host "Recording raw events to $outPath for $Seconds seconds..."

$deadline = [DateTimeOffset]::UtcNow.AddSeconds($Seconds)
$buffer = New-Object byte[] 65536

try {
    while ([DateTimeOffset]::UtcNow -lt $deadline -and $ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $remaining = $deadline - [DateTimeOffset]::UtcNow
        $cts = [Threading.CancellationTokenSource]::new()
        $cts.CancelAfter([Math]::Max(100, [Math]::Min(1000, [int]$remaining.TotalMilliseconds)))

        try {
            $segment = [ArraySegment[byte]]::new($buffer)
            $result = $ws.ReceiveAsync($segment, $cts.Token).GetAwaiter().GetResult()
        } catch [System.OperationCanceledException] {
            continue
        } finally {
            $cts.Dispose()
        }

        if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
            break
        }

        $chunks = New-Object System.Collections.Generic.List[byte]
        if ($result.Count -gt 0) {
            $chunks.AddRange($buffer[0..($result.Count - 1)])
        }

        while (-not $result.EndOfMessage) {
            $segment = [ArraySegment[byte]]::new($buffer)
            $result = $ws.ReceiveAsync($segment, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
            if ($result.Count -gt 0) {
                $chunks.AddRange($buffer[0..($result.Count - 1)])
            }
        }

        $text = [System.Text.Encoding]::UTF8.GetString($chunks.ToArray())
        $line = [pscustomobject]@{
            timestamp = [DateTimeOffset]::UtcNow.ToString("o")
            message = $text
        } | ConvertTo-Json -Compress -Depth 100
        Add-Content -LiteralPath $outPath -Value $line -Encoding utf8NoBOM
    }
}
finally {
    if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
        $ws.CloseAsync(
            [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
            "done",
            [Threading.CancellationToken]::None
        ).GetAwaiter().GetResult()
    }
    $ws.Dispose()
}

Write-Host "Saved $outPath"
