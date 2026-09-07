<#
    dev.ps1 — start the whole stack locally with one command.

      ./dev.ps1                 # backend :8000, frontend :3000
      ./dev.ps1 -ApiPort 8001   # if :8000 is blocked on your machine

    Needs: backend/.env with a DATABASE_URL, `pip install -r backend/requirements.txt`,
    and `npm install` in frontend/. Ctrl+C stops both.
#>
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Test-Path "$root/backend/.env")) {
    Write-Error "backend/.env is missing. Copy backend/.env.example and set DATABASE_URL."
}

$env:API_PROXY_TARGET = "http://localhost:$ApiPort"
$env:PYTHONUTF8 = "1"

Write-Host "backend  -> http://localhost:$ApiPort" -ForegroundColor Yellow
Write-Host "frontend -> http://localhost:$WebPort" -ForegroundColor Cyan
Write-Host "Ctrl+C to stop both.`n"

# next's npm wrapper trips on paths containing '&'/spaces, so call the bin directly.
$nextBin = "$root/frontend/node_modules/next/dist/bin/next"

$api = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root/backend" `
    -FilePath "python" -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "$ApiPort"

$web = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root/frontend" `
    -FilePath "node" -ArgumentList "`"$nextBin`"", "dev", "-p", "$WebPort"

try {
    Wait-Process -Id $api.Id, $web.Id
}
finally {
    foreach ($p in @($api, $web)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    Write-Host "`nStopped." -ForegroundColor DarkGray
}
