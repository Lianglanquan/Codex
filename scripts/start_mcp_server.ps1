param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080
)

function Get-StoredGitHubToken {
    $inputPath = Join-Path $PWD ".git-cred-input.txt"
    try {
        Set-Content -Path $inputPath -Value "protocol=https`nhost=github.com`n" -NoNewline
        $raw = Get-Content $inputPath | git credential-manager get 2>$null
        $passwordLine = $raw | Select-String "^password="
        if ($passwordLine) {
            return ($passwordLine.ToString() -replace "^password=", "")
        }
    } finally {
        Remove-Item $inputPath -ErrorAction SilentlyContinue
    }
    return $null
}

function Get-RepositoryFromGitRemote {
    $remote = git remote get-url origin 2>$null
    if (-not $remote) {
        return $null
    }

    if ($remote -match "github\.com[:/](.+?)(\.git)?$") {
        return $matches[1]
    }

    return $null
}

if (-not $env:GITHUB_TOKEN) {
    $env:GITHUB_TOKEN = Get-StoredGitHubToken
}

if (-not $env:GITHUB_TOKEN) {
    Write-Error "GITHUB_TOKEN is required. Set it manually or sign in to GitHub with Git Credential Manager first."
    exit 1
}

if (-not $env:GITHUB_REPOSITORY) {
    $env:GITHUB_REPOSITORY = Get-RepositoryFromGitRemote
}

if (-not $env:GITHUB_REPOSITORY) {
    Write-Error "GITHUB_REPOSITORY is required. Set it manually or make sure the current git remote points to GitHub."
    exit 1
}

if (-not $env:MCP_ALLOWED_REPOS) {
    $env:MCP_ALLOWED_REPOS = $env:GITHUB_REPOSITORY
}

Write-Host "Starting MCP server for $env:GITHUB_REPOSITORY on http://$HostName`:$Port"

python -m uvicorn server:app --app-dir mcp-server --host $HostName --port $Port
