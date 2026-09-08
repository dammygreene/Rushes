# rushes (backend)

The Python half of [Rushes](../README.md): an ADK agent that plans a shot
description, fans out to four video sources in parallel, and merges them into one
ranked list. ClickHouse is queried over stdio through the real
[`mcp-clickhouse`](https://github.com/ClickHouse/mcp-clickhouse) MCP server.

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

Two console scripts:

- `rushes-api` — FastAPI on `PORT` (default 8080): `/api/search`, `/api/status`,
  `/healthz`, `/clips/<file>`.
- `rushes-doctor` — preflight that embeds a sentence, starts the MCP server,
  counts your clips over MCP, calls every source and runs one full search.

Pipelines: `python -m rushes.pipeline.create_schema`, then
`python -m rushes.pipeline.seed` (fetch → Gemini caption → embed → `INSERT`).

The MCP server lives in its own virtualenv (`../mcp-server/.venv`, created by
`../scripts/setup.sh`): it needs `mcp>=2` while `google-adk[mcp]` here pins
`mcp<2`. Configuration is read from the repo-root `.env` — see
[`../.env.example`](../.env.example).
