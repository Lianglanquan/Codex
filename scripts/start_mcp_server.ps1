param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080
)

if (-not $env:GITHUB_TOKEN) {
    Write-Error "GITHUB_TOKEN is required."
    exit 1
}

if (-not $env:GITHUB_REPOSITORY) {
    Write-Error "GITHUB_REPOSITORY is required."
    exit 1
}

if (-not $env:MCP_ALLOWED_REPOS) {
    $env:MCP_ALLOWED_REPOS = $env:GITHUB_REPOSITORY
}

python -m uvicorn server:app --app-dir mcp-server --host $HostName --port $Port
