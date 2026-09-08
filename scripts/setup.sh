#!/usr/bin/env bash
# One-shot developer setup for Rushes (macOS / Linux).
#   bash scripts/setup.sh
#
# Creates the two isolated virtualenvs the project needs, installs the frontend,
# and seeds a .env you can fill in. Safe to re-run.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python="${PYTHON:-python3}"
step() { printf '\033[36m==> %s\033[0m\n' "$1"; }

# --- backend venv: the app, ADK client side (needs mcp<2) --------------------
step 'backend venv'
[ -d "$root/backend/.venv" ] || "$python" -m venv "$root/backend/.venv"
"$root/backend/.venv/bin/pip" install --upgrade pip --quiet
"$root/backend/.venv/bin/pip" install -e "$root/backend[dev]" --quiet
step 'backend tests'
(cd "$root/backend" && "$root/backend/.venv/bin/pytest" -q)

# --- mcp-clickhouse venv: the real MCP server (needs fastmcp>=4, mcp>=2) -----
# Separate on purpose: its dependency floor conflicts with google-adk[mcp].
step 'mcp-clickhouse venv'
[ -d "$root/mcp-server/.venv" ] || "$python" -m venv "$root/mcp-server/.venv"
"$root/mcp-server/.venv/bin/pip" install --upgrade pip --quiet
"$root/mcp-server/.venv/bin/pip" install mcp-clickhouse==0.6.0 --quiet

# --- config -----------------------------------------------------------------
if [ ! -f "$root/.env" ]; then
  cp "$root/.env.example" "$root/.env"
  step 'created .env from .env.example — fill in your keys'
fi
[ -f "$root/frontend/.env.local" ] || cp "$root/frontend/.env.example" "$root/frontend/.env.local"

# --- frontend ---------------------------------------------------------------
step 'frontend dependencies'
(cd "$root/frontend" && npm install --no-fund --no-audit)

cat <<'EOF'

Setup complete. Next:
  1. Edit .env (GOOGLE_API_KEY, CLICKHOUSE_*, optional YOUTUBE/PEXELS keys)
  2. backend/.venv/bin/python -m rushes.pipeline.create_schema
  3. backend/.venv/bin/python -m rushes.pipeline.seed
  4. backend/.venv/bin/rushes-doctor      # verify every dependency
  5. backend/.venv/bin/rushes-api         # then: cd frontend && npm run dev
EOF
