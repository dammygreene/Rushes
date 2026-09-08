"""The agent: plan handling, the parallel fan-out, and the fallback path."""

from __future__ import annotations

import asyncio

from rushes import agent
from rushes.models import SearchHit, SearchPlan, Source

PLAN = SearchPlan(
    archive_query="a rain-slicked neon street at night",
    web_query="neon rain street night",
    keywords=["rain", "neon", "night"],
    sources=["archive", "youtube"],
)


def _envelope(source: Source, titles: list[str], *, ok: bool = True, note: str = "") -> dict:
    hits = [
        SearchHit(id=f"{source.value}-{n}", source=source, title=title)
        for n, title in enumerate(titles)
    ]
    return {
        "ok": ok,
        "note": note,
        "count": len(hits),
        "results": [hit.model_dump(mode="json") for hit in hits],
    }


def _fake_tools(monkeypatch, behaviour: dict[Source, object]) -> dict[Source, list]:
    """Replace the four tools with recorders. Returns the call log per source."""
    calls: dict[Source, list] = {source: [] for source in Source}

    def make(source: Source):
        async def tool(query: str, limit: int = 6):
            calls[source].append((query, limit))
            outcome = behaviour.get(source)
            if isinstance(outcome, Exception):
                raise outcome
            if callable(outcome):
                return await outcome(query, limit)
            return outcome if outcome is not None else _envelope(source, [])

        return tool

    monkeypatch.setattr(agent, "TOOLS", {source: make(source) for source in Source})
    return calls


def test_plan_from_state_accepts_a_dict_or_a_json_string():
    as_dict = agent._plan_from_state({agent.PLAN_KEY: PLAN.model_dump()}, "rain")
    assert as_dict.web_query == "neon rain street night"

    as_json = agent._plan_from_state({agent.PLAN_KEY: PLAN.model_dump_json()}, "rain")
    assert as_json.keywords == ["rain", "neon", "night"]


def test_plan_from_state_falls_back_on_junk():
    for junk in ({}, {agent.PLAN_KEY: "not json"}, {agent.PLAN_KEY: 7}):
        plan = agent._plan_from_state(junk, "moody rain at night")
        assert plan.archive_query == "moody rain at night"
        assert plan.keywords == ["moody", "rain", "night"]
        assert len(plan.sources) == 4


def test_plan_from_state_backfills_missing_pieces():
    plan = agent._plan_from_state({agent.PLAN_KEY: {"web_query": "rain"}}, "rain at night")
    assert plan.archive_query == "rain at night"
    assert plan.web_query == "rain"
    assert plan.keywords == ["rain", "night"]


def test_selected_sources_always_includes_the_archive():
    assert agent._selected_sources(SearchPlan(sources=["youtube"])) == [
        Source.ARCHIVE,
        Source.YOUTUBE,
    ]
    assert agent._selected_sources(SearchPlan(sources=[])) == list(agent._DEFAULT_SOURCES)
    assert agent._selected_sources(SearchPlan(sources=["pexels", "nonsense"])) == [
        Source.ARCHIVE,
        Source.STOCK,
    ]


async def test_execute_search_runs_only_the_planned_sources(monkeypatch, make_settings):
    calls = _fake_tools(
        monkeypatch,
        {
            Source.ARCHIVE: _envelope(Source.ARCHIVE, ["Rain on neon at night"]),
            Source.YOUTUBE: _envelope(Source.YOUTUBE, ["Neon rain walk", "Night street"]),
        },
    )
    payload = await agent.execute_search(
        "neon rain at night", PLAN, settings=make_settings(search_top_k_archive=8)
    )

    assert calls[Source.ARCHIVE] == [("a rain-slicked neon street at night", 8)]
    assert calls[Source.YOUTUBE] == [("neon rain street night", 6)]
    assert calls[Source.STOCK] == [] and calls[Source.PUBLIC_DOMAIN] == []
    assert len(payload["results"]) == 3
    assert {row["source"] for row in payload["sources"]} == {"archive", "youtube"}
    assert all(row["ok"] for row in payload["sources"])
    assert all(hit["match_reason"] for hit in payload["results"])
    assert payload["warnings"] == []


async def test_execute_search_survives_a_raising_tool(monkeypatch, make_settings):
    _fake_tools(
        monkeypatch,
        {
            Source.ARCHIVE: RuntimeError("clickhouse is down"),
            Source.YOUTUBE: _envelope(Source.YOUTUBE, ["Neon rain walk"]),
        },
    )
    payload = await agent.execute_search("neon rain", PLAN, settings=make_settings())

    assert len(payload["results"]) == 1
    archive_report = next(row for row in payload["sources"] if row["source"] == "archive")
    assert archive_report["ok"] is False
    assert "clickhouse is down" in archive_report["note"]
    assert any("Archive" in warning for warning in payload["warnings"])


async def test_execute_search_reports_a_timeout_without_hanging(monkeypatch, make_settings):
    async def slow(query: str, limit: int):
        await asyncio.sleep(5)
        return _envelope(Source.YOUTUBE, [])

    monkeypatch.setattr(agent, "TOOL_TIMEOUT_S", 0.05)
    _fake_tools(monkeypatch, {Source.YOUTUBE: slow, Source.ARCHIVE: _envelope(Source.ARCHIVE, [])})
    payload = await agent.execute_search("neon rain", PLAN, settings=make_settings())

    youtube_report = next(row for row in payload["sources"] if row["source"] == "youtube")
    assert youtube_report["ok"] is False
    assert "timed out" in youtube_report["note"]


async def test_execute_search_normalises_an_adk_error_dict(monkeypatch, make_settings):
    _fake_tools(monkeypatch, {Source.ARCHIVE: {"error": "tool refused"}})
    payload = await agent.execute_search("neon rain", SearchPlan(sources=["archive"]), settings=make_settings())
    report = payload["sources"][0]
    assert report["ok"] is False and "tool refused" in report["note"]


async def test_execute_search_honours_the_limit(monkeypatch, make_settings):
    _fake_tools(
        monkeypatch,
        {Source.ARCHIVE: _envelope(Source.ARCHIVE, [f"clip {n}" for n in range(10)])},
    )
    payload = await agent.execute_search(
        "rain", SearchPlan(sources=["archive"]), settings=make_settings(), limit=3
    )
    assert len(payload["results"]) == 3


async def test_run_search_without_gemini_uses_a_keyword_plan(monkeypatch, make_settings):
    calls = _fake_tools(
        monkeypatch,
        {source: _envelope(source, [f"{source.value} clip"]) for source in Source},
    )
    response = await agent.run_search("moody rain-soaked street", settings=make_settings())

    assert response.plan.archive_query == "moody rain-soaked street"
    assert calls[Source.ARCHIVE][0][0] == "moody rain-soaked street"
    assert calls[Source.STOCK][0][0] == "moody rain soaked street"
    assert len(response.results) == 4
    assert len(response.sources) == 4
    assert response.total_ms >= 0
    assert any("Gemini is not configured" in warning for warning in response.warnings)


async def test_run_search_rejects_an_empty_query(make_settings):
    response = await agent.run_search("   ", settings=make_settings())
    assert response.results == []
    assert response.warnings == ["empty query"]


async def test_run_search_falls_back_when_the_adk_run_fails(monkeypatch, make_settings):
    _fake_tools(monkeypatch, {source: _envelope(source, ["clip"]) for source in Source})

    async def boom(query, limit, cfg):
        raise RuntimeError("planner exploded")

    monkeypatch.setattr(agent, "_run_through_adk", boom)
    response = await agent.run_search(
        "rain at night", settings=make_settings(google_api_key="fake-key")
    )
    assert len(response.results) == 4
    assert any("planner unavailable" in warning for warning in response.warnings)


def test_build_root_agent_is_a_two_stage_sequence(make_settings):
    root = agent.build_root_agent(make_settings())
    assert [sub.name for sub in root.sub_agents] == ["shot_planner", "source_fanout"]
    planner = root.sub_agents[0]
    assert planner.output_schema is SearchPlan
    assert planner.output_key == agent.PLAN_KEY
