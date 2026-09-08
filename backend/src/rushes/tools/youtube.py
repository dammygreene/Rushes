"""Tool 2 of 4: YouTube Data API v3 search (metadata and links only).

Nothing is downloaded or rehosted — each result is a title, a thumbnail served
by YouTube, and an outbound watch URL.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings
from ..models import SearchHit, Source
from ..runtime import get_http
from ._common import envelope, failure, first_url, parse_iso_duration, reason

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_THUMB_KEYS = ("high", "medium", "standard", "default")


async def search_youtube(query: str, limit: int = 6) -> dict[str, Any]:
    """Find public YouTube videos matching a shot description.

    Returns metadata and an outbound link for each video. Never returns a file
    we host, and never downloads the video.

    Args:
        query: Short keyword query, e.g. "rainy neon street night".
        limit: Maximum number of videos to return.
    """
    settings = get_settings()
    if not settings.youtube_api_key:
        return failure("YOUTUBE_API_KEY is not set")

    params: dict[str, Any] = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max(1, min(int(limit), 25)),
        "order": "relevance",
        "safeSearch": "moderate",
        "key": settings.youtube_api_key,
    }
    if settings.youtube_video_license.strip().lower() == "creativecommon":
        params["videoLicense"] = "creativeCommon"

    http = get_http()
    try:
        response = await http.get(SEARCH_URL, params=params)
        if response.status_code == 403:
            return failure(f"YouTube API refused the request: {_api_error(response.json())}")
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - degrade, don't break the search
        logger.warning("YouTube search failed: %s", reason(exc))
        return failure(f"YouTube search failed: {reason(exc)}")

    hits: list[SearchHit] = []
    for item in payload.get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        licensed_cc = "videoLicense" in params
        hits.append(
            SearchHit(
                id=f"yt:{video_id}",
                source=Source.YOUTUBE,
                title=snippet.get("title") or "Untitled video",
                description=(snippet.get("description") or "")[:600],
                thumbnail_url=first_url(snippet.get("thumbnails"), _THUMB_KEYS),
                page_url=f"https://www.youtube.com/watch?v={video_id}",
                attribution=snippet.get("channelTitle"),
                license="Creative Commons (YouTube)" if licensed_cc else "YouTube — see source",
            )
        )

    await _attach_durations(hits, settings.youtube_api_key)
    return envelope(hits)


async def _attach_durations(hits: list[SearchHit], api_key: str) -> None:
    """One extra videos.list call (1 quota unit) to show real durations."""
    if not hits:
        return
    ids = ",".join(hit.id.removeprefix("yt:") for hit in hits)
    try:
        response = await get_http().get(
            VIDEOS_URL,
            params={"part": "contentDetails", "id": ids, "key": api_key},
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - durations are cosmetic
        logger.debug("YouTube duration lookup skipped: %s", reason(exc))
        return
    durations = {
        item.get("id"): parse_iso_duration((item.get("contentDetails") or {}).get("duration", ""))
        for item in payload.get("items", [])
    }
    for hit in hits:
        hit.duration_seconds = durations.get(hit.id.removeprefix("yt:"))


def _api_error(payload: dict[str, Any]) -> str:
    """Pull the machine-readable reason out of a YouTube 403 body."""
    errors = (payload.get("error") or {}).get("errors") or []
    if errors:
        return str(errors[0].get("reason") or errors[0].get("message") or "forbidden")
    return str((payload.get("error") or {}).get("message") or "forbidden")
