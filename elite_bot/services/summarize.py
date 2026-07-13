"""Lightweight extractive summary of a keyword across the curriculum.

This is the non-AI baseline for the app's "Summary" feature: pull the lines that
mention the keyword from the matching pages, deduplicate near-identical ones, and
join a handful into a short passage. When an AI provider is configured it can
replace this with a generated summary; the interface stays the same.
"""

from __future__ import annotations

import re

from services.search_engine import PageHit, ScopeIndex
from utils.arabic import normalize

_MAX_SENTENCES = 6
_MIN_LEN = 25
_MAX_LEN = 300


def _split_lines(text: str) -> list[str]:
    parts = re.split(r"[\n.।؟!]+", text)
    return [p.strip() for p in parts if p.strip()]


def extractive_summary(keyword: str, index: ScopeIndex, hits: list[PageHit]) -> str | None:
    """Return a short deduped passage of curriculum lines mentioning ``keyword``."""
    norm_kw = normalize(keyword)
    if not norm_kw:
        return None

    text_by_page = {(p.subject, p.page): p.text for p in index.pages}

    seen: set[str] = set()
    picked: list[str] = []
    for hit in hits:
        text = text_by_page.get((hit.subject, hit.page), "")
        for line in _split_lines(text):
            if not (_MIN_LEN <= len(line) <= _MAX_LEN):
                continue
            if norm_kw not in normalize(line):
                continue
            # Dedup on a normalized fingerprint so OCR noise doesn't defeat it.
            fingerprint = normalize(line)[:60]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            picked.append(line)
            if len(picked) >= _MAX_SENTENCES:
                break
        if len(picked) >= _MAX_SENTENCES:
            break

    if not picked:
        return None
    return "\n".join(f"• {line}" for line in picked)
