"""The four tools, with mocked transports. No key, no network, no flakiness."""

from __future__ import annotations

import json

import httpx
import pytest

from rushes.models import Source
from rushes.tools import archive, archive_org, pexels, youtube

YT_SEARCH = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Neon rain walk",
                "description": "A walk through wet neon streets",
                "channelTitle": "City Walks",
                "thumbnails": {"high": {"url": "https://i.ytimg.test/abc123.jpg"}},
            },
        },
        {"id": {}, "snippet": {"title": "no id, dropped"}},
    ]
}
YT_VIDEOS = {"items": [{"id": "abc123", "contentDetails": {"duration": "PT1M30S"}}]}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_youtube_returns_links_not_files(monkeypatch, make_settings):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            assert request.url.params["type"] == "video"
            return httpx.Response(200, json=YT_SEARCH)
        return httpx.Response(200, json=YT_VIDEOS)

    monkeypatch.setattr(youtube, "get_settings", lambda: make_settings(youtube_api_key="k"))
    monkeypatch.setattr(youtube, "get_http", lambda: _client(handler))

    payload = await youtube.search_youtube("neon rain", 5)
    assert payload["ok"] is True
    assert payload["count"] == 1
    hit = payload["results"][0]
    assert hit["id"] == "yt:abc123"
    assert hit["source"] == Source.YOUTUBE.value
    assert hit["page_url"] == "https://www.youtube.com/watch?v=abc123"
    assert hit["duration_seconds"] == 90
    assert hit["clip_url"] is None and hit["hosted_by_us"] is False


async def test_youtube_reports_a_quota_error_without_raising(monkeypatch, make_settings):
    body = {"error": {"errors": [{"reason": "quotaExceeded"}]}}
    monkeypatch.setattr(youtube, "get_settings", lambda: make_settings(youtube_api_key="k"))
    monkeypatch.setattr(
        youtube, "get_http", lambda: _client(lambda request: httpx.Response(403, json=body))
    )
    payload = await youtube.search_youtube("neon rain")
    assert payload["ok"] is False
    assert "quotaExceeded" in payload["note"]


async def test_youtube_without_a_key_degrades(monkeypatch, make_settings):
    monkeypatch.setattr(youtube, "get_settings", lambda: make_settings())
    payload = await youtube.search_youtube("neon rain")
    assert payload == {"ok": False, "note": "YOUTUBE_API_KEY is not set", "count": 0, "results": []}


async def test_pexels_titles_from_alt_and_links_out(monkeypatch, make_settings):
    body = {
        "videos": [
            {
                "id": 42,
                "url": "https://www.pexels.com/video/rain-42/",
                "image": "https://images.pexels.test/42.jpg",
                "duration": 15,
                "alt": "Rain falling on a neon lit street",
                "user": {"name": "Ada"},
            }
        ]
    }
    monkeypatch.setattr(pexels, "get_settings", lambda: make_settings(pexels_api_key="k"))
    monkeypatch.setattr(
        pexels, "get_http", lambda: _client(lambda request: httpx.Response(200, json=body))
    )
    hit = (await pexels.search_pexels("neon rain"))["results"][0]
    assert hit["id"] == "px:42"
    assert hit["title"] == "Rain falling on a neon lit street"
    assert hit["attribution"] == "Ada"
    assert hit["clip_url"] is None
    assert "Pexels License" in hit["license"]


async def test_pexels_rate_limit_is_a_note(monkeypatch, make_settings):
    monkeypatch.setattr(pexels, "get_settings", lambda: make_settings(pexels_api_key="k"))
    monkeypatch.setattr(
        pexels, "get_http", lambda: _client(lambda request: httpx.Response(429, text="slow down"))
    )
    payload = await pexels.search_pexels("neon rain")
    assert payload["ok"] is False and "rate limit" in payload["note"]


async def test_archive_org_widens_when_the_cc_tier_is_thin(monkeypatch, make_settings):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        calls.append(query)
        if "creativecommons" in query:
            return httpx.Response(200, json={"response": {"docs": []}})
        docs = [
            {
                "identifier": f"film{n}",
                "title": [f"City film {n}"],
                "description": ["Traffic at dusk"],
                "creator": "Prelinger",
                "runtime": "00:01:30",
            }
            for n in range(4)
        ]
        return httpx.Response(200, json={"response": {"docs": docs}})

    monkeypatch.setattr(archive_org, "get_settings", lambda: make_settings())
    monkeypatch.setattr(archive_org, "get_http", lambda: _client(handler))

    payload = await archive_org.search_archive_org("1950s city traffic", 4)
    assert len(calls) == 2
    assert "mediatype:movies" in calls[0]
    assert payload["count"] == 4
    assert "widened" in payload["note"]
    hit = payload["results"][0]
    assert hit["source"] == Source.PUBLIC_DOMAIN.value
    assert hit["page_url"] == "https://archive.org/details/film0"
    assert hit["thumbnail_url"] == "https://archive.org/services/img/film0"
    assert hit["duration_seconds"] == 90
    assert hit["license"] == "Internet Archive — check rights"


async def test_archive_org_labels_creative_commons(monkeypatch, make_settings):
    docs = [
        {
            "identifier": "cc1",
            "title": "Open film",
            "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/",
        }
    ] * 4
    monkeypatch.setattr(archive_org, "get_settings", lambda: make_settings())
    monkeypatch.setattr(
        archive_org,
        "get_http",
        lambda: _client(lambda request: httpx.Response(200, json={"response": {"docs": docs}})),
    )
    payload = await archive_org.search_archive_org("open film", 4)
    assert payload["results"][0]["license"] == "Public domain (CC0/PDM)"
    assert payload["note"] == ""


async def test_archive_org_rejects_a_query_with_no_words(monkeypatch, make_settings):
    monkeypatch.setattr(archive_org, "get_settings", lambda: make_settings())
    payload = await archive_org.search_archive_org("!!! ???")
    assert payload["ok"] is False


class _StubMcp:
    def __init__(self, rows):
        self.rows = rows
        self.seen_limit = 0

    async def vector_search(self, embedding, limit):
        self.seen_limit = limit
        return self.rows


async def test_archive_filters_far_matches_and_absolutises_urls(monkeypatch, make_settings):
    rows = [
        {"clip_id": "near", "title": "Rain", "clip_url": "/clips/rain.mp4", "distance": 0.2},
        {"clip_id": "far", "title": "Desert", "clip_url": "/clips/sun.mp4", "distance": 0.95},
    ]
    stub = _StubMcp(rows)
    monkeypatch.setattr(
        archive, "get_settings", lambda: make_settings(clickhouse_host="h", embedding_dim=3)
    )
    monkeypatch.setattr(archive, "get_mcp_client", lambda: stub)

    async def fake_embed(text, *, settings=None):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(archive, "embed_query", fake_embed)

    payload = await archive.search_archive("rain on neon", 4)
    assert stub.seen_limit == 4
    assert payload["count"] == 1
    hit = payload["results"][0]
    assert hit["clip_url"] == "http://testserver/clips/rain.mp4"
    assert hit["hosted_by_us"] is True


async def test_archive_reports_a_dimension_mismatch(monkeypatch, make_settings):
    monkeypatch.setattr(
        archive, "get_settings", lambda: make_settings(clickhouse_host="h", embedding_dim=768)
    )

    async def fake_embed(text, *, settings=None):
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(archive, "embed_query", fake_embed)
    payload = await archive.search_archive("rain")
    assert payload["ok"] is False and "EMBEDDING_DIM" in payload["note"]


async def test_archive_without_clickhouse_is_a_soft_failure(monkeypatch, make_settings):
    monkeypatch.setattr(archive, "get_settings", lambda: make_settings())
    payload = await archive.search_archive("rain")
    assert payload["ok"] is False and payload["results"] == []


def test_envelope_is_json_serialisable():
    from rushes.tools._common import envelope, failure

    assert json.loads(json.dumps(failure("nope")))["count"] == 0
    assert json.loads(json.dumps(envelope([])))["ok"] is True


def test_reason_never_renders_an_empty_note():
    """httpx transport errors stringify to '', which used to reach the UI as
    'Pexels search failed: ' with nothing after the colon."""
    from rushes.tools._common import reason

    assert reason(ValueError("bad vector")) == "bad vector"
    assert reason(httpx.ConnectError("")) == "ConnectError"
    assert reason(httpx.ReadTimeout("   ")) == "ReadTimeout"


@pytest.mark.parametrize(
    ("iso", "seconds"),
    [("PT1M30S", 90), ("PT2H", 7200), ("P1DT1S", 86401), ("", None), ("nonsense", None)],
)
def test_iso_duration_parsing(iso, seconds):
    from rushes.tools._common import parse_iso_duration

    assert parse_iso_duration(iso) == seconds
