"""Create the archive_clips table. Idempotent.

    python -m rushes.pipeline.create_schema
"""

from __future__ import annotations

import logging

from ..clickhouse.direct import count_clips, ensure_table
from ..clickhouse.queries import create_table_sql
from ..config import get_settings


def main() -> int:
    logging.basicConfig(level="INFO", format="%(levelname)s %(message)s")
    cfg = get_settings()
    if not cfg.clickhouse_configured:
        print("CLICKHOUSE_HOST is not set. Copy .env.example to .env and fill it in.")
        return 1
    print(create_table_sql(cfg.qualified_table))
    table = ensure_table(cfg)
    print(f"\nOK: {table} exists, {count_clips(cfg)} clips currently indexed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
