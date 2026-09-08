"""Shared helpers for the four search tools.

Every tool returns the same envelope so the fan-out agent can treat them
identically, and so a single failing source degrades the grid instead of
breaking the search:

    {"ok": bool, "note": str, "count": int, "results": [<SearchHit dict>, ...]}
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any

from ..models import SearchHit

logger = logging.getLogger(__name__)

_ISO_DURATION = re.compile(
    r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def envelope(hits: Sequence[SearchHit], *, ok: bool = True, note: str = "") -> dict[str, Any]:
    return {
        "ok": ok,
        "note": note,
        "count": len(hits),
        "results": [hit.model_dump(mode="json") for hit in hits],
    }


def failure(note: str) -> dict[str, Any]:
    return {"ok": False, "note": note, "count": 0, "results": []}


def reason(exc: BaseException) -> str:
    """Render an exception for a note the UI will show.

    httpx raises several transport errors with an empty `str()` — a dropped
    connection or a DNS blip both arrive that way — which would otherwise
    surface in the grid as a sentence that stops at the colon.
    """
    return str(exc).strip() or type(exc).__name__


def hits_from(payload: dict[str, Any]) -> list[SearchHit]:
    """Rebuild SearchHit objects from a tool envelope."""
    out: list[SearchHit] = []
    for row in payload.get("results") or []:
        try:
            out.append(SearchHit.model_validate(row))
        except Exception as exc:  # noqa: BLE001 - drop malformed rows, keep the rest
            logger.warning("dropping malformed tool result: %s", exc)
    return out


def parse_iso_duration(value: str) -> int | None:
    """YouTube's contentDetails.duration, e.g. 'PT1M30S' -> 90."""
    if not value:
        return None
    match = _ISO_DURATION.fullmatch(value.strip())
    if not match:
        return None
    parts = {key: int(val) for key, val in match.groupdict(default="0").items()}
    total = (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
    return total or None


def first_url(mapping: Any, keys: Sequence[str]) -> str | None:
    """Pick the first present URL from a nested thumbnails-style dict."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        entry = mapping.get(key)
        if isinstance(entry, dict) and entry.get("url"):
            return str(entry["url"])
        if isinstance(entry, str) and entry:
            return entry
    return None


def as_text(value: Any, limit: int = 600) -> str:
    """Internet Archive fields arrive as str, list[str] or missing."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return str(value).strip()[:limit]
