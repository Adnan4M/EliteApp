"""
Index PDFs directly on disk — bypasses HTTP, no timeouts.
Indexes all files NOT already in batch_done.txt.

Run:
    py direct_index.py
"""

import sys
import uuid
import re
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from database import SessionLocal, init_db
from backend.models import SubjectBook
from backend.content import index_scope_for_upload, get_subject
from config import settings

PDF_DIR   = Path(__file__).parent / "pdfs" / "uploads" / "med_books"
DONE_FILE = Path(__file__).parent / "batch_done.txt"

RULES: list[tuple[list[str], str, str, str, str]] = [
    (["فيزياء", "physics", "فيزيا"],
        "first", "physics",   "الفيزياء الطبية",     "السنة التحضيرية"),
    (["كيميا", "chem", "chemistry"],
        "first", "chemistry", "الكيمياء الطبية",     "السنة التحضيرية"),
    (["احياء", "biology bac", "bbio"],
        "first", "biology",   "علم الأحياء",          "السنة التحضيرية"),
    (["cell", "خلية", "nucleus", "cytoskeleton", "membrane", "bio"],
        "first", "biology",   "بيولوجيا الخلية",     "السنة التحضيرية"),
    (["history", "تاريخ", "sketch history"],
        "first", "history",   "تاريخ الطب",           "السنة التحضيرية"),
    (["english", "unit", "cambridge", "انجليز"],
        "first", "english",   "اللغة الإنجليزية",    "السنة التحضيرية"),
    (["physiology", "فيزيولوج", "physio"],
        "second", "physiology", "الفيزيولوجيا",       "السنة التحضيرية"),
    (["anatomy", "تشريح", "مصطلحات التشريح"],
        "second", "anatomy",    "التشريح",             "السنة التحضيرية"),
    (["genetic", "وراثة"],
        "second", "genetics",   "الوراثة",             "السنة التحضيرية"),
    (["stat", "احصاء", "إحصاء"],
        "second", "statistics", "الإحصاء",             "السنة التحضيرية"),
]
DEFAULT = ("first", "biology", "كتب متنوعة", "السنة التحضيرية")


def classify(pdf: Path) -> tuple[str, str, str, str]:
    """Classify by folder path first, then filename keywords."""
    parts = [p.lower() for p in pdf.parts]
    fl = pdf.name.lower()

    # Files inside a 'Questions' folder go to biology (questions context)
    if "questions" in parts:
        # Detect semester from path
        semester = "second" if any("term 2" in p or "second" in p for p in parts) else "first"
        # Try to classify by subject name in filename
        for keywords, sem, subject, book_name, year in RULES:
            if any(kw.lower() in fl for kw in keywords):
                return sem, subject, f"أسئلة — {book_name}", year
        return semester, "biology", "أسئلة امتحانية", "السنة التحضيرية"

    # Files inside Term 1 / Term 2 folders
    if any("term 1" in p or "الفصل الأول" in p for p in parts):
        for keywords, _, subject, book_name, year in RULES:
            if any(kw.lower() in fl for kw in keywords):
                return "first", subject, book_name, year
        return "first", DEFAULT[1], DEFAULT[2], DEFAULT[3]
    if any("term 2" in p or "الفصل الثاني" in p for p in parts):
        for keywords, _, subject, book_name, year in RULES:
            if any(kw.lower() in fl for kw in keywords):
                return "second", subject, book_name, year
        return "second", DEFAULT[1], DEFAULT[2], DEFAULT[3]

    # Fallback: classify by filename
    for keywords, semester, subject, book_name, year in RULES:
        if any(kw.lower() in fl for kw in keywords):
            return semester, subject, book_name, year
    return DEFAULT


def index_one(pdf: Path, db) -> None:
    semester, subject_id, book_name, academic_year = classify(pdf)

    # Copy file into the uploads folder with a unique safe name
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", pdf.name)
    stored = f"uploads/med_books/{uuid.uuid4().hex[:8]}_{safe}"
    dest = settings.pdf_dir / stored
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Symlink or copy — copy is safer on Windows
    import shutil
    if not dest.exists():
        shutil.copy2(pdf, dest)

    # Detect text layer
    from indexer import detect_text_layer
    try:
        has_text = detect_text_layer(dest)
    except Exception:
        has_text = False

    # Create DB row
    subject = get_subject(semester, subject_id)
    row = SubjectBook(
        semester=semester,
        subject_id=subject_id,
        source_file=stored,
        index_grade=index_scope_for_upload(semester),
        index_subject=subject_id,
        book_name=book_name or (subject.name_ar if subject else subject_id),
        academic_year=academic_year,
        ocr_lang="ara+eng",
        has_text_layer=has_text,
        status="indexing",
        pages_indexed=0,
        pages_total=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    print(f"  Indexing {pdf.name} → {semester}/{subject_id}")

    # Run indexer directly (blocking — shows progress)
    from indexer import index_pdf

    def progress(done, total):
        if total:
            print(f"  page {done}/{total}", end="\r")

    try:
        indexed, total = index_pdf(
            grade=row.index_grade,
            subject=row.index_subject,
            pdf_path=dest,
            ocr_lang=row.ocr_lang,
            has_text_layer=row.has_text_layer,
            progress=progress,
        )
        row.status = "ready"
        row.pages_indexed = indexed
        row.pages_total = total
        row.error = None
        print(f"\n  ✓ done: {indexed}/{total} pages")
    except Exception as e:
        row.status = "error"
        row.error = str(e)[:500]
        print(f"\n  ✗ error: {e}")

    db.commit()

    # Reload search indexes so new pages are immediately searchable
    try:
        from backend.content import reload_indexes
        reload_indexes()
    except Exception:
        pass

    # Mark as done (use relative path to handle subdirectories)
    rel = str(pdf.relative_to(PDF_DIR))
    with DONE_FILE.open("a", encoding="utf-8") as f:
        f.write(rel + "\n")


def main() -> None:
    init_db()

    already_done = set()
    if DONE_FILE.exists():
        already_done = set(DONE_FILE.read_text(encoding="utf-8").splitlines())

    # Scan all subdirectories (Books/Term 1, Books/Term 2, Questions, etc.)
    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    # Use relative path from PDF_DIR as key to avoid name collisions across subdirs
    pending = [p for p in pdfs if str(p.relative_to(PDF_DIR)) not in already_done]

    print(f"Total PDFs : {len(pdfs)}")
    print(f"Already done: {len(already_done)}")
    print(f"To index now: {len(pending)}\n")

    db = SessionLocal()
    try:
        for i, pdf in enumerate(pending, 1):
            print(f"\n[{i}/{len(pending)}] {pdf.name}  ({pdf.stat().st_size // (1024*1024)} MB)")
            index_one(pdf, db)
    finally:
        db.close()

    print(f"\n{'='*50}")
    print("All done.")


if __name__ == "__main__":
    main()
