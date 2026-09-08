"""Gemini calls: embeddings, structured JSON generation, match explanations.

One client, built from Settings, shared by the API and the seeding pipeline.
Async wherever the request path touches it so a slow embedding never blocks the
event loop.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Sequence
from typing import Any

from google import genai
from google.genai import types
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from .config import Settings, get_settings
from .models import MatchReasons, SearchHit

logger = logging.getLogger(__name__)

_TRANSIENT_MARKERS = ("429", "500", "502", "503", "504", "deadline", "timeout", "unavailable")


class GeminiNotConfigured(RuntimeError):
    pass


_clients: dict[tuple[Any, ...], genai.Client] = {}


def get_client(settings: Settings | None = None) -> genai.Client:
    """Cached genai client. Settings objects are not hashable, so the cache is
    keyed on the credentials that actually change the client."""
    cfg = settings or get_settings()
    if not cfg.gemini_configured:
        raise GeminiNotConfigured(
            "Gemini is not configured: set GOOGLE_API_KEY, or "
            "GOOGLE_GENAI_USE_VERTEXAI=true with GOOGLE_CLOUD_PROJECT."
        )
    key = (
        cfg.google_genai_use_vertexai,
        cfg.google_api_key,
        cfg.google_cloud_project,
        cfg.google_cloud_location,
    )
    client = _clients.get(key)
    if client is None:
        if cfg.google_genai_use_vertexai:
            client = genai.Client(
                vertexai=True,
                project=cfg.google_cloud_project,
                location=cfg.google_cloud_location,
            )
        else:
            client = genai.Client(api_key=cfg.google_api_key)
        _clients[key] = client
    return client


def _is_transient(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)


def normalize(vector: Sequence[float]) -> list[float]:
    """Unit-length the vector. Required for sub-3072 gemini-embedding output,
    and it keeps cosineDistance in ClickHouse on a predictable 0..2 scale."""
    norm = math.sqrt(sum(float(v) * float(v) for v in vector))
    if norm == 0.0:
        return [float(v) for v in vector]
    return [float(v) / norm for v in vector]


# ------------------------------------------------------------------ embeddings
@_retry
async def _embed_batch(texts: list[str], task_type: str, cfg: Settings) -> list[list[float]]:
    response = await get_client(cfg).aio.models.embed_content(
        model=cfg.gemini_embed_model,
        contents=list(texts),
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=cfg.embedding_dim,
        ),
    )
    return [normalize(item.values or []) for item in (response.embeddings or [])]


async def embed_texts(
    texts: Sequence[str],
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
    settings: Settings | None = None,
) -> list[list[float]]:
    """Embed a batch, falling back to one-at-a-time if the model refuses batches."""
    cfg = settings or get_settings()
    cleaned = [text.strip() or "untitled clip" for text in texts]
    if not cleaned:
        return []
    try:
        vectors = await _embed_batch(cleaned, task_type, cfg)
        if len(vectors) == len(cleaned):
            return vectors
        logger.warning("embedding batch returned %d of %d", len(vectors), len(cleaned))
    except Exception as exc:  # noqa: BLE001 - some models cap batches at 1
        logger.warning("batch embedding failed (%s); retrying one at a time", exc)
    out: list[list[float]] = []
    for text in cleaned:
        out.extend(await _embed_batch([text], task_type, cfg))
    return out


async def embed_query(text: str, *, settings: Settings | None = None) -> list[float]:
    vectors = await embed_texts([text], task_type="RETRIEVAL_QUERY", settings=settings)
    if not vectors:
        raise RuntimeError("Gemini returned no embedding for the query")
    return vectors[0]


# ------------------------------------------------- structured text generation
@_retry
async def generate_json(
    prompt: str | list[Any],
    schema: type,
    *,
    settings: Settings | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> Any:
    """One Gemini call constrained to a Pydantic schema."""
    cfg = settings or get_settings()
    contents = prompt if isinstance(prompt, list) else [prompt]
    response = await get_client(cfg).aio.models.generate_content(
        model=model or cfg.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        ),
    )
    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        return parsed
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty response")
    return schema.model_validate(json.loads(text))  # type: ignore[attr-defined]


_REASON_PROMPT = """You are helping a film editor scan search results.

Their request: "{query}"

For each candidate below, write one clause (max 10 words, lower case, no full
stop) naming the concrete visual features that make it a match — e.g.
"rain-slick road, neon reflections, wide framing". Do not invent details that
are not in the candidate's own title or description. If a candidate is a weak
match, say so plainly, e.g. "only loosely related: daytime, no rain".

Candidates:
{candidates}
"""


async def write_match_reasons(
    query: str,
    hits: Sequence[SearchHit],
    *,
    settings: Settings | None = None,
) -> int:
    """Fill in match_reason for the given hits with one batched Gemini call.

    Returns the number of hits updated. Keyword-derived reasons stay in place if
    this fails — the grid is never blocked on it.
    """
    if not hits:
        return 0
    candidates = "\n".join(
        f"- id={hit.id} | source={hit.source.value} | {hit.title} | "
        f"{(hit.description or '')[:240]}"
        for hit in hits
    )
    result = await generate_json(
        _REASON_PROMPT.format(query=query, candidates=candidates),
        MatchReasons,
        settings=settings,
        temperature=0.3,
    )
    reasons = result if isinstance(result, MatchReasons) else MatchReasons.model_validate(result)
    by_id = {item.id: item.reason.strip() for item in reasons.reasons if item.reason.strip()}
    updated = 0
    for hit in hits:
        reason = by_id.get(hit.id)
        if reason:
            hit.match_reason = reason
            updated += 1
    return updated
