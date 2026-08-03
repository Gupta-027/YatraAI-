<#
.SYNOPSIS
  Windows equivalent of the Makefile.  Usage:  ./tasks.ps1 <target>
#>
param(
  [Parameter(Position = 0)]
  [ValidateSet('install', 'install-web', 'lint', 'format', 'typecheck', 'test', 'test-cov',
    'migrate', 'seed', 'pipeline', 'api', 'web', 'experiments', 'rag-eval',
    'verify', 'docker-up', 'docker-down', 'clean', 'help')]
  [string]$Target = 'help',
  [string]$Message = 'migration'
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Bin = Join-Path $Root '.venv\Scripts'
$Py = Join-Path $Bin 'python.exe'

function Invoke-Step([string]$Label, [scriptblock]$Block) {
  Write-Host "==> $Label" -ForegroundColor Cyan
  & $Block
  if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { throw "$Label failed (exit $LASTEXITCODE)" }
}

switch ($Target) {
  'install' {
    if (-not (Test-Path $Py)) { Invoke-Step 'create venv' { python -m venv (Join-Path $Root '.venv') } }
    Invoke-Step 'install python deps' { & $Py -m pip install --upgrade pip setuptools wheel; & $Py -m pip install -e "$Root[dev]" }
  }
  'install-web' { Invoke-Step 'npm install' { Push-Location (Join-Path $Root 'apps\web'); npm install; Pop-Location } }
  'lint' {
    Invoke-Step 'ruff check' { & (Join-Path $Bin 'ruff.exe') check $Root }
    Invoke-Step 'ruff format --check' { & (Join-Path $Bin 'ruff.exe') format --check $Root }
  }
  'format' {
    Invoke-Step 'ruff --fix' { & (Join-Path $Bin 'ruff.exe') check --fix $Root }
    Invoke-Step 'ruff format' { & (Join-Path $Bin 'ruff.exe') format $Root }
  }
  'typecheck' { Invoke-Step 'mypy' { & (Join-Path $Bin 'mypy.exe') (Join-Path $Root 'apps\api\yatraai') } }
  'test' { Invoke-Step 'pytest' { & $Py -m pytest } }
  'test-cov' { Invoke-Step 'pytest+cov' { & $Py -m pytest --cov=apps/api/yatraai --cov-report=term-missing } }
  'migrate' { Invoke-Step 'alembic upgrade head' { Push-Location (Join-Path $Root 'apps\api'); & (Join-Path $Bin 'alembic.exe') upgrade head; Pop-Location } }
  'seed' { Invoke-Step 'seed catalogue' { & $Py -m yatraai.cli seed --knowledge --embeddings } }
  'pipeline' { Invoke-Step 'bronze/silver/gold' { & $Py -m yatraai.cli pipeline --all } }
  'api' { & (Join-Path $Bin 'uvicorn.exe') yatraai.main:app --reload --app-dir (Join-Path $Root 'apps\api') --port 8000 }
  'web' { Push-Location (Join-Path $Root 'apps\web'); npm run dev; Pop-Location }
  'experiments' { Invoke-Step 'experiments' { & $Py (Join-Path $Root 'ml\run_experiments.py') } }
  'rag-eval' { Invoke-Step 'rag eval' { & $Py (Join-Path $Root 'evaluation\run_rag_eval.py') } }
  'verify' { & $PSCommandPath 'lint'; & $PSCommandPath 'test' }
  'docker-up' { Invoke-Step 'docker compose up' { docker compose up -d --build } }
  'docker-down' { Invoke-Step 'docker compose down' { docker compose down -v } }
  'clean' {
    Get-ChildItem -Path $Root -Include __pycache__, .pytest_cache, .ruff_cache, .mypy_cache -Recurse -Directory -ErrorAction SilentlyContinue |
      Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'cleaned'
  }
  default {
    Write-Host @'
YatraAI tasks:
  install       Install Python deps into .venv
  install-web   npm install for apps/web
  lint          ruff check + format check
  format        ruff auto-fix + format
  typecheck     mypy
  test          pytest
  test-cov      pytest with coverage
  migrate       alembic upgrade head
  seed          Load curated catalogue + knowledge + embeddings
  pipeline      Bronze -> Silver -> Gold
  api           Run FastAPI with reload
  web           Run Next.js dev server
  experiments   Reproduce aggregation/planner/ML experiments
  rag-eval      Run the RAG benchmark
  verify        lint + test (CI parity)
  docker-up     docker compose up -d --build
  docker-down   docker compose down -v
'@
  }
}
