"""Smart search: suggestions, keyword search, and highlighted page images.

Access is gated per semester. The heavy page render (open PDF, draw highlight
boxes) happens here on the server and is streamed to the app as a PNG, so the
client never handles raw PDFs.
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.content import get_subject, is_valid_semester, scope_index_for
from backend.deps import current_user, get_db, has_semester_access
from backend.models import AppUser
from backend.schemas import (
    ExplanationOut,
    LocationOut,
    MCQOut,
    QuestionsOut,
    SearchOut,
    SummaryOut,
    SuggestOut,
)
from services.summarize import extractive_summary
from config import settings
from services.ai import AIError, AINotConfigured, AIQuotaError, get_study_ai
from services.pdf_engine import PdfEngine
from services.search_engine import ScopeIndex, SearchEngine
from services.search_session import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])
_engine = SearchEngine()


def _require_access(db: Session, user: AppUser, semester: str) -> None:
    if not is_valid_semester(semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    if not has_semester_access(db, user, semester):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"no active subscription for the {semester} semester",
        )


@router.get("/suggest", response_model=SuggestOut)
def suggest(
    semester: str = Query(...),
    q: str = Query(..., min_length=1),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> SuggestOut:
    _require_access(db, user, semester)
    index = scope_index_for(semester, db)
    return SuggestOut(suggestions=_engine.suggest(q, index))


@router.post("", response_model=SearchOut)
def search(
    semester: str = Query(...),
    keyword: str = Query(..., min_length=1),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> SearchOut:
    _require_access(db, user, semester)
    index = scope_index_for(semester, db)
    hits = _engine.search(keyword, index)

    if not hits:
        return SearchOut(query=keyword, query_id="", total=0, summary=None, locations=[])

    query_id = store.create(keyword, f"semester:{semester}", hits)

    # Build chapter lookup: {(subject_id, semester): [SubjectChapter rows]}
    from backend.models import SubjectChapter as _SC
    _chapter_rows = db.query(_SC).filter(_SC.semester == semester).all()
    _chapters_by_subject: dict[str, list] = {}
    for _ch in _chapter_rows:
        _chapters_by_subject.setdefault(_ch.subject_id, []).append(_ch)

    def _find_chapter(subject_id: str, printed_page: str, chapter_header: str):
        """Return (chapter_number, chapter_name) for a hit, or (None, None)."""
        chapters = _chapters_by_subject.get(subject_id, [])
        if not chapters:
            return None, None
        # Try page range match first
        try:
            pg = int(printed_page)
            for ch in chapters:
                if ch.page_start and ch.page_end and ch.page_start <= pg <= ch.page_end:
                    return ch.chapter_number, ch.chapter_name
        except (ValueError, TypeError):
            pass
        # Fall back to header text match
        if chapter_header:
            header_lower = chapter_header.strip()
            for ch in chapters:
                if ch.chapter_name and ch.chapter_name.strip() == header_lower:
                    return ch.chapter_number, ch.chapter_name
        return None, None

    locations = []
    for i, hit in enumerate(hits):
        sid = _subject_id(semester, hit.subject)
        ch_num, ch_name = _find_chapter(sid, hit.printed, hit.chapter_header)
        locations.append(LocationOut(
            semester=semester,
            subject_id=sid,
            subject_name=hit.subject,
            book_id=hit.book_id,
            book_name=hit.book_name or hit.subject,
            academic_year=hit.academic_year,
            source=hit.source,
            page=hit.page,
            printed=hit.printed,
            occurrences=hit.occurrences,
            position=i,
            chapter_header=hit.chapter_header,
            chapter_number=ch_num,
            chapter_name=ch_name,
        ))
    summary = extractive_summary(keyword, index, hits)
    return SearchOut(
        query=keyword, query_id=query_id, total=len(hits), summary=summary, locations=locations
    )


def _gather_context(index: ScopeIndex, keyword: str, max_pages: int = 12) -> list[str]:
    """Text of the top pages mentioning ``keyword``, for grounding the AI."""
    hits = _engine.search(keyword, index, limit=max_pages)
    by_key = {(p.subject, p.page): p.text for p in index.pages}
    return [by_key.get((h.subject, h.page), "") for h in hits]


@router.post("/summary", response_model=SummaryOut)
def summary(
    semester: str = Query(...),
    keyword: str = Query(..., min_length=1),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> SummaryOut:
    _require_access(db, user, semester)
    index = scope_index_for(semester, db)
    contexts = _gather_context(index, keyword)
    if not contexts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "keyword not found in this semester")

    ai = get_study_ai()
    if ai.available():
        try:
            return SummaryOut(
                keyword=keyword,
                summary=ai.summary(keyword, contexts, scope=semester),
                ai_generated=True,
            )
        except (AINotConfigured, AIError) as exc:
            logger.warning("AI summary failed, using extractive fallback: %s", exc)

    # Fallback: the non-AI extractive summary always works.
    hits = _engine.search(keyword, index)
    text = extractive_summary(keyword, index, hits) or "—"
    return SummaryOut(keyword=keyword, summary=text, ai_generated=False)


@router.post("/explanation", response_model=ExplanationOut)
def explanation(
    semester: str = Query(...),
    keyword: str = Query(..., min_length=1),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ExplanationOut:
    _require_access(db, user, semester)
    index = scope_index_for(semester, db)
    contexts = _gather_context(index, keyword)
    # If keyword isn't in the book, pass empty context — AI answers from general knowledge.

    ai = get_study_ai()
    if not ai.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "AI features are not configured (set GEMINI_API_KEY)")
    try:
        exp = ai.explanation(keyword, contexts, scope=semester)
    except AIQuotaError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "AI daily limit reached — please try again later")
    except AIError as exc:
        if str(exc) == "not_scientific":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "not_scientific")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")
    except AINotConfigured as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")
    return ExplanationOut(
        keyword=keyword, simple=exp.simple, advanced=exp.advanced,
        real_life=exp.real_life, related=exp.related,
    )


@router.post("/questions", response_model=QuestionsOut)
def questions(
    semester: str = Query(...),
    keyword: str = Query(..., min_length=1),
    count: int = Query(6, ge=1, le=12),
    refresh: bool = Query(False, description="bypass cache and generate a new set"),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> QuestionsOut:
    _require_access(db, user, semester)
    index = scope_index_for(semester, db)
    contexts = _gather_context(index, keyword)

    ai = get_study_ai()
    if not ai.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "AI features are not configured (set GEMINI_API_KEY)")
    try:
        mcqs = ai.questions(keyword, contexts, n=count, scope=semester, force=refresh)
    except AIQuotaError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "AI daily limit reached — please try again later")
    except (AINotConfigured, AIError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")
    return QuestionsOut(
        keyword=keyword,
        questions=[MCQOut(question=m.question, options=m.options,
                          correct_index=m.correct_index, difficulty=m.difficulty)
                   for m in mcqs],
    )


@router.get("/page")
def page_image(
    semester: str = Query(...),
    subject_id: str = Query(...),
    page: int = Query(..., ge=0),
    query: str = Query(...),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Return the highlighted PNG for one search result page (stateless)."""
    from backend.models import SubjectBook

    book = (
        db.query(SubjectBook)
        .filter(SubjectBook.semester == semester, SubjectBook.subject_id == subject_id)
        .first()
    )
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "book not found")

    # Re-run keyword search for the semester, filter to this subject+page.
    # Match on source file, not display_subject — display_subject may be the
    # English name ("Physiology") while subject_id is the key ("physiology").
    index = scope_index_for(semester, db)
    all_hits = _engine.search(query, index) if index else []
    hit = next(
        (h for h in all_hits if h.source == book.source_file and h.page == page),
        None,
    )

    if hit is None:
        # Fall back: render without highlights if page somehow not found.
        source = book.source_file
        if not source:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no PDF for this subject")
        png = _render_page_raw(source, page)
    else:
        png = _render_page(hit)

    return StreamingResponse(io.BytesIO(png), media_type="image/png")


def _subject_id(semester: str, subject_name: str) -> str:
    from backend.content import subjects_for

    match = next(
        (s for s in subjects_for(semester)
         if subject_name in (s.name_en, s.name_ar)),
        None,
    )
    return match.id if match else subject_name


def _render_page_raw(source: str, page: int) -> bytes:
    safe_source = source.replace("/", "_").replace("\\", "_")
    cache = settings.cache_dir / f"{safe_source}_{page}_0.png"
    if cache.exists():
        return cache.read_bytes()
    with PdfEngine(settings.pdf_dir / source, dpi=settings.render_dpi) as pdf:
        png = pdf.render_page(page, highlights=[], scale=0.6)
    try:
        cache.write_bytes(png)
    except OSError:
        pass
    return png


def _render_page(hit) -> bytes:
    safe_source = hit.source.replace("/", "_").replace("\\", "_")
    cache = settings.cache_dir / f"{safe_source}_{hit.page}_{len(hit.matched_words)}.png"
    if cache.exists():
        return cache.read_bytes()
    with PdfEngine(settings.pdf_dir / hit.source, dpi=settings.render_dpi) as pdf:
        png = pdf.render_page(hit.page, highlights=hit.matched_words, scale=0.6)
    try:
        cache.write_bytes(png)
    except OSError:
        logger.warning("could not cache render at %s", cache)
    return png
