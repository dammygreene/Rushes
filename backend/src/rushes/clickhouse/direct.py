"""Direct clickhouse-connect client: DDL and INSERT for the seeding pipeline.

The search path never comes through here — every archive read in the running app
goes over the mcp-clickhouse MCP server (see `mcp_client.py`), which is read-only
by design. Seeding needs CREATE TABLE and INSERT, so the pipeline uses the
official Python driver instead. Keeping the two paths in separate modules makes
it obvious which one the demo's search actually uses.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from ..config import Settings, get_settings
from .queries import create_table_sql, validate_identifier

logger = logging.getLogger(__name__)

INSERT_COLUMNS = (
    "clip_id",
    "title",
    "description",
    "tags",
    "embedding",
    "duration_seconds",
    "thumbnail_url",
    "clip_url",
    "source",
    "license",
)


def get_client(settings: Settings | None = None) -> Client:
    cfg = settings or get_settings()
    if not cfg.clickhouse_configured:
        raise RuntimeError("CLICKHOUSE_HOST is not set; copy .env.example to .env first")
    return clickhouse_connect.get_client(
        host=cfg.clickhouse_host,
        port=cfg.clickhouse_port,
        username=cfg.clickhouse_user,
        password=cfg.clickhouse_password,
        secure=cfg.clickhouse_secure,
        verify=cfg.clickhouse_verify,
        database=cfg.clickhouse_database,
        connect_timeout=15,
        send_receive_timeout=180,
        client_name="rushes-seed",
    )


def ensure_table(settings: Settings | None = None) -> str:
    """Create archive_clips if it is not there yet. Safe to run repeatedly."""
    cfg = settings or get_settings()
    table = cfg.qualified_table
    with get_client(cfg) as client:
        client.command(create_table_sql(table))
    logger.info("ensured table %s", table)
    return table


def existing_clip_urls(settings: Settings | None = None) -> set[str]:
    """Already-seeded clip_urls, so re-running the seed does not duplicate rows."""
    cfg = settings or get_settings()
    table = validate_identifier(cfg.qualified_table)
    try:
        with get_client(cfg) as client:
            result = client.query(f"SELECT DISTINCT clip_url FROM {table}")
        return {str(row[0]) for row in result.result_rows if row and row[0]}
    except Exception as exc:  # noqa: BLE001 - first run: the table may not exist
        logger.debug("could not read existing clips: %s", exc)
        return set()


def insert_clips(rows: Sequence[dict[str, Any]], settings: Settings | None = None) -> int:
    """Insert caption+embedding rows. Returns the number of rows written."""
    if not rows:
        return 0
    cfg = settings or get_settings()
    data = [[_coerce(column, row.get(column)) for column in INSERT_COLUMNS] for row in rows]
    with get_client(cfg) as client:
        client.insert(cfg.qualified_table, data, column_names=list(INSERT_COLUMNS))
    logger.info("inserted %d clips into %s", len(data), cfg.qualified_table)
    return len(data)


def count_clips(settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    table = validate_identifier(cfg.qualified_table)
    with get_client(cfg) as client:
        result = client.query(f"SELECT count() FROM {table}")
    return int(result.result_rows[0][0]) if result.result_rows else 0


def _coerce(column: str, value: Any) -> Any:
    """Match the column types in create_table_sql exactly."""
    if column == "clip_id":
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return uuid.uuid4()
    if column in ("tags",):
        return [str(item) for item in (value or [])]
    if column == "embedding":
        return [float(item) for item in (value or [])]
    if column == "duration_seconds":
        try:
            return max(0, min(65535, int(value)))
        except (TypeError, ValueError):
            return 0
    if column == "source":
        return str(value or "archive")
    if column == "license":
        return str(value or "owned")
    return str(value or "")
