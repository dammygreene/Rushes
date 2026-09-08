"""Shared test fixtures. Nothing here touches the network."""

from __future__ import annotations

from typing import Any

import pytest

from rushes.config import Settings
from rushes.models import SearchHit, Source


@pytest.fixture
def make_settings():
    """Settings built in isolation from the developer's own .env."""

    def factory(**overrides: Any) -> Settings:
        base: dict[str, Any] = {
            "google_api_key": "",
            "clickhouse_host": "",
            "youtube_api_key": "",
            "pexels_api_key": "",
            "enable_llm_reasons": False,
            "public_base_url": "http://testserver",
        }
        base.update(overrides)
        return Settings(_env_file=None, **base)  # type: ignore[call-arg]

    return factory


@pytest.fixture
def hit_factory():
    def factory(
        source: Source,
        title: str,
        *,
        hit_id: str | None = None,
        description: str = "",
        raw_score: float | None = None,
        page_url: str | None = None,
    ) -> SearchHit:
        return SearchHit(
            id=hit_id or f"{source.value}-{abs(hash(title)) % 10_000}",
            source=source,
            title=title,
            description=description,
            raw_score=raw_score,
            page_url=page_url or f"https://example.test/{abs(hash(title)) % 10_000}",
        )

    return factory
