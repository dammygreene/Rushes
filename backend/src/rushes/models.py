"""Shared data shapes: what the LLM is asked to produce, what the tools return,
and what the API hands to the frontend.

The LLM-facing models (SearchPlan, ClipCaption, MatchReasons) deliberately avoid
Optional fields — Gemini's structured-output schema converter is happiest with
plain strings/lists plus defaults.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Source(str, Enum):
    """Where a result came from. Only ARCHIVE is ever hosted by us."""

    ARCHIVE = "archive"
    YOUTUBE = "youtube"
    PUBLIC_DOMAIN = "public_domain"
    STOCK = "stock"


SOURCE_LABELS: dict[Source, str] = {
    Source.ARCHIVE: "Archive",
    Source.YOUTUBE: "YouTube",
    Source.PUBLIC_DOMAIN: "Public Domain",
    Source.STOCK: "Stock",
}

# Tolerate whatever the planner LLM calls each source.
SOURCE_ALIASES: dict[str, Source] = {
    "archive": Source.ARCHIVE,
    "private": Source.ARCHIVE,
    "private_archive": Source.ARCHIVE,
    "clickhouse": Source.ARCHIVE,
    "youtube": Source.YOUTUBE,
    "yt": Source.YOUTUBE,
    "public_domain": Source.PUBLIC_DOMAIN,
    "publicdomain": Source.PUBLIC_DOMAIN,
    "internet_archive": Source.PUBLIC_DOMAIN,
    "archive_org": Source.PUBLIC_DOMAIN,
    "stock": Source.STOCK,
    "pexels": Source.STOCK,
}


def coerce_source(value: str) -> Source | None:
    return SOURCE_ALIASES.get(value.strip().lower().replace("-", "_").replace(" ", "_"))


# --------------------------------------------------------------------- LLM I/O
class SearchPlan(BaseModel):
    """Structured reading of the user's shot description (planner agent output)."""

    archive_query: str = Field(
        default="",
        description="Query rewritten as a dense visual sentence, for embedding.",
    )
    web_query: str = Field(
        default="",
        description="Short keyword query (2-6 words) for public video APIs.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Concrete visual concepts to match on: objects, weather, light, action.",
    )
    setting: str = Field(default="", description="Location or environment, e.g. 'city street'.")
    mood: str = Field(default="", description="Emotional register, e.g. 'moody', 'joyful'.")
    shot_type: str = Field(default="", description="e.g. 'wide shot', 'close-up', 'aerial'.")
    subjects: list[str] = Field(default_factory=list, description="People/animals/vehicles wanted.")
    sources: list[str] = Field(
        default_factory=list,
        description="Which sources to search: archive, youtube, public_domain, stock.",
    )


class ClipCaption(BaseModel):
    """Gemini's structured description of one archive clip (seeding pipeline)."""

    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    mood: str = ""
    setting: str = ""
    objects: list[str] = Field(default_factory=list)


class MatchReason(BaseModel):
    id: str = ""
    reason: str = ""


class MatchReasons(BaseModel):
    reasons: list[MatchReason] = Field(default_factory=list)


# ----------------------------------------------------------------- results/API
class SearchHit(BaseModel):
    """One row in the unified result grid."""

    id: str
    source: Source
    title: str
    description: str = ""
    thumbnail_url: str | None = None
    # Outbound link to the source's own page. Always present for external hits.
    page_url: str | None = None
    # Directly playable media. Only set for clips we own and host.
    clip_url: str | None = None
    duration_seconds: int | None = None
    license: str = ""
    attribution: str | None = None
    tags: list[str] = Field(default_factory=list)
    # 0..1 after normalisation; raw_score keeps the source-native number
    # (cosine similarity for the archive, rank position for web sources).
    score: float = 0.0
    raw_score: float | None = None
    match_reason: str = ""
    # True only for owned archive clips; the UI uses it to decide play vs link.
    hosted_by_us: bool = False

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS[self.source]


class SourceReport(BaseModel):
    """Per-source outcome, surfaced in the UI so a silent failure is visible."""

    source: Source
    count: int = 0
    duration_ms: float = 0.0
    ok: bool = True
    note: str = ""


class SearchResponse(BaseModel):
    query: str
    plan: SearchPlan
    results: list[SearchHit] = Field(default_factory=list)
    sources: list[SourceReport] = Field(default_factory=list)
    total_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
