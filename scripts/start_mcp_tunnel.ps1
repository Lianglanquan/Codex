param(
    [string]$LocalUrl = "http://127.0.0.1:8080",
    [string]$LogDir = "C:\Users\Fool\cloudflared-logs"
)

$cloudflared = Join-Path $env:USERPROFILE "AppData\Local\cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflared)) {
    Write-Error "cloudflared.exe not found at $cloudflared"
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$outLog = Join-Path $LogDir "cloudflared.log"
$errLog = Join-Path $LogDir "cloudflared.err.log"

Write-Host "Starting cloudflared tunnel for $LocalUrl"
Write-Host "Logs: $outLog"

& $cloudflared tunnel --no-autoupdate --logfile $outLog --url $LocalUrl 2>> $errLog
