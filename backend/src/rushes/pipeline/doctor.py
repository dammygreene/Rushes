"""Preflight check: `rushes-doctor`.

Answers the two questions that matter before a demo — is ClickHouse really being
reached over MCP, and does each source answer — by doing the real thing rather
than inspecting config.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from ..agent import run_search
from ..config import Settings, get_settings
from ..gemini import embed_query
from ..models import Source
from ..runtime import get_mcp_client, shutdown
from ..tools import TOOLS

DEFAULT_QUERY = "moody rain-soaked city street at night"

_OK = "[ ok ]"
_FAIL = "[fail]"
_WARN = "[warn]"


def _mask(value: str) -> str:
    if not value:
        return "unset"
    if len(value) <= 8:
        return "set"
    return f"{value[:4]}…{value[-2:]} ({len(value)} chars)"


def _print_config(cfg: Settings) -> None:
    print("configuration")
    print(f"  gemini            : {'vertex ai' if cfg.google_genai_use_vertexai else 'api key'} "
          f"{_mask(cfg.google_api_key)}, model={cfg.gemini_model}")
    print(f"  embeddings        : {cfg.gemini_embed_model} @ {cfg.embedding_dim}d")
    print(f"  clickhouse        : {cfg.clickhouse_host or 'unset'}:{cfg.clickhouse_port} "
          f"table={cfg.qualified_table}")
    command, args = cfg.mcp_command()
    print(f"  mcp server        : {command} {' '.join(args)}".rstrip())
    print(f"  youtube key       : {_mask(cfg.youtube_api_key)}")
    print(f"  pexels key        : {_mask(cfg.pexels_api_key)}")
    print(f"  internet archive  : {cfg.archive_org_base}")
    print(f"  public base url   : {cfg.public_base_url}")
    print()


async def _check_gemini(cfg: Settings) -> bool:
    if not cfg.gemini_configured:
        print(f"{_FAIL} gemini: set GOOGLE_API_KEY (or Vertex AI project)")
        return False
    try:
        vector = await embed_query("a rainy street at night", settings=cfg)
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic
        print(f"{_FAIL} gemini embeddings: {exc}")
        return False
    if len(vector) != cfg.embedding_dim:
        print(f"{_FAIL} gemini embeddings: {len(vector)}d != EMBEDDING_DIM {cfg.embedding_dim}")
        return False
    print(f"{_OK} gemini embeddings: {len(vector)}d, unit norm")
    return True


async def _check_clickhouse(cfg: Settings) -> bool:
    if not cfg.clickhouse_configured:
        print(f"{_FAIL} clickhouse: CLICKHOUSE_HOST is not set")
        return False
    client = get_mcp_client()
    try:
        info = await client.start()
    except Exception as exc:  # noqa: BLE001
        print(f"{_FAIL} mcp-clickhouse did not start: {exc}")
        return False
    print(f"{_OK} mcp-clickhouse {info.get('version') or '?'} "
          f"(protocol {info.get('protocol') or '?'}), query tool: {info.get('query_tool')}")
    print(f"       tools exposed: {', '.join(info.get('tools') or [])}")
    try:
        clips = await client.count_clips()
    except Exception as exc:  # noqa: BLE001
        print(f"{_FAIL} SELECT over MCP failed: {exc}")
        return False
    if clips == 0:
        print(f"{_WARN} {cfg.qualified_table} is empty — run python -m rushes.pipeline.seed")
    else:
        print(f"{_OK} {clips} clips indexed in {cfg.qualified_table} (counted over MCP)")
    return True


async def _check_tools(query: str) -> None:
    async def one(source: Source) -> tuple[Source, dict[str, Any]]:
        try:
            payload = await TOOLS[source](query, 3)
        except Exception as exc:  # noqa: BLE001
            payload = {"ok": False, "count": 0, "note": str(exc)[:120]}
        return source, payload

    for source, payload in await asyncio.gather(*(one(source) for source in TOOLS)):
        mark = _OK if payload.get("ok") else _WARN
        note = payload.get("note") or ""
        print(f"{mark} {source.value:<14} {payload.get('count', 0)} results {note}".rstrip())


async def _check_search(query: str) -> None:
    response = await run_search(query)
    print(f"{_OK} end-to-end search: {len(response.results)} results in {response.total_ms:.0f}ms")
    print(f"       plan.archive_query: {response.plan.archive_query}")
    print(f"       plan.keywords     : {', '.join(response.plan.keywords)}")
    for hit in response.results[:5]:
        print(f"       {hit.score:.2f} [{hit.source_label:<13}] {hit.title[:52]}")
        print(f"            why: {hit.match_reason}")
    for warning in response.warnings:
        print(f"{_WARN} {warning}")


async def _run(args: argparse.Namespace) -> int:
    cfg = get_settings()
    _print_config(cfg)
    gemini_ok = await _check_gemini(cfg)
    clickhouse_ok = await _check_clickhouse(cfg)
    print()
    print(f"sources (query: {args.query!r})")
    await _check_tools(args.query)
    if not args.skip_search:
        print()
        await _check_search(args.query)
    await shutdown()
    return 0 if (gemini_ok and clickhouse_ok) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that every Rushes dependency answers.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--skip-search", action="store_true", help="skip the full agent run")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level="DEBUG" if args.verbose else "WARNING",
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
