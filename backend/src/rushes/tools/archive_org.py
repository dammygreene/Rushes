"""Tool 3 of 4: Internet Archive search, biased towards reusable footage.

Two tiers: first ask only for Creative Commons / known public-domain film
collections, and if that comes back thin, widen to any moving image and label the
licence honestly as "check rights". Metadata and outbound links only.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..config import get_settings
from ..models import SearchHit, Source
from ..runtime import get_http
from ._common import as_text, envelope, failure, reason

logger = logging.getLogger(__name__)

# Collections that are reliably reusable; used for the first, stricter tier.
_OPEN_COLLECTIONS = (
    "prelinger",
    "publicmoviesarchive",
    "public_domain_movies",
    "feature_films",
    "opensource_movies",
)
_FIELDS = ("identifier", "title", "description", "creator", "licenseurl", "collection", "runtime")
_SAFE_TERM = re.compile(r"[^0-9A-Za-z' ]+")


async def search_archive_org(query: str, limit: int = 6) -> dict[str, Any]:
    """Find public-domain or Creative Commons films on the Internet Archive.

    Returns metadata plus a details-page link. Nothing is downloaded or
    rehosted.

    Args:
        query: Short keyword query, e.g. "1950s city traffic".
        limit: Maximum number of items to return.
    """
    settings = get_settings()
    terms = _SAFE_TERM.sub(" ", query).strip()
    if not terms:
        return failure("query had no searchable words")

    base = settings.archive_org_base.rstrip("/")
    wanted = max(1, min(int(limit), 20))
    collections = " OR ".join(_OPEN_COLLECTIONS)
    tiers = (
        (
            f"({terms}) AND mediatype:movies AND "
            f"(licenseurl:*creativecommons* OR collection:({collections}))",
            True,
        ),
        (f"({terms}) AND mediatype:movies", False),
    )

    docs: list[dict[str, Any]] = []
    open_tier = True
    note = ""
    for solr_query, is_open in tiers:
        try:
            docs = await _fetch(base, solr_query, wanted)
        except Exception as exc:  # noqa: BLE001 - one dead source must not break the grid
            logger.warning("Internet Archive search failed: %s", reason(exc))
            return failure(f"Internet Archive search failed: {reason(exc)}")
        open_tier = is_open
        if len(docs) >= max(2, wanted // 2):
            break
        if is_open:
            note = "widened past CC-only collections; check rights on the source page"

    hits = [_to_hit(doc, open_tier) for doc in docs if doc.get("identifier")]
    return envelope(hits[:wanted], note=note if hits else "")


async def _fetch(base: str, solr_query: str, rows: int) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = [
        ("q", solr_query),
        ("rows", str(rows)),
        ("page", "1"),
        ("output", "json"),
        ("sort[]", "downloads desc"),
    ]
    params += [("fl[]", field) for field in _FIELDS]
    response = await get_http().get(f"{base}/advancedsearch.php", params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return []
    return list((payload.get("response") or {}).get("docs") or [])


def _to_hit(doc: dict[str, Any], open_tier: bool) -> SearchHit:
    identifier = str(doc["identifier"])
    return SearchHit(
        id=f"ia:{identifier}",
        source=Source.PUBLIC_DOMAIN,
        title=as_text(doc.get("title"), 200) or identifier,
        description=as_text(doc.get("description")),
        thumbnail_url=f"https://archive.org/services/img/{identifier}",
        page_url=f"https://archive.org/details/{identifier}",
        duration_seconds=_runtime_seconds(as_text(doc.get("runtime"), 32)),
        attribution=as_text(doc.get("creator"), 120) or "Internet Archive",
        license=_license_label(doc, open_tier),
    )


def _license_label(doc: dict[str, Any], open_tier: bool) -> str:
    url = as_text(doc.get("licenseurl"), 200).lower()
    if "creativecommons.org/publicdomain" in url:
        return "Public domain (CC0/PDM)"
    if "creativecommons.org" in url:
        return "Creative Commons — see source"
    if open_tier:
        return "Open collection — see source"
    return "Internet Archive — check rights"


def _runtime_seconds(value: str) -> int | None:
    """IA 'runtime' arrives as '1:30', '00:01:30', '90 min' or nothing."""
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) > 1 and all(part.strip().isdigit() for part in parts):
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total or None
    digits = re.match(r"(\d+)\s*min", value.strip(), re.IGNORECASE)
    if digits:
        return int(digits.group(1)) * 60
    return None
