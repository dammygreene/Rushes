"""Tool 1 of 4: semantic search over the private archive in ClickHouse.

The query is embedded with Gemini, then the nearest neighbours are fetched by
running a cosineDistance SELECT through the live mcp-clickhouse MCP server. This
is the only source whose clips we host.
"""

from __future__ import annotations

import logging
from typing import Any

from ..clickhouse.queries import rows_to_hits
from ..config import get_settings
from ..gemini import embed_query
from ..runtime import get_mcp_client
from ._common import envelope, failure, reason

logger = logging.getLogger(__name__)

# cosineDistance above this is treated as "not really a match", so a nonsense
# query returns an empty archive section instead of padding the grid.
MAX_DISTANCE = 0.75


async def search_archive(query: str, limit: int = 8) -> dict[str, Any]:
    """Search the editor's own indexed footage by meaning, not keywords.

    Use for every query: this is the private archive of clips the user owns.
    Results are ranked by vector similarity against Gemini captions.

    Args:
        query: A visual description of the wanted shot, in plain English.
        limit: Maximum number of clips to return.

    Returns:
        An envelope with `results`, each carrying a playable clip_url.
    """
    settings = get_settings()
    if not settings.clickhouse_configured:
        return failure("CLICKHOUSE_HOST is not set")
    try:
        embedding = await embed_query(query, settings=settings)
    except Exception as exc:  # noqa: BLE001 - reported per source in the UI
        logger.warning("archive search could not embed the query: %s", reason(exc))
        return failure(f"embedding failed: {reason(exc)}")

    if len(embedding) != settings.embedding_dim:
        return failure(
            f"embedding dimension {len(embedding)} != EMBEDDING_DIM "
            f"{settings.embedding_dim}; re-seed or fix the setting"
        )

    try:
        rows = await get_mcp_client().vector_search(embedding, limit=max(1, int(limit)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ClickHouse MCP search failed: %s", reason(exc))
        return failure(f"ClickHouse MCP unavailable: {reason(exc)}")

    kept = [row for row in rows if _distance_of(row) <= MAX_DISTANCE]
    hits = rows_to_hits(kept)
    for hit in hits:
        hit.clip_url = _absolute(hit.clip_url, settings.public_base_url)
        hit.page_url = hit.clip_url
        hit.thumbnail_url = _absolute(hit.thumbnail_url, settings.public_base_url)
    note = ""
    if rows and not kept:
        note = f"{len(rows)} clips scanned, none within the relevance cut-off"
    return envelope(hits, note=note)


def _distance_of(row: dict[str, Any]) -> float:
    value = row.get("distance")
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _absolute(url: str | None, base: str) -> str | None:
    """Seeded rows may hold a repo-relative path like /clips/rain.mp4."""
    if not url:
        return None
    if url.startswith("/"):
        return base.rstrip("/") + url
    return url
