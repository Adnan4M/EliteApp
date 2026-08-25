"""Content model: academic years, semesters, and subjects.

Adding a new year
-----------------
1. Define ``_<YEAR>_FIRST_SUBJECTS`` and ``_<YEAR>_SECOND_SUBJECTS`` tuples.
2. Add both entries to ``_BY_YEAR_SEMESTER``.

That is the whole change. ``available_years()`` derives visibility from
``_BY_YEAR_SEMESTER``, the ``/me`` response carries it to the app, and the app
renders only what it is told. A year with no subjects is invisible to users and
404s if requested directly — so partial content can never leak early.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from services.search_engine import BookRef, ScopeIndex, get_scope_index

# ── Year / semester identifiers ───────────────────────────────────────────────

YEAR_PREP   = "prep"
YEAR_1      = "year1"
YEAR_2      = "year2"
YEAR_3      = "year3"
YEAR_4      = "year4"
YEAR_5      = "year5"
YEAR_6      = "year6"

SEMESTER_FIRST  = "first"
SEMESTER_SECOND = "second"
SEMESTERS = (SEMESTER_FIRST, SEMESTER_SECOND)

# Display names for every year the platform will ever serve. A year appearing
# here is NOT enough to make it visible — see ``available_years()``, which only
# returns years that actually have subjects wired up in ``_BY_YEAR_SEMESTER``.
YEAR_LABELS: dict[str, str] = {
    YEAR_PREP: "السنة التحضيرية",
    YEAR_1:    "السنة الأولى",
    YEAR_2:    "السنة الثانية",
    YEAR_3:    "السنة الثالثة",
    YEAR_4:    "السنة الرابعة",
    YEAR_5:    "السنة الخامسة",
    YEAR_6:    "السنة السادسة",
}


# ── Subject dataclass ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Subject:
    """One subject within a (year, semester)."""

    id: str
    name_ar: str
    name_en: str
    books: tuple[BookRef, ...] = ()

    @property
    def has_content(self) -> bool:
        return bool(self.books)


def _book(year_label: str, index_subject: str, display: str, pdf: str, name: str) -> BookRef:
    return BookRef(
        year_label, index_subject, display, pdf,
        book_id=pdf, book_name=name, academic_year=year_label,
    )


def _prep_book(index_subject: str, display: str, pdf: str, name: str) -> BookRef:
    return _book(YEAR_LABELS[YEAR_PREP], index_subject, display, pdf, name)


# ── Prep year subjects ────────────────────────────────────────────────────────

_PREP_FIRST_SUBJECTS: tuple[Subject, ...] = (
    Subject("physics", "الفيزياء", "Physics",
            (_prep_book("الفيزياء", "Physics", "phys.pdf", "الفيزياء — السنة التحضيرية"),)),
    Subject("chemistry", "الكيمياء", "Chemistry",
            (_prep_book("الكيمياء", "Chemistry", "chem.pdf", "الكيمياء — السنة التحضيرية"),)),
    Subject("history", "التاريخ", "History",
            (_prep_book("التاريخ", "History", "hist.pdf", "التاريخ — السنة التحضيرية"),)),
    Subject("english", "الإنجليزية", "English",
            (_prep_book("Biology (English)", "English", "bio.pdf", "English — Prep Year"),)),
    Subject("biology", "علم الأحياء", "Biology",
            (_prep_book("علم الأحياء", "Biology", "bbio.pdf", "علم الأحياء — السنة التحضيرية"),)),
)

_PREP_SECOND_SUBJECTS: tuple[Subject, ...] = (
    Subject("physiology", "الفيزيولوجيا", "Physiology"),
    Subject("anatomy",    "التشريح",      "Anatomy"),
    Subject("genetics",   "الوراثة",      "Genetics"),
    Subject("statistics", "الإحصاء",      "Statistics"),
    Subject("english",    "الإنجليزية",   "English"),
)

# ── Registry ──────────────────────────────────────────────────────────────────
# Add new years here as (year_id, semester) → subjects mapping.

_BY_YEAR_SEMESTER: dict[tuple[str, str], tuple[Subject, ...]] = {
    (YEAR_PREP, SEMESTER_FIRST):  _PREP_FIRST_SUBJECTS,
    (YEAR_PREP, SEMESTER_SECOND): _PREP_SECOND_SUBJECTS,
    # Future years:
    # (YEAR_1, SEMESTER_FIRST):  _YEAR1_FIRST_SUBJECTS,
    # (YEAR_1, SEMESTER_SECOND): _YEAR1_SECOND_SUBJECTS,
}


# ── Public API ────────────────────────────────────────────────────────────────

def subjects_for(semester: str, *, year: str = YEAR_PREP) -> tuple[Subject, ...]:
    return _BY_YEAR_SEMESTER.get((year, semester), ())


def get_subject(semester: str, subject_id: str, *, year: str = YEAR_PREP) -> Subject | None:
    return next((s for s in subjects_for(semester, year=year) if s.id == subject_id), None)


def is_valid_semester(semester: str) -> bool:
    return semester in SEMESTERS


def available_years() -> tuple[str, ...]:
    """Years that actually have subjects wired up, in YEAR_LABELS order.

    This is the single source of truth for what the app is allowed to show.
    A year becomes visible the moment its subjects are added to
    ``_BY_YEAR_SEMESTER`` — no other code needs to change.
    """
    with_content = {year for (year, _semester) in _BY_YEAR_SEMESTER}
    return tuple(y for y in YEAR_LABELS if y in with_content)


def is_valid_year(year: str) -> bool:
    """Only years with real content are valid; others 404 rather than 200-empty."""
    return year in available_years()


def year_label(year: str) -> str:
    return YEAR_LABELS.get(year, year)


def index_scope_for_upload(semester: str, *, year: str = YEAR_PREP) -> str:
    """The index ``grade`` slot used for admin-uploaded books.

    The prep year keeps the legacy un-namespaced form (``app_first``) because
    books are already indexed on disk under it; adding the year segment would
    orphan those indexes. Later years are namespaced from the start.
    """
    if year == YEAR_PREP:
        return f"app_{semester}"
    return f"app_{year}_{semester}"


# NOTE: ``db`` stays the second positional parameter and ``year`` is keyword-only.
# Existing callers use ``resolve_books(semester, db)`` / ``scope_index_for(semester, db)``;
# inserting ``year`` positionally would silently bind the Session to ``year``.
def resolve_books(semester: str, db: Session | None = None, *, year: str = YEAR_PREP) -> tuple[BookRef, ...]:
    """Every book backing a (year, semester): static books plus admin uploads."""
    from backend.models import SubjectBook  # avoid circular import

    books: list[BookRef] = []
    for subject in subjects_for(semester, year=year):
        books.extend(subject.books)

    if db is not None:
        rows = (
            db.query(SubjectBook)
            .filter(
                SubjectBook.year == year,
                SubjectBook.semester == semester,
                SubjectBook.status == "ready",
            )
            .all()
        )
        for row in rows:
            subject = get_subject(semester, row.subject_id, year=year)
            display = subject.name_en if subject else row.subject_id
            books.append(BookRef(
                row.index_grade, row.index_subject, display, row.source_file,
                book_id=f"upload:{row.id}",
                book_name=row.book_name or display,
                academic_year=row.academic_year or "",
            ))
    return tuple(books)


def scope_index_for(semester: str, db: Session | None = None, *, year: str = YEAR_PREP) -> ScopeIndex:
    """Cached search index over every book in a (year, semester)."""
    return get_scope_index(
        f"year:{year}:semester:{semester}",
        resolve_books(semester, db, year=year),
    )
