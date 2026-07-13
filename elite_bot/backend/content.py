"""Prep-year content model: two semesters, five subjects each.

Subjects are declared here (the admin panel will later edit them) and each is
wired to an on-disk index via :class:`~services.search_engine.BookRef`. Semester
one points at the books already OCR-indexed for the bot, so search returns real
results immediately. Semester two's books are uploaded by the admin later.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from services.search_engine import BookRef, ScopeIndex, get_scope_index

# The single year this app serves.
YEAR_NAME = "السنة التحضيرية"

SEMESTER_FIRST = "first"
SEMESTER_SECOND = "second"
SEMESTERS = (SEMESTER_FIRST, SEMESTER_SECOND)


@dataclass(frozen=True, slots=True)
class Subject:
    """One subject within a semester. May hold several books."""

    id: str
    name_ar: str
    name_en: str
    #: Statically-configured books. A subject can have many (editions/years);
    #: admins add more via upload. Empty until content exists.
    books: tuple[BookRef, ...] = ()

    @property
    def has_content(self) -> bool:
        return bool(self.books)


def _demo_book(index_subject: str, display: str, pdf: str, name: str) -> BookRef:
    """A semester-one demo book (reuses the already-indexed البكالوريا PDFs)."""
    return BookRef(
        "البكالوريا", index_subject, display, pdf,
        book_id=pdf, book_name=name, academic_year="البكالوريا",
    )


# NOTE: semester-one subjects reuse the already-indexed البكالوريا books so the
# app demonstrates real search on day one. Edit `book_name`/`academic_year` to the
# real titles, and add more BookRefs per subject as books are digitized.
_FIRST_SUBJECTS = (
    Subject("physics", "الفيزياء", "Physics",
            (_demo_book("الفيزياء", "Physics", "phys.pdf", "الفيزياء — بكالوريا"),)),
    Subject("chemistry", "الكيمياء", "Chemistry",
            (_demo_book("الكيمياء", "Chemistry", "chem.pdf", "الكيمياء — بكالوريا"),)),
    Subject("history", "التاريخ", "History",
            (_demo_book("التاريخ", "History", "hist.pdf", "التاريخ — بكالوريا"),)),
    Subject("english", "الإنجليزية", "English",
            (_demo_book("Biology (English)", "English", "bio.pdf", "English — IGCSE"),)),
    Subject("biology", "علم الأحياء", "Biology",
            (_demo_book("علم الأحياء", "Biology", "bbio.pdf", "علم الأحياء — بكالوريا"),)),
)

# Semester two: السنة التحضيرية — الفصل الثاني
_SECOND_SUBJECTS = (
    Subject("physiology", "الفيزيولوجيا", "Physiology"),
    Subject("anatomy", "التشريح", "Anatomy"),
    Subject("genetics", "الوراثة", "Genetics"),
    Subject("statistics", "الإحصاء", "Statistics"),
    Subject("english", "الإنجليزية", "English"),
)

_BY_SEMESTER: dict[str, tuple[Subject, ...]] = {
    SEMESTER_FIRST: _FIRST_SUBJECTS,
    SEMESTER_SECOND: _SECOND_SUBJECTS,
}


def subjects_for(semester: str) -> tuple[Subject, ...]:
    return _BY_SEMESTER.get(semester, ())


def get_subject(semester: str, subject_id: str) -> Subject | None:
    return next((s for s in subjects_for(semester) if s.id == subject_id), None)


def index_scope_for_upload(semester: str) -> str:
    """The index ``grade`` slot used for admin-uploaded books in a semester."""
    return f"app_{semester}"


def resolve_books(semester: str, db: Session | None = None) -> tuple[BookRef, ...]:
    """Every book backing a semester: static books plus admin uploads.

    A subject may have several books; uploaded books are added alongside the
    static ones (not replacing them), so results can span multiple books per
    subject.
    """
    from backend.models import SubjectBook  # avoid a circular import at module load

    books: list[BookRef] = []
    for subject in subjects_for(semester):
        books.extend(subject.books)

    if db is not None:
        rows = (
            db.query(SubjectBook)
            .filter(SubjectBook.semester == semester, SubjectBook.status == "ready")
            .all()
        )
        for row in rows:
            subject = get_subject(semester, row.subject_id)
            display = subject.name_en if subject else row.subject_id
            books.append(BookRef(
                row.index_grade, row.index_subject, display, row.source_file,
                book_id=f"upload:{row.id}",
                book_name=row.book_name or display,
                academic_year=row.academic_year or "",
            ))
    return tuple(books)


def scope_index_for(semester: str, db: Session | None = None) -> ScopeIndex:
    """Cached search index over every book in a semester."""
    return get_scope_index(f"semester:{semester}", resolve_books(semester, db))


def is_valid_semester(semester: str) -> bool:
    return semester in SEMESTERS
