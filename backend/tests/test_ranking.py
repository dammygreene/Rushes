"""Ranking is the part of the demo nobody can see, so it gets the most tests."""

from __future__ import annotations

from rushes.models import Source
from rushes.ranking import (
    deterministic_reason,
    keywords_from_text,
    lexical_overlap,
    matched_terms,
    merge_results,
    positional_score,
    score_hits,
)

KEYWORDS = ["rain", "neon", "night", "street"]


def test_keywords_from_text_drops_stopwords_and_keeps_order():
    assert keywords_from_text("a moody rain-soaked street at night") == [
        "moody",
        "rain",
        "soaked",
        "street",
        "night",
    ]


def test_keywords_from_text_is_capped():
    assert len(keywords_from_text(" ".join(f"word{n}" for n in range(20)), limit=4)) == 4


def test_matched_terms_handles_plurals_and_case(hit_factory):
    hit = hit_factory(Source.YOUTUBE, "Neon Signs In The Rain", description="wet city streets")
    assert matched_terms(hit, KEYWORDS) == ["rain", "neon", "street"]
    assert lexical_overlap(hit, KEYWORDS) == 0.75


def test_positional_score_decays():
    assert positional_score(0) == 1.0
    assert positional_score(1) < positional_score(0)
    assert positional_score(5) > 0


def test_archive_score_uses_similarity_and_beats_a_weaker_web_hit(hit_factory):
    archive = hit_factory(Source.ARCHIVE, "Rain on a neon street at night", raw_score=0.9)
    web = hit_factory(Source.YOUTUBE, "Unrelated cooking video")
    score_hits([archive], KEYWORDS)
    score_hits([web], KEYWORDS)
    assert archive.score > web.score


def test_deterministic_reason_never_invents(hit_factory):
    lexical = hit_factory(Source.STOCK, "Neon street in the rain")
    assert deterministic_reason(lexical, KEYWORDS) == "matches: rain, neon, street"

    semantic = hit_factory(Source.ARCHIVE, "Wet asphalt", raw_score=0.87)
    assert deterministic_reason(semantic, KEYWORDS) == "semantic match (87% similarity)"

    nothing = hit_factory(Source.YOUTUBE, "Unrelated")
    assert deterministic_reason(nothing, KEYWORDS) == "close to your description"


def test_merge_dedupes_by_url_and_fills_reasons(hit_factory):
    first = hit_factory(Source.YOUTUBE, "Neon rain", page_url="https://x.test/a")
    duplicate = hit_factory(Source.YOUTUBE, "Neon rain again", page_url="https://x.test/a")
    merged = merge_results({Source.YOUTUBE: [first, duplicate]}, KEYWORDS)
    assert len(merged) == 1
    assert merged[0].match_reason


def test_merge_interleaves_sources_then_respects_the_limit(hit_factory):
    archive = [hit_factory(Source.ARCHIVE, f"rain night street {n}", raw_score=0.9) for n in range(3)]
    youtube = [hit_factory(Source.YOUTUBE, f"neon rain {n}") for n in range(3)]
    merged = merge_results(
        {Source.ARCHIVE: archive, Source.YOUTUBE: youtube}, KEYWORDS, limit=4
    )
    assert len(merged) == 4
    assert {hit.source for hit in merged[:2]} == {Source.ARCHIVE, Source.YOUTUBE}


def test_merge_by_score_puts_the_best_first(hit_factory):
    weak = hit_factory(Source.ARCHIVE, "unrelated", raw_score=0.1)
    strong = hit_factory(Source.STOCK, "rain neon night street")
    merged = merge_results(
        {Source.ARCHIVE: [weak], Source.STOCK: [strong]}, KEYWORDS, strategy="score"
    )
    assert merged[0] is strong
