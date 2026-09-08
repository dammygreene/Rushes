"""Gemini watches each clip and writes its catalogue entry.

This is the step that makes the archive searchable by meaning: a structured
caption per clip, embedded into the vector column. Captions are cached under
data/captions so re-seeding costs nothing, and every failure falls back to a
caption built from the clip's own metadata rather than dropping the clip.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from google.genai import types

from ..config import REPO_ROOT, Settings, get_settings
from ..gemini import generate_json, get_client
from ..models import ClipCaption
from .fetch_clips import FetchedClip

logger = logging.getLogger(__name__)

CACHE_DIR = REPO_ROOT / "data" / "captions"

# Videos under this go inline as bytes, which also works on Vertex AI. Larger
# files go through the Files API (Gemini Developer API only).
_INLINE_LIMIT = 18 * 1024 * 1024
_POLL_SECONDS = 2.0
_POLL_ATTEMPTS = 30

_PROMPT = """You are cataloguing a shot for a film editor's archive.

Watch the clip and fill in the schema:

- title: max 8 words, no punctuation at the end, naming the subject and setting.
- description: one or two sentences on what is visible — subject, setting, time
  of day, light, weather, and camera movement if it is obvious.
- tags: 5-10 lower-case terms an editor would search for. Include the setting,
  the weather or light, the main objects, and the shot size.
- mood: two or three words, e.g. "calm, spacious".
- setting: the place, e.g. "coastal cliff road".
- objects: the concrete things in frame.

Describe only what you can see. No plot, no speculation, no camera brand talk."""


def cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key.replace(':', '-')}.json"


def load_cached(key: str) -> ClipCaption | None:
    path = cache_path(key)
    if not path.exists():
        return None
    try:
        return ClipCaption.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a stale cache file is not fatal
        logger.debug("ignoring unreadable caption cache %s: %s", path.name, exc)
        return None


def save_cached(key: str, caption: ClipCaption) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(key).write_text(caption.model_dump_json(indent=2), encoding="utf-8")


def fallback_caption(clip: FetchedClip) -> ClipCaption:
    """No Gemini? Describe the clip from the query that found it."""
    return ClipCaption(
        title=clip.query.title(),
        description=f"Stock shot matching “{clip.query}”, {clip.duration_seconds}s.",
        tags=sorted({*clip.tags, *[w for w in clip.query.lower().split() if len(w) > 3]}),
        setting=clip.query,
    )


def caption_text(caption: ClipCaption) -> str:
    """The single string that gets embedded. Order matters less than coverage."""
    parts = [
        caption.title.strip(),
        caption.description.strip(),
        f"Setting: {caption.setting}." if caption.setting else "",
        f"Mood: {caption.mood}." if caption.mood else "",
        f"Objects: {', '.join(caption.objects)}." if caption.objects else "",
        f"Tags: {', '.join(caption.tags)}." if caption.tags else "",
    ]
    return " ".join(part for part in parts if part)


async def caption_clip(
    clip: FetchedClip,
    *,
    settings: Settings | None = None,
    use_cache: bool = True,
) -> ClipCaption:
    cfg = settings or get_settings()
    if use_cache:
        cached = load_cached(clip.key)
        if cached is not None:
            logger.debug("caption cache hit for %s", clip.key)
            return cached
    if not cfg.gemini_configured:
        return fallback_caption(clip)
    try:
        part = await _video_part(clip.path, cfg)
        caption = await generate_json(
            [part, _PROMPT],
            ClipCaption,
            settings=cfg,
            temperature=0.3,
        )
        result = (
            caption if isinstance(caption, ClipCaption) else ClipCaption.model_validate(caption)
        )
        if not result.title:
            result.title = clip.query.title()
        save_cached(clip.key, result)
        return result
    except Exception as exc:  # noqa: BLE001 - never lose a clip over a caption
        logger.warning("captioning %s failed (%s); using metadata", clip.key, exc)
        return fallback_caption(clip)


async def _video_part(path: Path, cfg: Settings) -> types.Part:
    """Inline the bytes when small, otherwise upload through the Files API."""
    size = path.stat().st_size
    if size <= _INLINE_LIMIT:
        return types.Part.from_bytes(data=path.read_bytes(), mime_type="video/mp4")

    client = get_client(cfg)
    uploaded = await client.aio.files.upload(
        file=str(path),
        config=types.UploadFileConfig(mime_type="video/mp4", display_name=path.name),
    )
    for _ in range(_POLL_ATTEMPTS):
        state = str(getattr(uploaded.state, "name", uploaded.state) or "")
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise RuntimeError(f"Gemini could not process {path.name}")
        await asyncio.sleep(_POLL_SECONDS)
        uploaded = await client.aio.files.get(name=uploaded.name or "")
    if not uploaded.uri:
        raise RuntimeError(f"upload of {path.name} did not return a URI")
    return types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type or "video/mp4")
