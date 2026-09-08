"""The Rushes search agent, built on Google ADK.

Two sub-agents, run in sequence:

* `shot_planner` is a real `LlmAgent` (Gemini) with a Pydantic `output_schema`.
  It turns "moody rain-soaked street at night" into a structured SearchPlan: a
  dense sentence to embed against the archive, a short keyword query for the
  public APIs, and the concrete visual concepts to rank on.
* `source_fanout` is a custom ADK agent that runs the four `FunctionTool`s
  concurrently, then merges and ranks the four streams.

The fan-out is deliberately code rather than a second LLM turn: four parallel
calls cost as long as the slowest source, the ordering is reproducible on stage,
and a dead API degrades its own section of the grid instead of derailing the
agent mid-conversation. The tools are still ADK `FunctionTool`s, invoked with an
ADK `ToolContext` inside an ADK `SequentialAgent`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Mapping
from typing import Any

from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, ToolContext
from google.genai import types
from pydantic import ValidationError

from .config import Settings, get_settings
from .gemini import write_match_reasons
from .models import (
    SOURCE_LABELS,
    SearchHit,
    SearchPlan,
    SearchResponse,
    Source,
    SourceReport,
    coerce_source,
)
from .ranking import keywords_from_text, merge_results
from .tools import TOOLS
from .tools._common import failure, hits_from

logger = logging.getLogger(__name__)

APP_NAME = "rushes"
USER_ID = "editor"
PLAN_KEY = "search_plan"
RESULT_KEY = "search_results"

# Per-source ceiling. httpx and the MCP client have their own timeouts; this is
# the backstop that keeps one wedged source from holding the whole grid.
TOOL_TIMEOUT_S = 30.0

_DEFAULT_SOURCES = (Source.ARCHIVE, Source.STOCK, Source.PUBLIC_DOMAIN, Source.YOUTUBE)

# The same four functions, wrapped once as ADK tools.
_ADK_TOOLS: dict[Source, FunctionTool] = {
    source: FunctionTool(func=fn) for source, fn in TOOLS.items()
}

_PLANNER_INSTRUCTION = """You plan footage searches for a film editor.

Read their shot description and fill in the schema:

- archive_query: one dense visual sentence describing what should be *visible* in
  the frame. It is embedded and compared against clip captions, so name the
  subject, the setting, the light and the weather. No commentary, no "footage of".
- web_query: 2-6 plain keywords for public video APIs. No punctuation.
- keywords: 4-8 concrete visual concepts — objects, weather, light, action.
  Lower case, one or two words each. Nothing abstract.
- setting / mood / shot_type: short phrases; empty string if the editor did not
  imply one.
- subjects: the people, animals or vehicles that must appear.
- sources: which of "archive", "stock", "public_domain", "youtube" to search.
  Always include "archive" — that is the editor's own footage. Include the rest
  unless they rule them out: only "archive" if they say "my own footage", drop
  "youtube" when they ask for licensable material, and lead with "public_domain"
  for anything historical or archival.

Infer, never ask. Never invent a subject the editor did not imply."""


# ------------------------------------------------------------------- plan plumbing
def _query_of(ctx: InvocationContext) -> str:
    content = ctx.user_content
    if content and content.parts:
        text = " ".join((part.text or "") for part in content.parts).strip()
        if text:
            return text
    return str(ctx.session.state.get("query") or "")


def fallback_plan(query: str) -> SearchPlan:
    """The plan we use when Gemini is unavailable: the query, plus its keywords."""
    words = keywords_from_text(query)
    text = query.strip()
    return SearchPlan(
        archive_query=text,
        web_query=" ".join(words[:6]) or text,
        keywords=words,
        sources=[source.value for source in _DEFAULT_SOURCES],
    )


def _plan_from_state(state: Mapping[str, Any], query: str) -> SearchPlan:
    """Read the planner's output_key, filling any gap it left."""
    raw = state.get(PLAN_KEY)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = None
    if not isinstance(raw, dict):
        return fallback_plan(query)
    try:
        plan = SearchPlan.model_validate(raw)
    except ValidationError as exc:
        logger.warning("planner output did not validate: %s", exc)
        return fallback_plan(query)
    text = query.strip()
    plan.archive_query = plan.archive_query.strip() or text
    plan.web_query = plan.web_query.strip() or " ".join(keywords_from_text(query)[:6]) or text
    plan.keywords = plan.keywords or keywords_from_text(query)
    return plan


def _selected_sources(plan: SearchPlan) -> list[Source]:
    picked: list[Source] = []
    for name in plan.sources:
        source = coerce_source(name)
        if source and source not in picked:
            picked.append(source)
    if not picked:
        return list(_DEFAULT_SOURCES)
    if Source.ARCHIVE not in picked:
        picked.insert(0, Source.ARCHIVE)  # the editor's own footage always counts
    return picked


def _ranking_keywords(plan: SearchPlan, query: str) -> list[str]:
    out: list[str] = []
    for term in [*plan.keywords, *plan.subjects]:
        cleaned = term.strip().lower()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return (out or keywords_from_text(query))[:10]


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# ------------------------------------------------------------------- the fan-out
async def execute_search(
    query: str,
    plan: SearchPlan,
    *,
    settings: Settings | None = None,
    tool_context: ToolContext | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run every selected source at once, then merge, rank and explain.

    Returns the JSON-safe payload that the API serves and that the fan-out agent
    writes into session state.
    """
    cfg = settings or get_settings()
    sources = _selected_sources(plan)
    keywords = _ranking_keywords(plan, query)

    outcomes = await asyncio.gather(
        *(_call_source(source, plan, query, cfg, tool_context) for source in sources)
    )

    hits_by_source: dict[Source, list[SearchHit]] = {}
    reports: list[SourceReport] = []
    warnings: list[str] = []
    for source, payload, elapsed_ms in outcomes:
        hits = hits_from(payload)
        hits_by_source[source] = hits
        note = str(payload.get("note") or "")
        ok = bool(payload.get("ok"))
        reports.append(
            SourceReport(
                source=source,
                count=len(hits),
                duration_ms=round(elapsed_ms, 1),
                ok=ok,
                note=note,
            )
        )
        if not ok:
            warnings.append(f"{SOURCE_LABELS[source]}: {note or 'unavailable'}")

    results = merge_results(
        hits_by_source,
        keywords,
        strategy=cfg.ranking_strategy,
        limit=limit or cfg.result_limit,
    )
    # One batched Gemini call turns the keyword reasons into sentences an editor
    # would actually say. Keyword reasons stay if it fails.
    if results and cfg.enable_llm_reasons and cfg.gemini_configured:
        try:
            await write_match_reasons(query, results, settings=cfg)
        except Exception as exc:  # noqa: BLE001 - cosmetic, never blocks the grid
            logger.warning("match reasons fell back to keyword overlap: %s", exc)
            warnings.append("match explanations fell back to keyword overlap")

    return {
        "query": query,
        "plan": plan.model_dump(mode="json"),
        "results": [hit.model_dump(mode="json") for hit in results],
        "sources": [report.model_dump(mode="json") for report in reports],
        "warnings": warnings,
    }


async def _call_source(
    source: Source,
    plan: SearchPlan,
    query: str,
    cfg: Settings,
    tool_context: ToolContext | None,
) -> tuple[Source, dict[str, Any], float]:
    """One tool call that always returns an envelope, never raises."""
    if source is Source.ARCHIVE:
        args = {"query": plan.archive_query or query, "limit": cfg.search_top_k_archive}
    else:
        args = {"query": plan.web_query or query, "limit": cfg.search_top_k_external}

    started = time.perf_counter()
    try:
        payload = await asyncio.wait_for(_invoke(source, args, tool_context), TOOL_TIMEOUT_S)
    except TimeoutError:
        logger.warning("%s tool timed out", source.value)
        payload = failure(f"timed out after {TOOL_TIMEOUT_S:.0f}s")
    except Exception as exc:  # noqa: BLE001 - one source must not sink the search
        logger.warning("%s tool raised: %s", source.value, exc)
        payload = failure(str(exc)[:200])
    if not isinstance(payload, dict):
        payload = failure("tool returned an unexpected shape")
    elif "results" not in payload:
        # ADK reports a refused/failed tool call as a bare error dict.
        payload = failure(str(payload.get("error") or payload)[:200])
    return source, payload, (time.perf_counter() - started) * 1000.0

async def _invoke(
    source: Source, args: dict[str, Any], tool_context: ToolContext | None
) -> Any:
    """Through the ADK FunctionTool when running as an agent; direct otherwise."""
    if tool_context is not None:
        return await _ADK_TOOLS[source].run_async(args=args, tool_context=tool_context)
    return await TOOLS[source](**args)


# ---------------------------------------------------------------------- agents
class FanOutAgent(BaseAgent):
    """Second stage: run the four tools concurrently, merge, rank, explain."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        cfg = get_settings()
        query = _query_of(ctx)
        plan = _plan_from_state(ctx.session.state, query)
        payload = await execute_search(
            query,
            plan,
            settings=cfg,
            tool_context=ToolContext(ctx),
            limit=_int_or_none(ctx.session.state.get("limit")),
        )
        counts = ", ".join(f"{row['source']}:{row['count']}" for row in payload["sources"])
        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text=f"{len(payload['results'])} results merged ({counts}).")
                ],
            ),
            actions=EventActions(state_delta={RESULT_KEY: payload}),
        )


def build_planner(settings: Settings | None = None) -> LlmAgent:
    cfg = settings or get_settings()
    # ADK builds its own genai client from the environment, not from cfg.
    cfg.apply_genai_env()
    return LlmAgent(
        name="shot_planner",
        model=cfg.gemini_model,
        description="Reads a shot description and writes a structured search plan.",
        instruction=_PLANNER_INSTRUCTION,
        output_schema=SearchPlan,
        output_key=PLAN_KEY,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
    )

def build_root_agent(settings: Settings | None = None) -> SequentialAgent:
    """plan -> fan out -> merge. The object ADK's own tooling would load."""
    cfg = settings or get_settings()
    return SequentialAgent(
        name="rushes_search",
        description="Plans a footage search, queries four sources in parallel, ranks the results.",
        sub_agents=[
            build_planner(cfg),
            FanOutAgent(
                name="source_fanout",
                description="Runs the archive, stock, public-domain and YouTube tools together.",
            ),
        ],
    )


# `adk web` / `adk run` discover a module-level `root_agent`; see __getattr__ below.


# --------------------------------------------------------------------- entry point
async def _run_through_adk(query: str, limit: int | None, cfg: Settings) -> dict[str, Any] | None:
    """Drive the SequentialAgent with an ADK Runner and read the result out of state."""
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=APP_NAME,
        agent=build_root_agent(cfg),
        session_service=session_service,
    )
    try:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            state={"query": query, "limit": limit or cfg.result_limit},
        )
        state: dict[str, Any] = {}
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=query)]),
        ):
            delta = event.actions.state_delta if event.actions else None
            if delta:
                state.update(delta)
            if event.error_message:
                logger.warning("agent event error: %s", event.error_message)
        payload = state.get(RESULT_KEY)
        return payload if isinstance(payload, dict) else None
    finally:
        await runner.close()

async def run_search(
    query: str,
    *,
    limit: int | None = None,
    settings: Settings | None = None,
) -> SearchResponse:
    """Public entry point: one query in, one ranked SearchResponse out.

    The ADK path is tried first. If Gemini is unconfigured or the planner fails,
    the same fan-out runs against a keyword plan so the demo still returns
    footage — with a warning saying so, rather than a silent downgrade.
    """
    cfg = settings or get_settings()
    started = time.perf_counter()
    text = query.strip()
    if not text:
        return SearchResponse(query=query, plan=SearchPlan(), warnings=["empty query"])

    payload: dict[str, Any] | None = None
    warnings: list[str] = []
    if cfg.gemini_configured:
        try:
            payload = await _run_through_adk(text, limit, cfg)
            if payload is None:
                warnings.append("agent returned no results section; used a keyword plan")
        except Exception as exc:  # noqa: BLE001 - the search still has to answer
            logger.warning("ADK run failed (%s); falling back to a keyword plan", exc)
            warnings.append(f"agent planner unavailable ({type(exc).__name__}); used a keyword plan")
    else:
        warnings.append("Gemini is not configured; used a keyword plan")

    if payload is None:
        payload = await execute_search(text, fallback_plan(text), settings=cfg, limit=limit)

    response = _response_from_payload(payload)
    response.total_ms = round((time.perf_counter() - started) * 1000.0, 1)
    response.warnings = [*warnings, *response.warnings]
    return response


def _response_from_payload(payload: dict[str, Any]) -> SearchResponse:
    reports: list[SourceReport] = []
    for row in payload.get("sources") or []:
        try:
            reports.append(SourceReport.model_validate(row))
        except ValidationError as exc:
            logger.debug("dropping malformed source report: %s", exc)
    try:
        plan = SearchPlan.model_validate(payload.get("plan") or {})
    except ValidationError:
        plan = SearchPlan()
    return SearchResponse(
        query=str(payload.get("query") or ""),
        plan=plan,
        results=hits_from(payload),
        sources=reports,
        warnings=[str(item) for item in payload.get("warnings") or []],
    )


def __getattr__(name: str) -> Any:  # pragma: no cover - `adk web` discovery hook
    if name == "root_agent":
        return build_root_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "APP_NAME",
    "FanOutAgent",
    "PLAN_KEY",
    "RESULT_KEY",
    "build_planner",
    "build_root_agent",
    "execute_search",
    "fallback_plan",
    "run_search",
]
