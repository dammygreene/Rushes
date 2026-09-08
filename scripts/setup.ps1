# One-shot developer setup for Rushes (Windows / PowerShell).
#   pwsh -File scripts/setup.ps1
#
# Creates the two isolated virtualenvs the project needs, installs the frontend,
# and seeds a .env you can fill in. Safe to re-run.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

function Step($message) { Write-Host "==> $message" -ForegroundColor Cyan }

# --- backend venv: the app, ADK client side (needs mcp<2) --------------------
Step 'backend venv'
$backendVenv = Join-Path $root 'backend\.venv'
if (-not (Test-Path $backendVenv)) { python -m venv $backendVenv }
$py = Join-Path $backendVenv 'Scripts\python.exe'
& $py -m pip install --upgrade pip --quiet
& $py -m pip install -e "$(Join-Path $root 'backend')[dev]" --quiet
Step 'backend tests'
Push-Location (Join-Path $root 'backend')
try { & $py -m pytest -q } finally { Pop-Location }

# --- mcp-clickhouse venv: the real MCP server (needs fastmcp>=4, mcp>=2) -----
# Separate on purpose: its dependency floor conflicts with google-adk[mcp].
Step 'mcp-clickhouse venv'
$mcpVenv = Join-Path $root 'mcp-server\.venv'
if (-not (Test-Path $mcpVenv)) { python -m venv $mcpVenv }
$mcpPy = Join-Path $mcpVenv 'Scripts\python.exe'
& $mcpPy -m pip install --upgrade pip --quiet
& $mcpPy -m pip install mcp-clickhouse==0.6.0 --quiet

# --- config -----------------------------------------------------------------
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $root '.env.example') $envFile
    Step 'created .env from .env.example — fill in your keys'
}
$frontEnv = Join-Path $root 'frontend\.env.local'
if (-not (Test-Path $frontEnv)) {
    Copy-Item (Join-Path $root 'frontend\.env.example') $frontEnv
}

# --- frontend ---------------------------------------------------------------
Step 'frontend dependencies'
Push-Location (Join-Path $root 'frontend')
try { npm install --no-fund --no-audit } finally { Pop-Location }

Write-Host ''
Write-Host 'Setup complete. Next:' -ForegroundColor Green
Write-Host '  1. Edit .env (GOOGLE_API_KEY, CLICKHOUSE_*, optional YOUTUBE/PEXELS keys)'
Write-Host '  2. backend\.venv\Scripts\python -m rushes.pipeline.create_schema'
Write-Host '  3. backend\.venv\Scripts\python -m rushes.pipeline.seed'
Write-Host '  4. backend\.venv\Scripts\rushes-doctor      # verify every dependency'
Write-Host '  5. backend\.venv\Scripts\rushes-api         # then: cd frontend; npm run dev'
