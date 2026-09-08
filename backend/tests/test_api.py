"""The HTTP surface. ASGITransport means no lifespan, so no MCP subprocess."""

from __future__ import annotations

import httpx
import pytest

from rushes import api
from rushes.models import SearchHit, SearchPlan, SearchResponse, SourceReport, Source

RESPONSE = SearchResponse(
    query="neon rain",
    plan=SearchPlan(archive_query="a rain-slicked neon street", web_query="neon rain street"),
    results=[
        SearchHit(
            id="archive-1",
            source=Source.ARCHIVE,
            title="Rain on neon",
            clip_url="http://testserver/clips/rain.mp4",
            hosted_by_us=True,
            score=0.91,
            match_reason="semantic match (88% similarity)",
        ),
        SearchHit(
            id="yt:abc",
            source=Source.YOUTUBE,
            title="Neon rain walk",
            page_url="https://www.youtube.com/watch?v=abc",
            score=0.4,
            match_reason="matches: rain, neon",
        ),
    ],
    sources=[
        SourceReport(source=Source.ARCHIVE, count=1, duration_ms=12.0),
        SourceReport(source=Source.YOUTUBE, count=1, duration_ms=90.0),
    ],
    total_ms=105.0,
    warnings=["Stock is offline: PEXELS_API_KEY is not set"],
)


@pytest.fixture
def client() -> httpx.AsyncClient:
    """No lifespan: nothing starts a subprocess or touches the network."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app), base_url="http://testserver"
    )


def _capture(monkeypatch) -> list[tuple[str, int | None]]:
    seen: list[tuple[str, int | None]] = []

    async def fake_run_search(query: str, *, limit=None, settings=None) -> SearchResponse:
        seen.append((query, limit))
        return RESPONSE

    monkeypatch.setattr(api, "run_search", fake_run_search)
    return seen


async def test_healthz_needs_nothing(client):
    async with client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_search_returns_the_unified_shape(monkeypatch, client):
    seen = _capture(monkeypatch)
    async with client:
        response = await client.post("/api/search", json={"query": "neon rain", "limit": 12})

    assert response.status_code == 200
    assert seen == [("neon rain", 12)]
    body = response.json()
    assert body["plan"]["web_query"] == "neon rain street"
    assert [hit["source"] for hit in body["results"]] == ["archive", "youtube"]
    archive, youtube = body["results"]
    assert archive["hosted_by_us"] is True and archive["clip_url"].endswith("rain.mp4")
    assert youtube["hosted_by_us"] is False and youtube["clip_url"] is None
    assert all(hit["match_reason"] for hit in body["results"])
    assert body["warnings"] == ["Stock is offline: PEXELS_API_KEY is not set"]


async def test_search_validates_the_request(monkeypatch, client):
    _capture(monkeypatch)
    async with client:
        empty = await client.post("/api/search", json={"query": ""})
        huge = await client.post("/api/search", json={"query": "rain", "limit": 500})
        missing = await client.post("/api/search", json={})
    assert empty.status_code == huge.status_code == missing.status_code == 422


async def test_search_is_open_when_no_token_is_configured(monkeypatch, client, make_settings):
    _capture(monkeypatch)
    monkeypatch.setattr(api, "get_settings", lambda: make_settings(api_token=""))
    async with client:
        response = await client.post("/api/search", json={"query": "rain"})
    assert response.status_code == 200


async def test_search_requires_the_bearer_token_when_one_is_set(monkeypatch, client, make_settings):
    _capture(monkeypatch)
    monkeypatch.setattr(api, "get_settings", lambda: make_settings(api_token="s3cret"))
    async with client:
        anonymous = await client.post("/api/search", json={"query": "rain"})
        wrong = await client.post(
            "/api/search", json={"query": "rain"}, headers={"Authorization": "Bearer nope"}
        )
        right = await client.post(
            "/api/search", json={"query": "rain"}, headers={"Authorization": "Bearer s3cret"}
        )
    assert anonymous.status_code == 401
    assert wrong.status_code == 401
    assert right.status_code == 200


async def test_status_reports_what_is_wired_up(monkeypatch, client, make_settings):
    monkeypatch.setattr(api, "get_settings", lambda: make_settings(youtube_api_key="k"))
    async with client:
        body = (await client.get("/api/status")).json()

    assert body["clickhouse"]["configured"] is False
    assert body["clickhouse"]["error"] == "CLICKHOUSE_HOST is not set"
    assert body["clickhouse"]["via"] == "mcp-clickhouse (stdio)"
    assert body["gemini"]["configured"] is False
    assert body["sources"] == {
        "archive": False,
        "youtube": True,
        "public_domain": True,
        "stock": False,
    }


async def test_status_never_500s_when_the_mcp_server_is_broken(monkeypatch, client, make_settings):
    class _Broken:
        running = False

        async def start(self):
            raise RuntimeError("uvx is not installed")

    monkeypatch.setattr(api, "get_settings", lambda: make_settings(clickhouse_host="h"))
    monkeypatch.setattr(api, "get_mcp_client", lambda: _Broken())
    async with client:
        response = await client.get("/api/status")

    assert response.status_code == 200
    assert "uvx is not installed" in response.json()["clickhouse"]["error"]
