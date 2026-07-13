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

    @property
    def occurrences(self) -> int:
        return len(self.matched_words)


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


class SearchEngine:
    """Keyword search over a scope's pages, optionally reranked semantically."""

    def __init__(self, semantic: "SemanticRanker | None" = None) -> None:
        self._semantic = semantic

    def search(self, query: str, index: ScopeIndex, limit: int = MAX_HITS) -> list[PageHit]:
        """Find every page in ``index`` mentioning ``query``, best first."""
        tokens = tokenize(query)
        if not tokens or index.is_empty:
            return []

        hits: list[PageHit] = []
        for page_idx in index.candidates(tokens):
            page = index.pages[page_idx]
            matched = tuple(
                word
                for word, norm in zip(page.words, page.normalized_words)
                if norm and any(token in norm for token in tokens)
            )
            if not matched:
                continue
            confidence = sum(w.confidence for w in matched) / len(matched)
            hits.append(
                PageHit(
                    scope=index.scope_id,
                    subject=page.subject,
                    source=page.source,
                    page=page.page,
                    printed=page.printed,
                    score=len(matched) + confidence / 1000.0,
                    matched_words=matched,
                    book_id=page.book_id,
                    book_name=page.book_name,
                    academic_year=page.academic_year,
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
