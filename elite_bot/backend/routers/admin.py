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
    PastQuestion,
    SemesterAccess,
    SubjectBook,
    SubjectChapter,
    SubjectMeta,
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
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


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
import threading
_INDEX_LOCK = threading.Lock()  # one indexing job at a time per subject


def _index_book_task(book_id: int) -> None:
    """Background worker: OCR-index an uploaded PDF and mark the row ready.

    Runs in a threadpool thread. With --workers 2, the second uvicorn worker
    handles API requests while this worker does OCR — no blocking.
    The lock prevents two uploads from writing the same JSONL file concurrently.
    """
    from indexer import index_pdf
    from services.search_engine import reload_indexes

    with _INDEX_LOCK:
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
            reload_indexes()
            logger.info("indexed upload for %s/%s: %d/%d pages",
                        row.semester, row.subject_id, indexed, total)
        except Exception as exc:  # noqa: BLE001
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
    force_ocr: str = Form("false"),
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
    if force_ocr.lower() in ("true", "1", "yes"):
        has_text = False  # skip text layer, force Tesseract OCR
    else:
        try:
            has_text = detect_text_layer(dest)
        except Exception:
            has_text = False

    # Always replace the existing entry for this subject — one book per subject.
    # Delete any extras first (guards against old duplicates).
    existing = (
        db.query(SubjectBook)
        .filter(SubjectBook.semester == semester, SubjectBook.subject_id == subject_id)
        .order_by(SubjectBook.id)
        .all()
    )
    if existing:
        row = existing[0]
        for extra in existing[1:]:
            db.delete(extra)
    else:
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
    """Every subject in a semester with its upload/index status.
    Also includes uploaded books whose subject_id is not in curriculum.yaml.
    """
    if not is_valid_semester(semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    db_books = {
        b.subject_id: b
        for b in db.query(SubjectBook).filter(SubjectBook.semester == semester).all()
    }
    curriculum = {s.id: s for s in subjects_for(semester)}
    out: list[SubjectStatusOut] = []

    # Curriculum subjects first
    for subject in subjects_for(semester):
        book = db_books.get(subject.id)
        has_static = bool(subject.books)
        out.append(SubjectStatusOut(
            subject_id=subject.id,
            name_ar=subject.name_ar,
            name_en=subject.name_en,
            has_book=book is not None or has_static,
            status=book.status if book else ("ready" if has_static else None),
            pages_indexed=book.pages_indexed if book else 0,
            pages_total=book.pages_total if book else 0,
            book_name=book.book_name if book else None,
            can_delete=book is not None,
        ))

    # Extra uploaded books not in curriculum
    for subj_id, book in db_books.items():
        if subj_id not in curriculum:
            out.append(SubjectStatusOut(
                subject_id=subj_id,
                name_ar=book.book_name or subj_id,
                name_en=subj_id,
                has_book=True,
                status=book.status,
                pages_indexed=book.pages_indexed or 0,
                pages_total=book.pages_total or 0,
                book_name=book.book_name,
                can_delete=True,
            ))
    return out


@router.delete("/subjects/{semester}/{subject_id}/pdf",
               dependencies=[Depends(_require_admin)])
def delete_book(semester: str, subject_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete an uploaded book, its physical file, and its search index."""
    from services.search_engine import reload_indexes

    rows = (
        db.query(SubjectBook)
        .filter(SubjectBook.semester == semester, SubjectBook.subject_id == subject_id)
        .all()
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no uploaded book for this subject")

    deleted_files: list[str] = []
    for row in rows:
        pdf_path = settings.pdf_dir / row.source_file
        if pdf_path.exists():
            pdf_path.unlink(missing_ok=True)
            deleted_files.append(row.source_file)
        db.delete(row)

    db.commit()

    # Remove the JSONL index files for this subject so stale data is gone
    grade = rows[0].index_grade  # e.g. "app_first"
    index_dir = settings.pdf_dir.parent / "indexes"
    for suffix in (".jsonl", ".meta.json"):
        idx_file = index_dir / f"{grade}__{subject_id}{suffix}"
        if idx_file.exists():
            idx_file.unlink(missing_ok=True)

    reload_indexes()
    logger.info("deleted book %s/%s — files: %s", semester, subject_id, deleted_files)
    return {"deleted": len(rows), "files_removed": deleted_files}


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


# ── chapter management ───────────────────────────────────────────────────────

@router.get("/chapters/{semester}")
def get_chapters(
    semester: str,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return all subject chapters + name_ar for a semester."""
    rows = (
        db.query(SubjectChapter)
        .filter(SubjectChapter.semester == semester)
        .order_by(SubjectChapter.subject_id, SubjectChapter.sort_order)
        .all()
    )
    meta_rows = db.query(SubjectMeta).filter(SubjectMeta.semester == semester).all()
    name_ar_map = {m.subject_id: m.name_ar for m in meta_rows}

    subjects: dict[str, list[dict]] = {}
    for r in rows:
        subjects.setdefault(r.subject_id, []).append({
            "key": r.chapter_key,
            "name": r.chapter_name,
            "chapter_number": r.chapter_number,
            "page_start": r.page_start,
            "page_end": r.page_end,
        })
    return [
        {"subject_id": sid, "name_ar": name_ar_map.get(sid, ""), "chapters": chs}
        for sid, chs in subjects.items()
    ]


@router.put("/chapters/{semester}/{subject_id}")
def set_chapters(
    semester: str,
    subject_id: str,
    body: dict,
    _: None = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Replace chapter list + name_ar. Body: {name_ar: str, chapters: [{key, name}]}"""
    chapters = body.get("chapters", [])
    name_ar = body.get("name_ar", "").strip()

    # Save name_ar
    meta = db.query(SubjectMeta).filter_by(semester=semester, subject_id=subject_id).first()
    if meta is None:
        meta = SubjectMeta(semester=semester, subject_id=subject_id)
        db.add(meta)
    if name_ar:
        meta.name_ar = name_ar

    # Replace chapters
    db.query(SubjectChapter).filter(
        SubjectChapter.semester == semester,
        SubjectChapter.subject_id == subject_id,
    ).delete()
    for i, ch in enumerate(chapters):
        ps = ch.get("page_start")
        pe = ch.get("page_end")
        cn = ch.get("chapter_number")
        db.add(SubjectChapter(
            semester=semester,
            subject_id=subject_id,
            chapter_key=ch.get("key") or ch.get("name", "").replace(" ", "_")[:32],
            chapter_name=ch["name"],
            sort_order=i,
            chapter_number=int(cn) if cn else None,
            page_start=int(ps) if ps else None,
            page_end=int(pe) if pe else None,
        ))
    db.commit()
    return {"saved": len(chapters)}


# ── question bank management ─────────────────────────────────────────────────

@router.get("/questions/ping")
def questions_ping() -> dict:
    return {"pong": True}


_INDEXED_BOOK_PREFIX = re.compile(
    r"^(first|second|app)_[a-z]+_[0-9a-f]{6,}_"  # semester_subject_hash_
    r"|^[0-9a-f]{7,}[_\-]"  # raw hash-prefixed files (e.g. 0200bb8f_...)
)


@router.get("/questions/files", dependencies=[Depends(_require_admin)])
def list_question_files() -> list[dict]:
    """List question-bank PDFs: med_books/ subdir + non-indexed files in uploads root."""
    import os
    uploads_dir = settings.pdf_dir
    files = []
    for root, _dirs, filenames in os.walk(uploads_dir):
        for fname in sorted(filenames):
            if not fname.lower().endswith(".pdf"):
                continue
            # Skip auto-indexed book files (first_bio_<hash>_*.pdf)
            if _INDEXED_BOOK_PREFIX.match(fname):
                continue
            rel = os.path.relpath(os.path.join(root, fname), uploads_dir)
            files.append({"path": rel.replace("\\", "/"), "name": fname})
    files.sort(key=lambda x: x["name"])
    return files


@router.get("/questions", dependencies=[Depends(_require_admin)])
def list_questions(
    semester: str | None = None,
    subject_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict]:
    q = db.query(PastQuestion)
    if semester:
        q = q.filter(PastQuestion.semester == semester)
    if subject_id:
        q = q.filter(PastQuestion.subject_id == subject_id)
    rows = q.order_by(PastQuestion.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "semester": r.semester,
            "subject_id": r.subject_id,
            "question": r.question,
            "option_a": r.option_a,
            "option_b": r.option_b,
            "option_c": r.option_c,
            "option_d": r.option_d,
            "correct_index": r.correct_index,
            "source_file": r.source_file,
        }
        for r in rows
    ]


@router.delete("/questions/{question_id}", dependencies=[Depends(_require_admin)])
def delete_question(question_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(PastQuestion, question_id)
    if row is None:
        raise HTTPException(404, "question not found")
    db.delete(row)
    db.commit()
    return {"deleted": question_id}


@router.delete("/questions", dependencies=[Depends(_require_admin)])
def delete_all_questions(
    semester: str | None = None,
    subject_id: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Delete all questions for a subject (before re-extraction)."""
    q = db.query(PastQuestion)
    if semester:
        q = q.filter(PastQuestion.semester == semester)
    if subject_id:
        q = q.filter(PastQuestion.subject_id == subject_id)
    count = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}


_extraction_status: dict[str, dict] = {}  # key -> {status, total, done, errors}


@router.get("/questions/status/{job_id}", dependencies=[Depends(_require_admin)])
def extraction_status(job_id: str) -> dict:
    return _extraction_status.get(job_id, {"status": "not_found"})


@router.post("/questions/extract", dependencies=[Depends(_require_admin)])
def extract_questions(
    background_tasks: BackgroundTasks,
    semester: str = Form(...),
    subject_id: str = Form(...),
    source_path: str = Form(...),  # relative path inside uploads dir
    db: Session = Depends(get_db),
) -> dict:
    """Start background extraction of MCQ questions from a PDF using Gemini Vision."""
    pdf_path = settings.pdf_dir / source_path
    if not pdf_path.exists():
        raise HTTPException(404, f"file not found: {source_path}")

    job_id = str(uuid.uuid4())[:8]
    _extraction_status[job_id] = {"status": "running", "total": 0, "done": 0, "errors": 0, "extracted": 0}
    background_tasks.add_task(_run_extraction, job_id, semester, subject_id, str(pdf_path), source_path)
    return {"job_id": job_id}


def _run_extraction(job_id: str, semester: str, subject_id: str, pdf_path: str, source_rel: str) -> None:
    """Render each PDF page and send to Gemini Vision to extract MCQs."""
    import base64
    import json as _json

    status_d = _extraction_status[job_id]
    db = SessionLocal()
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        status_d["total"] = total_pages
        extracted_total = 0

        from config import settings as _s
        from services.ai.gemini import GeminiProvider
        ai = GeminiProvider(api_key=_s.gemini_api_key)

        for page_num in range(total_pages):
            try:
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode()

                prompt = [
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": img_b64,
                        }
                    },
                    """أنت مساعد متخصص في استخراج الأسئلة من بنوك الأسئلة العربية.
استخرج جميع الأسئلة متعددة الخيارات من هذه الصورة.

قواعد مهمة:
1. كل سؤال يظهر في جدول: صف علوي أزرق يحتوي على نص السؤال، وصفان به خيارات A وB وC وD.
2. مفتاح الإجابات يظهر في جدول منفصل في الأسفل.
3. إذا كان هناك نص تمهيدي أو سيناريو مشترك قبل مجموعة أسئلة (مثل: "في دراسة أجريت على..." أو "المعطيات التالية..." أو جدول بيانات)، يجب دمج هذا النص مع كل سؤال ينتمي إليه في حقل question. مثال: "المعطيات: [النص المشترك]. السؤال: [نص السؤال]".
4. لا تتجاهل أي نص سياقي مشترك — فهو جزء أساسي من السؤال.

أعد النتائج كـ JSON array فقط بدون أي نص إضافي. كل عنصر:
{"question": "نص السؤال كاملاً بما يشمل أي نص تمهيدي مشترك", "a": "الخيار أ", "b": "الخيار ب", "c": "الخيار ج", "d": "الخيار د", "answer": "A"}
حيث answer هي A أو B أو C أو D.
إذا لم تكن الصفحة تحتوي على أسئلة، أعد [].
""",
                ]

                import google.generativeai as genai
                genai.configure(api_key=_s.gemini_api_key)
                model = genai.GenerativeModel("gemini-3.5-flash-lite")

                import google.generativeai.types as gtypes
                resp = model.generate_content(
                    prompt,
                    generation_config=gtypes.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=4096,
                        response_mime_type="application/json",
                    ),
                )

                raw = (resp.text or "").strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    if "\n" in raw:
                        raw = raw[raw.find("\n") + 1:]
                    raw = raw.removeprefix("json").strip()

                questions = _json.loads(raw) if raw and raw != "[]" else []
                _LETTER_MAP = {"A": 0, "B": 1, "C": 2, "D": 3}

                for q in questions:
                    ans_letter = (q.get("answer") or "A").upper().strip()
                    correct_idx = _LETTER_MAP.get(ans_letter, 0)
                    db.add(PastQuestion(
                        semester=semester,
                        subject_id=subject_id,
                        question=q.get("question", ""),
                        option_a=q.get("a", ""),
                        option_b=q.get("b", ""),
                        option_c=q.get("c", ""),
                        option_d=q.get("d", ""),
                        correct_index=correct_idx,
                        source_file=source_rel,
                    ))
                    extracted_total += 1

                db.commit()
                status_d["done"] = page_num + 1
                status_d["extracted"] = extracted_total

            except Exception as exc:
                logger.warning("page %d extraction failed: %s", page_num, exc)
                status_d["errors"] = status_d.get("errors", 0) + 1
                status_d["done"] = page_num + 1

        status_d["status"] = "done"
        status_d["extracted"] = extracted_total

    except Exception as exc:
        logger.error("extraction job %s failed: %s", job_id, exc)
        status_d["status"] = "error"
        status_d["error"] = str(exc)
    finally:
        db.close()
