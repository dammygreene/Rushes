"""Fetch a starter archive from Pexels into data/clips.

These downloaded files stand in for the editor's own rushes: they are the one
source Rushes hosts and serves, so the demo has something to actually play. They
come from Pexels under the Pexels License; swap `data/clips` for real footage and
re-run the seed and nothing else changes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings, get_settings
from ..runtime import USER_AGENT

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.pexels.com/videos/search"

# Ten shots that cover the kinds of queries a demo asks for.
DEFAULT_QUERIES = (
    "rainy neon city street at night",
    "aerial coastline at sunrise",
    "crowded market street daytime",
    "empty desert highway wide shot",
    "foggy forest morning light",
    "city traffic at dusk",
    "waves crashing on rocks",
    "snowy mountain ridge",
    "child running through a park",
    "hands typing on a laptop close up",
)

_MAX_WIDTH = 1280  # SD/HD-lite keeps captioning fast and files small enough to inline


@dataclass
class FetchedClip:
    """One downloaded file plus the metadata we keep about it."""

    key: str
    path: Path
    query: str
    page_url: str
    thumbnail_url: str
    duration_seconds: int
    author: str
    tags: list[str] = field(default_factory=list)

    @property
    def clip_url(self) -> str:
        """Stored relative; resolved against PUBLIC_BASE_URL when serving."""
        return f"/clips/{self.path.name}"


async def fetch_clips(
    queries: tuple[str, ...] | list[str] = DEFAULT_QUERIES,
    per_query: int = 2,
    *,
    settings: Settings | None = None,
) -> list[FetchedClip]:
    cfg = settings or get_settings()
    if not cfg.pexels_api_key:
        raise RuntimeError("PEXELS_API_KEY is not set; needed to build the sample archive")
    cfg.clips_dir.mkdir(parents=True, exist_ok=True)

    out: list[FetchedClip] = []
    seen: set[str] = set()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as http:
        for query in queries:
            try:
                videos = await _search(http, query, per_query, cfg)
            except Exception as exc:  # noqa: BLE001 - keep seeding the other queries
                logger.warning("Pexels search failed for %r: %s", query, exc)
                continue
            for video in videos:
                key = f"pexels:{video.get('id')}"
                if key in seen:
                    continue
                clip = await _download(http, video, query, cfg)
                if clip is not None:
                    seen.add(key)
                    out.append(clip)
                if len([c for c in out if c.query == query]) >= per_query:
                    break
    logger.info("fetched %d clips into %s", len(out), cfg.clips_dir)
    return out


async def _search(
    http: httpx.AsyncClient, query: str, per_query: int, cfg: Settings
) -> list[dict[str, Any]]:
    response = await http.get(
        SEARCH_URL,
        params={
            "query": query,
            "per_page": max(2, per_query * 2),
            "orientation": "landscape",
            "size": "medium",
        },
        headers={"Authorization": cfg.pexels_api_key},
    )
    response.raise_for_status()
    return list(response.json().get("videos") or [])


async def _download(
    http: httpx.AsyncClient, video: dict[str, Any], query: str, cfg: Settings
) -> FetchedClip | None:
    video_id = video.get("id")
    source = _pick_file(video)
    if not video_id or not source:
        return None
    path = cfg.clips_dir / f"pexels-{video_id}.mp4"
    if not path.exists():
        try:
            async with http.stream("GET", source) as stream:
                stream.raise_for_status()
                with path.open("wb") as handle:
                    async for chunk in stream.aiter_bytes(1 << 16):
                        handle.write(chunk)
        except Exception as exc:  # noqa: BLE001 - a partial file must not be seeded
            logger.warning("download failed for %s: %s", source, exc)
            path.unlink(missing_ok=True)
            return None
        logger.info("downloaded %s (%.1f MB)", path.name, path.stat().st_size / 1e6)
    else:
        logger.debug("already downloaded: %s", path.name)

    user = video.get("user") or {}
    return FetchedClip(
        key=f"pexels:{video_id}",
        path=path,
        query=query,
        page_url=str(video.get("url") or f"https://www.pexels.com/video/{video_id}/"),
        thumbnail_url=str(video.get("image") or ""),
        duration_seconds=int(video.get("duration") or 0),
        author=str(user.get("name") or "Pexels"),
        tags=[part for part in query.split() if len(part) > 3],
    )


def _pick_file(video: dict[str, Any]) -> str | None:
    """Smallest mp4 at or under _MAX_WIDTH, else the smallest available."""
    candidates = [
        item
        for item in (video.get("video_files") or [])
        if item.get("link") and str(item.get("file_type", "")).endswith("mp4")
    ]
    if not candidates:
        return None
    small = [item for item in candidates if int(item.get("width") or 0) <= _MAX_WIDTH]
    pool = small or candidates
    pool.sort(key=lambda item: int(item.get("width") or 0))
    return str(pool[0]["link"])


async def _main() -> int:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    clips = await fetch_clips()
    for clip in clips:
        print(f"{clip.key:>18}  {clip.duration_seconds:>3}s  {clip.path.name}")
    return 0 if clips else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
