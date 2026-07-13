"""
Batch-upload all downloaded PDFs to the running backend for OCR indexing.

Usage:
    python batch_index.py

The backend must be running on localhost:8000.
Each PDF is assigned to a semester + subject based on its filename keywords.
"""

import time
import requests
from pathlib import Path

API_BASE   = "http://127.0.0.1:8000"
ADMIN_KEY  = "dev-admin-key-123"   # change if you changed APP_ADMIN_KEY in .env
PDF_DIR    = Path(__file__).parent / "pdfs" / "uploads" / "med_books"

HEADERS   = {"X-Admin-Key": ADMIN_KEY}
DONE_FILE = Path(__file__).parent / "batch_done.txt"  # tracks already-uploaded files

# ── Mapping: filename keywords → (semester, subject_id, book_name, academic_year)
# Add or adjust rows as needed. First match wins (case-insensitive).
RULES: list[tuple[list[str], str, str, str, str]] = [
    # keywords              semester    subject_id    book_name           academic_year
    # ── Semester 1 ────────────────────────────────────────────────────────────
    (["فيزياء", "physics", "فيزيا"],
        "first", "physics",   "الفيزياء الطبية",     "السنة التحضيرية"),
    (["كيميا", "chem", "chemistry"],
        "first", "chemistry", "الكيمياء الطبية",     "السنة التحضيرية"),
    (["احياء بكالوريا", "biology bac"],
        "first", "biology",   "علم الأحياء",          "البكالوريا"),
    (["cell", "خلية", "nucleus", "cytoskeleton", "membrane", "bio"],
        "first", "biology",   "بيولوجيا الخلية",     "السنة التحضيرية"),
    (["history", "تاريخ", "sketch history"],
        "first", "history",   "تاريخ الطب",           "السنة التحضيرية"),
    (["english", "unit", "cambridge", "انجليز"],
        "first", "english",   "اللغة الإنجليزية",    "السنة التحضيرية"),

    # ── Semester 2 ────────────────────────────────────────────────────────────
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


def classify(filename: str) -> tuple[str, str, str, str]:
    fl = filename.lower()
    for keywords, semester, subject, book_name, year in RULES:
        if any(kw.lower() in fl for kw in keywords):
            return semester, subject, book_name, year
    return DEFAULT


def upload(pdf: Path) -> bool:
    semester, subject_id, book_name, academic_year = classify(pdf.name)
    url = f"{API_BASE}/admin/subjects/{semester}/{subject_id}/pdf"
    print(f"\n{'─'*60}")
    print(f"File   : {pdf.name}  ({pdf.stat().st_size // (1024*1024)} MB)")
    print(f"→ {semester} / {subject_id} / {book_name}")
    for attempt in range(1, 4):
        try:
            with pdf.open("rb") as f:
                resp = requests.post(
                    url,
                    headers=HEADERS,
                    files={"file": (pdf.name, f, "application/pdf")},
                    data={
                        "ocr_lang": "ara+eng",
                        "book_name": book_name,
                        "academic_year": academic_year,
                    },
                    timeout=600,   # 10 minutes — enough for 100 MB files
                )
            if resp.status_code in (200, 202):
                print(f"✓ queued (attempt {attempt})")
                return True
            else:
                print(f"✗ server error {resp.status_code}: {resp.text[:200]}")
                return False
        except requests.exceptions.Timeout:
            print(f"  timeout on attempt {attempt}, retrying...")
            time.sleep(5)
        except Exception as e:
            print(f"  error: {e}")
            time.sleep(5)
    print("✗ gave up after 3 attempts")
    return False


def main() -> None:
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    done = set(DONE_FILE.read_text(encoding="utf-8").splitlines()) if DONE_FILE.exists() else set()
    remaining = [p for p in pdfs if p.name not in done]

    print(f"Found {len(pdfs)} PDFs — {len(done)} already done — {len(remaining)} to upload")
    print("Backend must be running: py -m uvicorn backend.main:app --port 8000\n")

    for i, pdf in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}]", end="")
        ok = upload(pdf)
        if ok:
            with DONE_FILE.open("a", encoding="utf-8") as f:
                f.write(pdf.name + "\n")
        time.sleep(1)

    print(f"\n{'='*60}")
    print("All files queued. OCR indexing runs in the background.")
    print("Check progress at: http://127.0.0.1:8000/admin-panel")


if __name__ == "__main__":
    main()
