"""Admin: issue activation codes and post notifications.

Guarded by a static admin key (``APP_ADMIN_KEY`` env) sent as ``X-Admin-Key``.
This is deliberately simple; a full admin-user system can replace it later.
"""

from __future__ import annotations

import logging
import re
import secrets
import string
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

import datetime

from backend.content import (
    get_subject,
    index_scope_for_upload,
    is_valid_semester,
    subjects_for,
)
from backend.deps import get_db
from backend.models import (
    ActivationCode,
    AppUser,
    Notification,
    SemesterAccess,
    SubjectBook,
)
from backend.schemas import (
    BookStatusOut,
    CodeOut,
    CreateCodeIn,
    CreateCodeOut,
    GrantAccessIn,
    GrantAccessOut,
    UserOut,
    StatsOut,
    SubjectStatusOut,
)
from config import settings
from database import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_ALPHABET = string.ascii_uppercase + string.digits  # no lowercase; codes are typed
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


def _require_admin(x_admin_key: str = Header(default="")) -> None:
    if not settings.app_admin_key or not secrets.compare_digest(
        x_admin_key, settings.app_admin_key
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin key required")


def _generate_code(length: int = 10) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


@router.post("/codes", response_model=CreateCodeOut, dependencies=[Depends(_require_admin)])
def create_codes(body: CreateCodeIn, db: Session = Depends(get_db)) -> CreateCodeOut:
    if not is_valid_semester(body.semester):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown semester")

    codes: list[str] = []
    for _ in range(body.count):
        # Retry on the rare collision with the unique constraint.
        for _attempt in range(5):
            value = _generate_code()
            if not db.query(ActivationCode).filter(ActivationCode.code == value).first():
                break
        else:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "code generation failed")
        db.add(
            ActivationCode(
                code=value,
                semester=body.semester,
                max_uses=body.max_uses,
                valid_days=body.valid_days,
            )
        )
        codes.append(value)
    db.commit()
    return CreateCodeOut(codes=codes)


@router.post("/codes/{code}/disable", dependencies=[Depends(_require_admin)])
def disable_code(code: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.query(ActivationCode).filter(ActivationCode.code == code).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "code not found")
    row.enabled = False
    db.commit()
    return {"status": "disabled"}


@router.post("/notifications", dependencies=[Depends(_require_admin)])
def post_notification(title: str, body: str, db: Session = Depends(get_db)) -> dict[str, int]:
    note = Notification(title=title, body=body)
    db.add(note)
    db.commit()
    return {"id": note.id}


# -- PDF upload + indexing -------------------------------------------------
def _index_book_task(book_id: int) -> None:
    """Background worker: OCR-index an uploaded PDF and mark the row ready.

    Runs in a threadpool thread with its own DB session, using the thread-based
    :func:`indexer.index_pdf` so it is safe inside the running server.
    """
    from indexer import index_pdf
    from services.search_engine import reload_indexes

    db = SessionLocal()
    try:
        book = db.get(SubjectBook, book_id)
        if book is None:
            return
        pdf_path = settings.pdf_dir / book.source_file

        def _progress(done: int, total: int) -> None:
            row = db.get(SubjectBook, book_id)
            if row is not None:
                row.pages_indexed, row.pages_total = done, total
                db.commit()

        indexed, total = index_pdf(
            grade=book.index_grade,
            subject=book.index_subject,
            pdf_path=pdf_path,
            ocr_lang=book.ocr_lang,
            has_text_layer=book.has_text_layer,
            progress=_progress,
        )
        row = db.get(SubjectBook, book_id)
        row.pages_indexed, row.pages_total = indexed, total
        row.status = "ready"
        row.error = None
        db.commit()
        reload_indexes()  # new pages become searchable
        logger.info("indexed upload for %s/%s: %d/%d pages",
                    row.semester, row.subject_id, indexed, total)
    except Exception as exc:  # noqa: BLE001 -- record any failure for the admin
        logger.exception("indexing failed for book %s", book_id)
        row = db.get(SubjectBook, book_id)
        if row is not None:
            row.status = "error"
            row.error = str(exc)[:500]
            db.commit()
    finally:
        db.close()


@router.post("/subjects/{semester}/{subject_id}/pdf", response_model=BookStatusOut,
             status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(_require_admin)])
async def upload_pdf(
    semester: str,
    subject_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ocr_lang: str = Form("ara+eng"),
    book_name: str = Form(""),
    academic_year: str = Form(""),
    db: Session = Depends(get_db),
) -> BookStatusOut:
    """Upload a PDF for a subject and start indexing it in the background."""
    if not is_valid_semester(semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    # Allow any subject_id so batch uploads can create new subjects dynamically.
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "only .pdf files are accepted")

    # Save the upload under pdfs/uploads with a unique, safe name.
    uploads = settings.pdf_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "book.pdf")
    stored = f"uploads/{semester}_{subject_id}_{uuid.uuid4().hex[:8]}_{safe}"
    dest = settings.pdf_dir / stored

    size = 0
    with dest.open("wb") as sink:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > _MAX_UPLOAD_BYTES:
                sink.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")
            sink.write(chunk)

    # Validate it is a real PDF before committing to indexing.
    from indexer import detect_text_layer
    try:
        has_text = detect_text_layer(dest)
    except Exception:
        has_text = False  # assume scanned image PDF, proceed with OCR

    # Each file gets its own row — look up by file path so re-uploads don't duplicate.
    row = (
        db.query(SubjectBook)
        .filter(
            SubjectBook.semester == semester,
            SubjectBook.subject_id == subject_id,
            SubjectBook.source_file == stored,
        )
        .first()
    )
    if row is None:
        row = SubjectBook(semester=semester, subject_id=subject_id)
        db.add(row)

    subject = get_subject(semester, subject_id)
    row.source_file = stored
    row.index_grade = index_scope_for_upload(semester)
    row.index_subject = subject_id
    row.book_name = book_name.strip() or (subject.name_ar if subject else subject_id)
    row.academic_year = academic_year.strip()
    row.ocr_lang = ocr_lang
    row.has_text_layer = has_text
    row.status = "indexing"
    row.error = None
    row.pages_indexed = 0
    row.pages_total = 0
    db.commit()
    db.refresh(row)

    background.add_task(_index_book_task, row.id)
    return _to_status(row)


@router.get("/subjects/{semester}", response_model=list[SubjectStatusOut],
            dependencies=[Depends(_require_admin)])
def list_subjects(semester: str, db: Session = Depends(get_db)) -> list[SubjectStatusOut]:
    """Every subject in a semester with its upload/index status."""
    if not is_valid_semester(semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    books = {
        b.subject_id: b
        for b in db.query(SubjectBook).filter(SubjectBook.semester == semester).all()
    }
    out = []
    for subject in subjects_for(semester):
        book = books.get(subject.id)
        has_static = bool(subject.books)
        out.append(SubjectStatusOut(
            subject_id=subject.id,
            name_ar=subject.name_ar,
            name_en=subject.name_en,
            has_book=book is not None or has_static,
            status=book.status if book else ("ready" if has_static else None),
            pages_indexed=book.pages_indexed if book else 0,
            pages_total=book.pages_total if book else 0,
        ))
    return out


@router.get("/codes", response_model=list[CodeOut], dependencies=[Depends(_require_admin)])
def list_codes(semester: str | None = None, db: Session = Depends(get_db)) -> list[CodeOut]:
    query = db.query(ActivationCode)
    if semester:
        query = query.filter(ActivationCode.semester == semester)
    rows = query.order_by(ActivationCode.created_at.desc()).limit(500).all()
    return [
        CodeOut(code=c.code, semester=c.semester, max_uses=c.max_uses,
                used_count=c.used_count, enabled=c.enabled, available=c.is_available)
        for c in rows
    ]


@router.get("/stats", response_model=StatsOut, dependencies=[Depends(_require_admin)])
def stats(db: Session = Depends(get_db)) -> StatsOut:
    now = datetime.datetime.now(datetime.timezone.utc)

    def _active(sem: str) -> int:
        count = 0
        for user in db.query(AppUser).all():
            from backend.deps import has_semester_access
            if has_semester_access(db, user, sem):
                count += 1
        return count

    codes = db.query(ActivationCode).all()
    return StatsOut(
        total_users=db.query(AppUser).count(),
        active_first=_active("first"),
        active_second=_active("second"),
        codes_total=len(codes),
        codes_available=sum(1 for c in codes if c.is_available),
        books_ready=db.query(SubjectBook).filter(SubjectBook.status == "ready").count(),
    )


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(_require_admin)])
def list_users(limit: int = 50, db: Session = Depends(get_db)) -> list[UserOut]:
    from backend.deps import has_semester_access
    users = db.query(AppUser).order_by(AppUser.created_at.desc()).limit(limit).all()
    return [
        UserOut(
            id=u.id,
            email=u.email,
            name=u.name,
            created_at=u.created_at.isoformat() if u.created_at else "",
            has_first=has_semester_access(db, u, "first"),
            has_second=has_semester_access(db, u, "second"),
        )
        for u in users
    ]


@router.post("/users/{user_id}/access", response_model=GrantAccessOut,
             dependencies=[Depends(_require_admin)])
def grant_access(user_id: int, body: GrantAccessIn,
                 db: Session = Depends(get_db)) -> GrantAccessOut:
    """Manually grant or revoke a semester for a user (activate/deactivate sub)."""
    if not is_valid_semester(body.semester):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown semester")
    if db.get(AppUser, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    access = (
        db.query(SemesterAccess)
        .filter(SemesterAccess.user_id == user_id, SemesterAccess.semester == body.semester)
        .first()
    )
    if body.revoke:
        if access:
            db.delete(access)
        db.commit()
        return GrantAccessOut(user_id=user_id, semester=body.semester,
                              granted=False, expires_at=None)

    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(days=body.days) if body.days else None
    if access is None:
        access = SemesterAccess(user_id=user_id, semester=body.semester)
        db.add(access)
    access.source = "admin"
    access.expires_at = expires
    db.commit()
    return GrantAccessOut(user_id=user_id, semester=body.semester, granted=True,
                          expires_at=expires.isoformat() if expires else None)


@router.get("/subjects/{semester}/{subject_id}/pdf", response_model=BookStatusOut,
            dependencies=[Depends(_require_admin)])
def book_status(semester: str, subject_id: str, db: Session = Depends(get_db)) -> BookStatusOut:
    row = (
        db.query(SubjectBook)
        .filter(SubjectBook.semester == semester, SubjectBook.subject_id == subject_id)
        .first()
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no PDF uploaded for this subject")
    return _to_status(row)


def _to_status(row: SubjectBook) -> BookStatusOut:
    return BookStatusOut(
        semester=row.semester,
        subject_id=row.subject_id,
        source_file=row.source_file,
        status=row.status,
        error=row.error,
        pages_indexed=row.pages_indexed or 0,
        pages_total=row.pages_total or 0,
        has_text_layer=bool(row.has_text_layer),
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )
