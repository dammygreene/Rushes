"""SQL construction and MCP payload parsing — the archive path's sharp edges."""

from __future__ import annotations

import pytest

from rushes.clickhouse.queries import (
    build_count_sql,
    build_vector_search_sql,
    create_table_sql,
    parse_tool_payload,
    rows_to_hits,
    validate_identifier,
    vector_literal,
)
from rushes.models import Source

EMBEDDING = [0.1, -0.2, 0.3]


def test_validate_identifier_rejects_injection():
    assert validate_identifier("default.archive_clips") == "default.archive_clips"
    for bad in ("clips; DROP TABLE x", "clips--", "a.b.c", "", "clips WHERE 1=1"):
        with pytest.raises(ValueError):
            validate_identifier(bad)


def test_vector_literal_rejects_non_finite():
    assert vector_literal([1.0, 2.5]) == "[1,2.5]"
    with pytest.raises(ValueError):
        vector_literal([float("nan")])
    with pytest.raises(ValueError):
        vector_literal([])


def test_vector_search_sql_shape():
    sql = build_vector_search_sql("default.archive_clips", EMBEDDING, limit=5)
    assert "cosineDistance(embedding, [0.1,-0.2,0.3]) AS distance" in sql
    assert "FROM default.archive_clips" in sql
    assert f"WHERE length(embedding) = {len(EMBEDDING)}" in sql
    # No SETTINGS clause: mcp-clickhouse runs read-only and ClickHouse rejects
    # setting changes in that mode (code 164, READONLY).
    assert "SETTINGS" not in sql
    assert sql.strip().endswith("LIMIT 5")
    assert "ORDER BY distance ASC LIMIT 5" in sql


def test_count_and_ddl_use_the_blueprint_schema():
    assert build_count_sql("db.t") == "SELECT count() AS clips FROM db.t"
    ddl = create_table_sql("db.archive_clips")
    assert "CREATE TABLE IF NOT EXISTS db.archive_clips" in ddl
    assert "embedding Array(Float32)" in ddl
    assert "ENGINE = MergeTree()" in ddl
    assert "ORDER BY clip_id" in ddl


@pytest.mark.parametrize(
    "payload",
    [
        '{"columns": ["clip_id"], "rows": [["abc"]]}',
        {"columns": ["clip_id"], "rows": [["abc"]]},
        [{"clip_id": "abc"}],
        {"result": '[{"clip_id": "abc"}]'},
        {"data": [{"clip_id": "abc"}]},
    ],
)
def test_parse_tool_payload_accepts_every_shape_the_server_has_used(payload):
    assert parse_tool_payload(payload) == [{"clip_id": "abc"}]


def test_parse_tool_payload_empty_and_error_cases():
    assert parse_tool_payload(None) == []
    assert parse_tool_payload("") == []
    with pytest.raises(RuntimeError):
        parse_tool_payload({"status": "error", "message": "readonly"})
    with pytest.raises(ValueError):
        parse_tool_payload("not json at all")


def test_rows_to_hits_maps_distance_to_similarity():
    hits = rows_to_hits(
        [
            {
                "clip_id": "uuid-1",
                "title": "Rain on neon street",
                "description": "wet asphalt",
                "tags": ["rain", "neon"],
                "duration_seconds": "12",
                "thumbnail_url": "https://img.test/1.jpg",
                "clip_url": "/clips/rain.mp4",
                "license": "owned",
                "distance": 0.25,
            }
        ]
    )
    hit = hits[0]
    assert hit.source is Source.ARCHIVE
    assert hit.hosted_by_us is True
    assert hit.raw_score == pytest.approx(0.75)
    assert hit.duration_seconds == 12
    assert hit.clip_url == hit.page_url == "/clips/rain.mp4"
    assert hit.attribution == "Private archive"


def test_rows_to_hits_tolerates_comma_separated_tags_and_missing_fields():
    hit = rows_to_hits([{"clip_id": "x", "tags": "rain, neon"}])[0]
    assert hit.tags == ["rain", "neon"]
    assert hit.title == "Untitled clip"
    assert hit.raw_score is None
