"""Seed the archive: fetch -> caption -> embed -> INSERT.

    python -m rushes.pipeline.seed                  # 10 queries x 2 clips
    python -m rushes.pipeline.seed -q "night rain" --per-query 3
    python -m rushes.pipeline.seed --dry-run        # no writes, prints the plan

Re-running is safe: clips already present in data/clips are not re-downloaded,
captions come from the cache, and rows whose clip_url is already in ClickHouse
are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from typing import Any

from ..clickhouse.direct import count_clips, ensure_table, existing_clip_urls, insert_clips
from ..config import Settings, get_settings
from ..gemini import embed_texts
from ..models import ClipCaption
from .captioner import caption_clip, caption_text
from .fetch_clips import DEFAULT_QUERIES, FetchedClip, fetch_clips

logger = logging.getLogger(__name__)

# Stable namespace so a clip's UUID is a function of its source id, not of when
# the seed ran.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/rushes-app/clips")

_CAPTION_CONCURRENCY = 3


async def seed(
    *,
    queries: tuple[str, ...] | list[str] = DEFAULT_QUERIES,
    per_query: int = 2,
    limit: int | None = None,
    dry_run: bool = False,
    recaption: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or get_settings()
    if not dry_run:
        ensure_table(cfg)

    clips = await fetch_clips(queries, per_query, settings=cfg)
    if limit:
        clips = clips[:limit]
    if not clips:
        return {"fetched": 0, "inserted": 0, "skipped": 0, "total": 0}

    known = set() if dry_run else existing_clip_urls(cfg)
    fresh = [clip for clip in clips if clip.clip_url not in known]
    logger.info("%d clips fetched, %d new", len(clips), len(fresh))
    if not fresh:
        total = 0 if dry_run else count_clips(cfg)
        return {"fetched": len(clips), "inserted": 0, "skipped": len(clips), "total": total}

    captions = await _caption_all(fresh, cfg, recaption=recaption)
    texts = [caption_text(caption) for caption in captions]
    embeddings = await embed_texts(texts, task_type="RETRIEVAL_DOCUMENT", settings=cfg)
    if len(embeddings) != len(fresh):
        raise RuntimeError(f"got {len(embeddings)} embeddings for {len(fresh)} clips")
    width = len(embeddings[0]) if embeddings else 0
    if width != cfg.embedding_dim:
        raise RuntimeError(
            f"embeddings are {width}-d but EMBEDDING_DIM is {cfg.embedding_dim}; "
            "align the setting with the model before seeding"
        )

    rows = [
        _row(clip, caption, embedding)
        for clip, caption, embedding in zip(fresh, captions, embeddings)
    ]
    if dry_run:
        for row in rows:
            print(f"  {row['title'][:56]:<56} {len(row['embedding'])}d  {row['clip_url']}")
        return {
            "fetched": len(clips),
            "inserted": 0,
            "skipped": len(clips) - len(rows),
            "total": 0,
            "dry_run": True,
        }

    inserted = insert_clips(rows, cfg)
    return {
        "fetched": len(clips),
        "inserted": inserted,
        "skipped": len(clips) - len(rows),
        "total": count_clips(cfg),
    }


async def _caption_all(
    clips: list[FetchedClip], cfg: Settings, *, recaption: bool
) -> list[ClipCaption]:
    """Caption a few clips at a time: Gemini is the slow part of seeding."""
    gate = asyncio.Semaphore(_CAPTION_CONCURRENCY)

    async def one(clip: FetchedClip) -> ClipCaption:
        async with gate:
            caption = await caption_clip(clip, settings=cfg, use_cache=not recaption)
            logger.info("captioned %s: %s", clip.key, caption.title)
            return caption

    return list(await asyncio.gather(*(one(clip) for clip in clips)))


def _row(clip: FetchedClip, caption: ClipCaption, embedding: list[float]) -> dict[str, Any]:
    tags = sorted({*(tag.lower().strip() for tag in caption.tags if tag.strip()), *clip.tags})
    return {
        "clip_id": uuid.uuid5(_NAMESPACE, clip.key),
        "title": caption.title or clip.query.title(),
        "description": caption.description,
        "tags": tags,
        "embedding": embedding,
        "duration_seconds": clip.duration_seconds,
        # Pexels' own still: we host the video, not their thumbnail.
        "thumbnail_url": clip.thumbnail_url,
        "clip_url": clip.clip_url,
        "source": "archive",
        "license": (
            f"Pexels License — {clip.author} (sample archive)"
            if clip.key.startswith("pexels:")
            else "owned"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Rushes archive in ClickHouse.")
    parser.add_argument("-q", "--query", action="append", dest="queries", metavar="TEXT")
    parser.add_argument("--per-query", type=int, default=2)
    parser.add_argument("--limit", type=int, default=None, help="cap the total clips seeded")
    parser.add_argument("--dry-run", action="store_true", help="caption and embed, do not insert")
    parser.add_argument("--recaption", action="store_true", help="ignore the caption cache")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level="DEBUG" if args.verbose else "INFO",
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = get_settings()
    if not args.dry_run and not cfg.clickhouse_configured:
        print("CLICKHOUSE_HOST is not set. Copy .env.example to .env first.")
        return 1
    if not cfg.pexels_api_key:
        print("PEXELS_API_KEY is not set; it is what builds the sample archive.")
        return 1

    summary = asyncio.run(
        seed(
            queries=tuple(args.queries) if args.queries else DEFAULT_QUERIES,
            per_query=args.per_query,
            limit=args.limit,
            dry_run=args.dry_run,
            recaption=args.recaption,
            settings=cfg,
        )
    )
    print(
        f"\nfetched={summary['fetched']} inserted={summary['inserted']} "
        f"skipped={summary['skipped']} total_in_clickhouse={summary['total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
