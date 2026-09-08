"""Merging and ranking the four result streams into one list.

The archive stream carries a real semantic score (cosine similarity from
ClickHouse). The public sources only give us their own ordering, so their base
score is positional and gets combined with lexical overlap against the planner's
keywords. Scores are therefore comparable-ish, not identical in kind — which is
why every card in the UI shows its source and its score.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .models import SearchHit, Source

# Nudges applied after scoring. The archive is the user's own footage: when
# relevance is close, their material should win.
SOURCE_PRIOR: dict[Source, float] = {
    Source.ARCHIVE: 1.00,
    Source.STOCK: 0.93,
    Source.PUBLIC_DOMAIN: 0.90,
    Source.YOUTUBE: 0.90,
}

_ARCHIVE_WEIGHTS = (0.75, 0.25)   # (semantic, lexical)
_EXTERNAL_WEIGHTS = (0.55, 0.45)  # (positional, lexical)
_POSITION_DECAY = 0.30

_STOPWORDS = frozenset("""
a an and are as at be by for from in into is it its of on or over shot the
this to with without at during near
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS or len(tok) < 3:
            continue
        out.add(tok)
        if len(tok) > 3 and tok.endswith("s"):
            out.add(tok[:-1])
    return out


def keywords_from_text(text: str, *, limit: int = 8) -> list[str]:
    """Keyword list straight from the raw query, in order, no LLM involved.

    Used when the planner is unavailable so ranking still has something to
    match on.
    """
    out: list[str] = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok in _STOPWORDS or len(tok) < 3 or tok in out:
            continue
        out.append(tok)
        if len(out) >= limit:
            break
    return out


def _hit_tokens(hit: SearchHit) -> set[str]:
    return _tokens(" ".join([hit.title, hit.description, " ".join(hit.tags)]))


def matched_terms(hit: SearchHit, keywords: Sequence[str]) -> list[str]:
    """Which planner keywords actually appear in this hit, in planner order."""
    have = _hit_tokens(hit)
    found: list[str] = []
    for kw in keywords:
        kw_tokens = _tokens(kw)
        if kw_tokens and kw_tokens & have:
            found.append(kw.strip().lower())
    return found


def lexical_overlap(hit: SearchHit, keywords: Sequence[str]) -> float:
    if not keywords:
        return 0.0
    return len(matched_terms(hit, keywords)) / len(keywords)


def positional_score(index: int) -> float:
    return 1.0 / (1.0 + _POSITION_DECAY * index)


def score_hits(hits: Sequence[SearchHit], keywords: Sequence[str]) -> None:
    """Assign `score` in place. Archive hits must already carry raw_score."""
    for index, hit in enumerate(hits):
        lexical = lexical_overlap(hit, keywords)
        if hit.source is Source.ARCHIVE:
            semantic = min(max(hit.raw_score or 0.0, 0.0), 1.0)
            w_sem, w_lex = _ARCHIVE_WEIGHTS
            base = w_sem * semantic + w_lex * lexical
        else:
            w_pos, w_lex = _EXTERNAL_WEIGHTS
            base = w_pos * positional_score(index) + w_lex * lexical
        hit.score = round(base * SOURCE_PRIOR.get(hit.source, 0.85), 4)


def deterministic_reason(hit: SearchHit, keywords: Sequence[str]) -> str:
    """Fallback for the 'why this matched' line — never fails, never lies."""
    terms = matched_terms(hit, keywords)[:4]
    if terms:
        return "matches: " + ", ".join(terms)
    if hit.source is Source.ARCHIVE and hit.raw_score is not None:
        return f"semantic match ({hit.raw_score:.0%} similarity)"
    return "close to your description"


def _dedupe(hits: Iterable[SearchHit]) -> list[SearchHit]:
    seen_keys: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    out: list[SearchHit] = []
    for hit in hits:
        key = (hit.source.value, hit.id)
        url = (hit.page_url or hit.clip_url or "").strip()
        if key in seen_keys or (url and url in seen_urls):
            continue
        seen_keys.add(key)
        if url:
            seen_urls.add(url)
        out.append(hit)
    return out


def _round_robin(groups: list[list[SearchHit]]) -> list[SearchHit]:
    """Interleave sources so the top of the grid shows the merge happening."""
    groups = [g for g in groups if g]
    groups.sort(key=lambda g: g[0].score, reverse=True)
    out: list[SearchHit] = []
    cursor = 0
    while any(cursor < len(g) for g in groups):
        for group in groups:
            if cursor < len(group):
                out.append(group[cursor])
        cursor += 1
    return out


def merge_results(
    hits_by_source: dict[Source, list[SearchHit]],
    keywords: Sequence[str],
    *,
    strategy: str = "diverse",
    limit: int = 24,
) -> list[SearchHit]:
    """Score each stream, then flatten into one ranked list."""
    groups: list[list[SearchHit]] = []
    for source in (Source.ARCHIVE, Source.STOCK, Source.PUBLIC_DOMAIN, Source.YOUTUBE):
        hits = _dedupe(hits_by_source.get(source, []))
        score_hits(hits, keywords)
        hits.sort(key=lambda h: h.score, reverse=True)
        for hit in hits:
            if not hit.match_reason:
                hit.match_reason = deterministic_reason(hit, keywords)
        groups.append(hits)

    if strategy == "score":
        ordered = sorted(
            (hit for group in groups for hit in group),
            key=lambda h: h.score,
            reverse=True,
        )
    else:
        ordered = _round_robin(groups)
    return ordered[:limit]
