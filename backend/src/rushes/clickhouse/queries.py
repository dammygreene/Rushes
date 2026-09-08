"""SQL construction and result parsing for the ClickHouse archive.

Reads go out over the mcp-clickhouse MCP server, which only accepts SELECT
statements, so everything here is either a SELECT or the one-off DDL used by the
seeding pipeline. Only numbers and validated identifiers are ever interpolated.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from typing import Any

from ..models import SearchHit, Source

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

SELECT_COLUMNS = (
    "clip_id",
    "title",
    "description",
    "tags",
    "duration_seconds",
    "thumbnail_url",
    "clip_url",
    "source",
    "license",
)


def validate_identifier(name: str) -> str:
    """Guard the one string we interpolate: the (optionally qualified) table."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"unsafe ClickHouse identifier: {name!r}")
    return name


def vector_literal(embedding: Sequence[float]) -> str:
    """Render a float vector as a ClickHouse array literal."""
    if not embedding:
        raise ValueError("embedding is empty")
    parts: list[str] = []
    for value in embedding:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("embedding contains NaN or infinity")
        parts.append(f"{number:.6g}")
    return "[" + ",".join(parts) + "]"


def build_vector_search_sql(
    table: str,
    embedding: Sequence[float],
    *,
    limit: int = 8,
) -> str:
    """Top-k nearest neighbours by cosine distance.

    cosineDistance returns 0 for identical direction, so similarity is 1 - d.
    The relevance cut-off is applied after parsing (see MAX_DISTANCE in
    tools/archive.py) to keep this statement portable and easy to eyeball.
    """
    table = validate_identifier(table)
    columns = ", ".join(SELECT_COLUMNS)
    # No SETTINGS clause on purpose: mcp-clickhouse runs every statement
    # read-only, and ClickHouse refuses to change a setting in that mode
    # (code 164, READONLY). The statement is bounded by the MCP client's own
    # send/receive timeout and by TOOL_TIMEOUT_S in agent.py instead.
    return (
        f"SELECT {columns}, "
        f"cosineDistance(embedding, {vector_literal(embedding)}) AS distance "
        f"FROM {table} "
        f"WHERE length(embedding) = {len(embedding)} "
        f"ORDER BY distance ASC "
        f"LIMIT {int(limit)}"
    )


def build_count_sql(table: str) -> str:
    return f"SELECT count() AS clips FROM {validate_identifier(table)}"


def create_table_sql(table: str) -> str:
    """Schema from the blueprint. MergeTree ordered by clip_id."""
    return f"""
CREATE TABLE IF NOT EXISTS {validate_identifier(table)} (
    clip_id UUID DEFAULT generateUUIDv4(),
    title String,
    description String,
    tags Array(String),
    embedding Array(Float32),
    duration_seconds UInt16,
    thumbnail_url String,
    clip_url String,
    source String DEFAULT 'archive',
    license String DEFAULT 'owned',
    created_at DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY clip_id
""".strip()


# --------------------------------------------------------------------- parsing
def parse_tool_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalise whatever run_select_query hands back into a list of row dicts.

    mcp-clickhouse has returned {"columns": [...], "rows": [[...]]} and plain
    lists of objects across versions, sometimes JSON-encoded inside a text
    content block. Handle all of them rather than pinning to one shape.
    """
    if payload is None:
        return []
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return []
        try:
            return parse_tool_payload(json.loads(text))
        except json.JSONDecodeError as exc:
            raise ValueError(f"ClickHouse MCP returned non-JSON text: {text[:200]}") from exc
    if isinstance(payload, dict):
        if payload.get("status") == "error" or ("error" in payload and "rows" not in payload):
            raise RuntimeError(str(payload.get("message") or payload.get("error")))
        rows = payload.get("rows")
        if rows is None:
            for key in ("data", "result", "results"):
                if key in payload:
                    return parse_tool_payload(payload[key])
            return []
        columns = payload.get("columns") or payload.get("column_names") or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append(row)
            else:
                out.append({str(col): val for col, val in zip(columns, row)})
        return out
    if isinstance(payload, list):
        out = []
        for item in payload:
            if isinstance(item, dict):
                out.append(item)
        return out
    raise ValueError(f"unexpected ClickHouse MCP payload type: {type(payload)!r}")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def rows_to_hits(rows: Sequence[dict[str, Any]]) -> list[SearchHit]:
    """Map archive rows onto the shared result shape."""
    hits: list[SearchHit] = []
    for row in rows:
        distance = row.get("distance")
        similarity = None
        if isinstance(distance, (int, float)):
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
        tags = row.get("tags") or []
        if isinstance(tags, str):
            tags = [t for t in (part.strip() for part in tags.split(",")) if t]
        clip_url = (row.get("clip_url") or "").strip() or None
        hits.append(
            SearchHit(
                id=str(row.get("clip_id") or row.get("id") or ""),
                source=Source.ARCHIVE,
                title=str(row.get("title") or "Untitled clip"),
                description=str(row.get("description") or ""),
                thumbnail_url=(row.get("thumbnail_url") or "").strip() or None,
                page_url=clip_url,
                clip_url=clip_url,
                duration_seconds=_as_int(row.get("duration_seconds")),
                license=str(row.get("license") or "owned"),
                attribution="Private archive",
                tags=[str(t) for t in tags],
                raw_score=similarity,
                hosted_by_us=True,
            )
        )
    return hits
