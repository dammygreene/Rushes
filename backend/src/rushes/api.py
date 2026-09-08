"""FastAPI surface: one search endpoint, one status endpoint, one static mount.

The heavy lifting lives in `agent.run_search`. This module is deliberately thin:
transport, auth, CORS, and serving the archive clips we own out of data/clips.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .agent import run_search
from .config import Settings, get_settings
from .models import SearchResponse
from .runtime import get_mcp_client, shutdown

logger = logging.getLogger(__name__)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Plain-English shot description.")
    limit: int | None = Field(default=None, ge=1, le=60)


def require_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Optional bearer auth. Unset API_TOKEN leaves the endpoint open."""
    token = get_settings().api_token
    if not token:
        return
    supplied = (authorization or "").strip()
    if not secrets.compare_digest(supplied, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    logging.basicConfig(
        level=cfg.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg.clips_dir.mkdir(parents=True, exist_ok=True)

    # Start the MCP server up front so the first search is not paying for it.
    if cfg.clickhouse_configured:
        try:
            info = await get_mcp_client().start()
            logger.info("mcp-clickhouse ready: %s", info)
        except Exception as exc:  # noqa: BLE001 - the other three sources still work
            logger.warning("mcp-clickhouse did not start: %s", exc)
    else:
        logger.warning("CLICKHOUSE_HOST is not set; the archive source will report as offline")
    try:
        yield
    finally:
        await shutdown()


app = FastAPI(
    title="Rushes",
    version=__version__,
    summary="Natural-language search across your own footage and the public web.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# The only media we ever host: clips the editor owns, seeded into data/clips.
get_settings().clips_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/clips",
    StaticFiles(directory=str(get_settings().clips_dir), check_dir=False),
    name="clips",
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness only — no network calls, safe for a container probe."""
    return {"status": "ok", "version": __version__}


@app.post("/api/search", response_model=SearchResponse, dependencies=[Depends(require_token)])
async def search(request: SearchRequest) -> SearchResponse:
    """Plan the query with Gemini, fan out to four sources, return one ranked list."""
    response = await run_search(request.query, limit=request.limit)
    logger.info(
        "search %r -> %d results in %.0fms (%s)",
        request.query,
        len(response.results),
        response.total_ms,
        ", ".join(f"{r.source.value}:{r.count}" for r in response.sources),
    )
    return response


@app.get("/api/status", dependencies=[Depends(require_token)])
async def status() -> dict[str, Any]:
    """What is actually wired up. Used by the UI banner and by `rushes-doctor`."""
    cfg = get_settings()
    return {
        "version": __version__,
        "clickhouse": await _clickhouse_status(cfg),
        "gemini": {
            "configured": cfg.gemini_configured,
            "vertex_ai": cfg.google_genai_use_vertexai,
            "model": cfg.gemini_model,
            "embed_model": cfg.gemini_embed_model,
            "embedding_dim": cfg.embedding_dim,
        },
        "sources": {
            "archive": cfg.clickhouse_configured,
            "youtube": bool(cfg.youtube_api_key),
            "public_domain": True,
            "stock": bool(cfg.pexels_api_key),
        },
        "ranking": {"strategy": cfg.ranking_strategy, "result_limit": cfg.result_limit},
    }


async def _clickhouse_status(cfg: Settings) -> dict[str, Any]:
    """Proves the MCP path end to end: handshake info plus a real COUNT(*)."""
    out: dict[str, Any] = {
        "configured": cfg.clickhouse_configured,
        "table": cfg.qualified_table,
        "via": "mcp-clickhouse (stdio)",
    }
    if not cfg.clickhouse_configured:
        out["error"] = "CLICKHOUSE_HOST is not set"
        return out
    client = get_mcp_client()
    try:
        out["server"] = await client.start()
        out["clips"] = await client.count_clips()
    except Exception as exc:  # noqa: BLE001 - status must never 500
        out["error"] = str(exc)[:300]
    out["mcp_running"] = client.running
    return out


def main() -> None:
    """`rushes-api` entry point."""
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "rushes.api:app",
        host="0.0.0.0",  # noqa: S104 - containers need this; put auth in front in production
        port=cfg.port,
        log_level=cfg.log_level.lower(),
    )
