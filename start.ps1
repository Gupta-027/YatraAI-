<#
.SYNOPSIS
  Start YatraAI locally. Checks prerequisites, seeds on first run, then serves.

.EXAMPLE
  .\start.ps1
  .\start.ps1 -Port 8080
#>
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Py = Join-Path $Root '.venv\Scripts\python.exe'

function Say($msg, $colour = 'Cyan') { Write-Host "==> $msg" -ForegroundColor $colour }

# ---- 1. virtualenv --------------------------------------------------------
if (-not (Test-Path $Py)) {
  Say 'Creating virtualenv and installing dependencies (one-off, ~2 min)...'
  python -m venv (Join-Path $Root '.venv')
  & $Py -m pip install --quiet --upgrade pip setuptools wheel
  & $Py -m pip install --quiet -e "$Root[dev]"
}

# ---- 2. database ----------------------------------------------------------
$dbFile = Join-Path $Root 'yatraai.sqlite3'
if (-not (Test-Path $dbFile) -or (Get-Item $dbFile).Length -lt 100000) {
  Say 'Creating and seeding the database (one-off)...'
  & $Py -m yatraai.cli migrate
  & $Py -m yatraai.cli seed --knowledge --embeddings
} else {
  Say 'Database found.' 'DarkGray'
}

# ---- 3. free port ---------------------------------------------------------
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) {
  Write-Host "Port $Port is already in use by PID $($busy.OwningProcess)." -ForegroundColor Yellow
  Write-Host "Either stop it, or run:  .\start.ps1 -Port 8080" -ForegroundColor Yellow
  exit 1
}

# ---- 4. serve -------------------------------------------------------------
$url = "http://127.0.0.1:$Port/"
Say "Starting YatraAI on $url"
Write-Host ''
Write-Host "   Open this in your browser:  $url" -ForegroundColor Green
Write-Host '   (works offline - no CDN assets)' -ForegroundColor DarkGray
Write-Host "   Machine-readable spec:      http://127.0.0.1:$Port/openapi.json" -ForegroundColor DarkGray
Write-Host ''
Write-Host '   Press Ctrl+C to stop.' -ForegroundColor DarkGray
Write-Host ''

Start-Job -ScriptBlock {
  param($u)
  Start-Sleep -Seconds 4
  try { Start-Process $u } catch { }
} -ArgumentList $url | Out-Null

& $Py -m uvicorn yatraai.main:app --app-dir (Join-Path $Root 'apps\api') `
  --host 127.0.0.1 --port $Port
