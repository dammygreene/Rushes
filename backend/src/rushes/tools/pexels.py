"""Tool 4 of 4: Pexels Video search for licensable stock shots.

Thumbnail plus outbound link, same as the other public sources. The Pexels
license is permissive, but we still do not rehost their files — the grid links
back to the Pexels page so the photographer gets the visit.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings
from ..models import SearchHit, Source
from ..runtime import get_http
from ._common import envelope, failure, reason

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.pexels.com/videos/search"


async def search_pexels(query: str, limit: int = 6) -> dict[str, Any]:
    """Find licensable stock footage on Pexels.

    Good for clean, modern establishing shots and b-roll.

    Args:
        query: Short keyword query, e.g. "aerial coastline sunrise".
        limit: Maximum number of clips to return.
    """
    settings = get_settings()
    if not settings.pexels_api_key:
        return failure("PEXELS_API_KEY is not set")

    try:
        response = await get_http().get(
            SEARCH_URL,
            params={
                "query": query,
                "per_page": max(1, min(int(limit), 20)),
                "orientation": "landscape",
            },
            headers={"Authorization": settings.pexels_api_key},
        )
        if response.status_code in (401, 403):
            return failure("Pexels rejected the API key")
        if response.status_code == 429:
            return failure("Pexels rate limit reached")
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - degrade, don't break the search
        logger.warning("Pexels search failed: %s", reason(exc))
        return failure(f"Pexels search failed: {reason(exc)}")

    hits: list[SearchHit] = []
    for video in payload.get("videos") or []:
        video_id = video.get("id")
        if not video_id:
            continue
        user = video.get("user") or {}
        hits.append(
            SearchHit(
                id=f"px:{video_id}",
                source=Source.STOCK,
                title=_title(video),
                description=(video.get("alt") or "").strip()[:600],
                thumbnail_url=video.get("image"),
                page_url=video.get("url") or f"https://www.pexels.com/video/{video_id}/",
                duration_seconds=_as_int(video.get("duration")),
                attribution=(user.get("name") or "Pexels").strip(),
                license="Pexels License (free to use, credit appreciated)",
            )
        )
    return envelope(hits)


def _title(video: dict[str, Any]) -> str:
    """Pexels videos have no title field; `alt` is a caption, the URL a slug."""
    alt = (video.get("alt") or "").strip()
    if alt:
        return alt[:200]
    slug = str(video.get("url") or "").rstrip("/").rsplit("/", 1)[-1]
    words = [part for part in slug.replace("-", " ").split() if not part.isdigit()]
    return " ".join(words).title() or f"Pexels clip {video.get('id')}"


def _as_int(value: Any) -> int | None:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return seconds or None
