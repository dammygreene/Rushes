"""Offline pipeline: create the schema, fetch sample clips, caption, embed, seed.

None of this runs in the request path. Entry points:

    python -m rushes.pipeline.create_schema
    python -m rushes.pipeline.seed --per-query 2
    rushes-doctor
"""
