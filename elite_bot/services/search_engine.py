"""Curriculum search across every indexed page of a *scope*.

A "scope" is any named set of books — a school grade for the bot, or a semester
for the app. Keyword search runs against normalized OCR/native text, so a query
typed without hamza or harakat still matches the printed form. Each hit carries
the word boxes needed to highlight the term on the rendered page.

Semantic search (FAISS + sentence-transformers) plugs in through
:class:`SemanticRanker`; when no embedding model is available the engine
degrades gracefully to keyword-only rather than failing.
"""

from __future__ import annotations

import functools
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

import yaml

from config import settings
from indexer import iter_index
from services.ocr_engine import Word
from utils.arabic import normalize, tokenize

logger = logging.getLogger(__name__)

#: Cap on hits returned, before grouping by subject.
MAX_HITS = 40


@dataclass(frozen=True, slots=True)
class BookRef:
    """Points a display subject at an on-disk index file.

    ``index_grade`` / ``index_subject`` name the ``indexes/{grade}__{subject}``
    files produced by the indexer; ``display_subject`` is what the user sees
    (e.g. index subject ``الفيزياء`` shown to the app as ``Physics``).
    """

    index_grade: str
    index_subject: str
    display_subject: str
    source_file: str  # the PDF filename, needed to render/highlight pages
    # Book identity: a subject may have several books (different editions/years),
    # so results are grouped by the book, not just the subject.
    book_id: str = ""
    book_name: str = ""
    academic_year: str = ""

    def resolved_id(self) -> str:
        return self.book_id or self.source_file

    def resolved_name(self) -> str:
        return self.book_name or self.display_subject


@dataclass(frozen=True, slots=True)
class PageHit:
    """One page containing the query, with the boxes of the matching words."""

    scope: str
    subject: str
    source: str
    page: int
    printed: str
    score: float
    matched_words: tuple[Word, ...]
    book_id: str = ""
    book_name: str = ""
    academic_year: str = ""
    chapter_header: str = ""

    @property
    def occurrences(self) -> int:
        return len(self.matched_words)


def _extract_chapter_header(words: tuple[Word, ...]) -> str:
    """Return the running chapter title from the topmost text line of a page.

    Arabic textbooks print the chapter (or unit) name as a header on every page.
    We find it by taking the topmost words, skipping pure page-number digits, and
    capping to a reasonable word count so we never capture body text.
    """
    if not words:
        return ""
    heights = [w.height for w in words]
    median_h = sorted(heights)[len(heights) // 2] if heights else 30
    line_h = max(int(median_h * 1.8), 25)

    min_top = min(w.top for w in words)

    def _line_words(top_from: int) -> list[str]:
        line = [w for w in words if top_from <= w.top <= top_from + line_h]
        return [w.text for w in sorted(line, key=lambda w: w.left, reverse=True)
                if not w.text.strip().isdigit() and len(w.text.strip()) > 1]

    header = _line_words(min_top)
    if not header:
        # Page number might occupy the very first line; try the next line down
        next_tops = [w.top for w in words if w.top > min_top + line_h]
        if next_tops:
            header = _line_words(min(next_tops))

    return " ".join(header[:8]).strip()


@dataclass(slots=True)
class IndexedPage:
    subject: str
    source: str
    page: int
    printed: str
    text: str
    words: tuple[Word, ...]
    book_id: str = ""
    book_name: str = ""
    academic_year: str = ""
    chapter_header: str = ""
    normalized_words: tuple[str, ...] = field(default=(), repr=False)


def _books_for_grade(grade: str) -> tuple[BookRef, ...]:
    """Every book in one grade of ``curriculum.yaml`` (used by the bot)."""
    path = settings.pdf_dir / "curriculum.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    subjects = ((data.get("grades") or {}).get(grade) or {}).get("subjects") or {}
    return tuple(
        BookRef(grade, subject, subject, meta["file"],
                book_id=meta["file"], book_name=meta.get("book_name", subject),
                academic_year=meta.get("academic_year", grade))
        for subject, meta in subjects.items()
    )


class ScopeIndex:
    """All indexed pages for one scope, held in memory with a token→pages map."""

    def __init__(self, scope_id: str, books: tuple[BookRef, ...]) -> None:
        self.scope_id = scope_id
        self.pages: list[IndexedPage] = []
        self._postings: dict[str, set[int]] = defaultdict(set)
        self._load(books)

    def _load(self, books: tuple[BookRef, ...]) -> None:
        for book in books:
            for record in iter_index(book.index_grade, book.index_subject):
                words = tuple(
                    Word(text=t, left=l, top=tp, width=w, height=h, confidence=c)
                    for t, l, tp, w, h, c in record["words"]
                )
                normalized = tuple(normalize(w.text) for w in words)
                idx = len(self.pages)
                self.pages.append(
                    IndexedPage(
                        subject=book.display_subject,
                        source=book.source_file,
                        page=record["page"],
                        printed=str(record.get("printed", record["page"] + 1)),
                        text=record["text"],
                        words=words,
                        book_id=book.resolved_id(),
                        book_name=book.resolved_name(),
                        academic_year=book.academic_year,
                        chapter_header=_extract_chapter_header(words),
                        normalized_words=normalized,
                    )
                )
                for token in normalized:
                    if token:
                        self._postings[token].add(idx)
        logger.info("scope %s: %d indexed pages loaded", self.scope_id, len(self.pages))

    @property
    def is_empty(self) -> bool:
        return not self.pages

    def candidates(self, query_tokens: Iterable[str]) -> set[int]:
        """Pages whose words contain any query token (exact or as a substring)."""
        found: set[int] = set()
        for token in query_tokens:
            if token in self._postings:
                found |= self._postings[token]
            else:
                for key, pages in self._postings.items():
                    if token in key:
                        found |= pages
        return found


@functools.lru_cache(maxsize=16)
def _cached_scope(scope_id: str, books: tuple[BookRef, ...]) -> ScopeIndex:
    return ScopeIndex(scope_id, books)


def get_scope_index(scope_id: str, books: tuple[BookRef, ...]) -> ScopeIndex:
    """Cached index for an explicit set of books (used by the app backend)."""
    return _cached_scope(scope_id, tuple(books))


def get_grade_index(grade: str) -> ScopeIndex:
    """Cached index for a whole curriculum grade (used by the bot)."""
    return _cached_scope(grade, _books_for_grade(grade))


def reload_indexes() -> None:
    """Drop cached indexes, e.g. after re-running the indexer."""
    _cached_scope.cache_clear()


def _proximity_score(page: IndexedPage, tokens: list[str], window: int = 5) -> float:
    """Score how close the tokens appear to each other on the page.

    Finds the smallest span (in word positions) that contains one occurrence
    of every token. A span of 0 or 1 means adjacent words (phrase match).
    Returns a score in (0, 1] — closer = higher. Returns 0 if any token is
    missing or all occurrences are further apart than ``window``.
    """
    # Position lists: indices in page.normalized_words where each token matches.
    positions: list[list[int]] = []
    for token in tokens:
        pos = [i for i, norm in enumerate(page.normalized_words)
               if norm and token in norm]
        if not pos:
            return 0.0
        positions.append(pos)

    # Sliding-window approach: advance the pointer for the token with the
    # smallest current index until we've tried every combination efficiently.
    import heapq
    # Build a min-heap of (position, token_index, list_cursor).
    heap = [(pos[0], ti, 0) for ti, pos in enumerate(positions)]
    heapq.heapify(heap)
    max_pos = max(pos[0] for pos in positions)
    best_span = max_pos - heap[0][0]

    while True:
        min_pos, ti, cursor = heapq.heappop(heap)
        span = max_pos - min_pos
        if span < best_span:
            best_span = span
        if best_span == 0:
            break
        cursor += 1
        if cursor >= len(positions[ti]):
            break
        new_pos = positions[ti][cursor]
        heapq.heappush(heap, (new_pos, ti, cursor))
        max_pos = max(max_pos, new_pos)

    if best_span > window:
        return 0.0
    return 1.0 - best_span / (window + 1)


class SearchEngine:
    """Keyword search over a scope's pages, optionally reranked semantically."""

    def __init__(self, semantic: "SemanticRanker | None" = None) -> None:
        self._semantic = semantic

    def search(self, query: str, index: ScopeIndex, limit: int = MAX_HITS) -> list[PageHit]:
        """Find pages mentioning ``query``, best first.

        Single-word: substring match anywhere on page.
        Multi-word: AND (all tokens on page) + proximity scoring so pages
        where the words appear near each other rank first.
        """
        tokens = tokenize(query)
        if not tokens or index.is_empty:
            return []

        if len(tokens) > 1:
            candidate_sets = [index.candidates([t]) for t in tokens]
            page_indices = candidate_sets[0]
            for s in candidate_sets[1:]:
                page_indices = page_indices & s
        else:
            page_indices = index.candidates(tokens)

        hits: list[PageHit] = []
        for page_idx in page_indices:
            page = index.pages[page_idx]
            matched = tuple(
                word
                for word, norm in zip(page.words, page.normalized_words)
                if norm and any(token in norm for token in tokens)
            )
            if not matched:
                continue
            confidence = sum(w.confidence for w in matched) / len(matched)
            proximity = _proximity_score(page, tokens) if len(tokens) > 1 else 0
            hits.append(
                PageHit(
                    scope=index.scope_id,
                    subject=page.subject,
                    source=page.source,
                    page=page.page,
                    printed=page.printed,
                    # proximity bonus: pages where words appear close together rank first
                    score=len(matched) + confidence / 1000.0 + proximity * 10,
                    matched_words=matched,
                    book_id=page.book_id,
                    book_name=page.book_name,
                    academic_year=page.academic_year,
                    chapter_header=page.chapter_header,
                )
            )

        if self._semantic is not None:
            hits = self._semantic.rerank(query, index, hits)

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def suggest(self, prefix: str, index: ScopeIndex, limit: int = 8) -> list[str]:
        """Autocomplete: indexed words beginning with the typed prefix."""
        norm = normalize(prefix)
        if not norm:
            return []
        counts: dict[str, int] = defaultdict(int)
        display: dict[str, str] = {}
        for page in index.pages:
            for word, wnorm in zip(page.words, page.normalized_words):
                if wnorm.startswith(norm) and len(wnorm) >= len(norm):
                    counts[wnorm] += 1
                    display.setdefault(wnorm, word.text)
        top = sorted(counts, key=lambda k: counts[k], reverse=True)[:limit]
        return [display[k] for k in top]

    @staticmethod
    def group_by_subject(hits: Iterable[PageHit]) -> dict[str, list[PageHit]]:
        grouped: dict[str, list[PageHit]] = defaultdict(list)
        for hit in hits:
            grouped[hit.subject].append(hit)
        for pages in grouped.values():
            pages.sort(key=lambda h: h.page)
        return dict(grouped)


class SemanticRanker:
    """Optional FAISS/embedding reranker. A missing model is a no-op."""

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning("sentence-transformers not installed; semantic rerank disabled")
            return False
        self._model = SentenceTransformer(self.model_name)
        return True

    def rerank(self, query: str, index: ScopeIndex, hits: list[PageHit]) -> list[PageHit]:
        if not hits or not self._ensure_model():
            return hits
        import numpy as np

        by_key = {(p.subject, p.page): p.text for p in index.pages}
        texts = [by_key.get((h.subject, h.page), "") for h in hits]
        vectors = self._model.encode([query] + texts, normalize_embeddings=True)
        query_vec, page_vecs = vectors[0], np.asarray(vectors[1:])
        sims = page_vecs @ query_vec
        return [
            PageHit(
                scope=h.scope, subject=h.subject, source=h.source, page=h.page,
                printed=h.printed, score=h.score + 10.0 * float(sim),
                matched_words=h.matched_words, book_id=h.book_id,
                book_name=h.book_name, academic_year=h.academic_year,
            )
            for h, sim in zip(hits, sims)
        ]
