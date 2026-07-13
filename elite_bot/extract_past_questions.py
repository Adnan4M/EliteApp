"""
Extract real MCQ questions from past-year exam PDFs and store them in the DB.

Usage:
    python extract_past_questions.py

Point QUESTION_PDFS at the files you want to extract from.
The AI reads each PDF's OCR text and pulls out every MCQ it finds.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

# Make sure we can import project modules
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from database import SessionLocal, init_db
from backend.models import PastQuestion
from services.ai import get_study_ai
from utils.arabic import normalize

# ── Config ────────────────────────────────────────────────────────────────────
PDF_DIR = Path(__file__).parent / "pdfs" / "uploads" / "med_books"

# Files that are question banks — identified by name patterns
QUESTION_KEYWORDS = [
    "rbcs", "rbc", "تجميع", "اسئلة", "أسئلة", "امتحان", "امتحانات",
    "question", "exam", "quiz", "history chapter", "sketch history",
    "unit1", "unit2", "unit3",
]

# Map filename keywords → (semester, subject_id)
SUBJECT_MAP: list[tuple[list[str], str, str]] = [
    (["فيزياء", "physics", "فيزيا"],        "first",  "physics"),
    (["كيميا", "chem"],                      "first",  "chemistry"),
    (["history", "تاريخ", "sketch"],         "first",  "history"),
    (["english", "unit", "انجليز"],          "first",  "english"),
    (["cell", "خلية", "bio", "nucleus",
      "cytoskeleton", "membrane", "rbcs"],   "first",  "biology"),
    (["physiology", "فيزيولوج"],             "second", "physiology"),
    (["anatomy", "تشريح"],                   "second", "anatomy"),
    (["genetic", "وراثة"],                   "second", "genetics"),
    (["stat", "احصاء"],                      "second", "statistics"),
]

DEFAULT_SUBJECT = ("first", "biology")

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_question_file(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in QUESTION_KEYWORDS)


def classify(name: str) -> tuple[str, str]:
    nl = name.lower()
    for keywords, sem, subj in SUBJECT_MAP:
        if any(kw.lower() in nl for kw in keywords):
            return sem, subj
    return DEFAULT_SUBJECT


def ocr_text(pdf_path: Path) -> str:
    """Extract text from PDF — tries native text layer first, then Tesseract OCR."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        pages_text = []
        for page in doc:
            text = page.get_text("text").strip()
            if not text:
                # Scanned page — run Tesseract on it
                import pytesseract
                from PIL import Image
                import io
                pix = page.get_pixmap(dpi=200)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang="ara+eng")
            pages_text.append(text)
        doc.close()
        return "\n\n".join(t for t in pages_text if t.strip())
    except Exception as e:
        logger.warning("OCR failed for %s: %s", pdf_path.name, e)
        return ""


def extract_mcqs(ai, text: str, source: str) -> list[dict]:
    """Ask the AI to extract all MCQs from raw text."""
    if not text.strip():
        return []

    # Chunk to avoid token limits
    chunk_size = 8000
    all_mcqs = []
    chunks = [text[i:i+chunk_size] for i in range(0, min(len(text), 80000), chunk_size)]

    for i, chunk in enumerate(chunks):
        logger.info("  chunk %d/%d", i+1, len(chunks))
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question":      {"type": "string"},
                    "option_a":      {"type": "string"},
                    "option_b":      {"type": "string"},
                    "option_c":      {"type": "string"},
                    "option_d":      {"type": "string"},
                    "correct_index": {"type": "integer"},
                },
                "required": ["question", "option_a", "option_b",
                             "option_c", "option_d", "correct_index"],
            },
        }
        prompt = (
            "Extract EVERY multiple-choice question from the text below. "
            "Each question has exactly 4 options (A, B, C, D). "
            "correct_index is 0 for A, 1 for B, 2 for C, 3 for D. "
            "If the correct answer is not explicitly marked, set correct_index to 0. "
            "Keep all text exactly as written — do not translate or paraphrase. "
            "Return ONLY a JSON array. If no MCQs found, return [].\n\n"
            f"TEXT:\n{chunk}"
        )
        try:
            data = ai.provider.complete_json(prompt, schema=schema, max_tokens=8192)
            if isinstance(data, list):
                all_mcqs.extend(data)
            elif isinstance(data, dict) and "questions" in data:
                all_mcqs.extend(data["questions"])
        except Exception as e:
            logger.warning("  AI extraction failed: %s", e)

    return all_mcqs


def keywords_for(question: str, options: list[str]) -> str:
    """Extract normalized keywords from question text for search matching."""
    combined = question + " " + " ".join(options)
    words = normalize(combined).split()
    # Keep words longer than 3 chars
    meaningful = [w for w in words if len(w) > 3]
    return " ".join(dict.fromkeys(meaningful))  # deduplicated, order-preserved


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    init_db()
    ai = get_study_ai()
    if not ai.available():
        print("ERROR: AI not configured. Set GEMINI_API_KEY in .env")
        return

    db = SessionLocal()
    try:
        question_files = [p for p in sorted(PDF_DIR.glob("*.pdf")) if is_question_file(p.name)]
        print(f"Found {len(question_files)} question bank files\n")

        total_added = 0
        for pdf in question_files:
            semester, subject_id = classify(pdf.name)
            print(f"\n{'─'*60}")
            print(f"File    : {pdf.name}")
            print(f"Subject : {semester} / {subject_id}")

            # Skip if already extracted
            existing = db.query(PastQuestion).filter(
                PastQuestion.source_file == pdf.name
            ).count()
            if existing > 0:
                print(f"[skip] already have {existing} questions from this file")
                continue

            print("Extracting text via OCR...")
            text = ocr_text(pdf)
            if not text.strip():
                print("[skip] no text extracted")
                continue
            print(f"Got {len(text)} chars of text. Sending to AI...")

            raw_mcqs = extract_mcqs(ai, text, pdf.name)
            print(f"AI found {len(raw_mcqs)} questions")

            added = 0
            for raw in raw_mcqs:
                try:
                    q = str(raw.get("question", "")).strip()
                    a = str(raw.get("option_a", "")).strip()
                    b = str(raw.get("option_b", "")).strip()
                    c = str(raw.get("option_c", "")).strip()
                    d = str(raw.get("option_d", "")).strip()
                    ci = int(raw.get("correct_index", 0))
                    if not q or not a or not b:
                        continue
                    ci = max(0, min(3, ci))
                    kws = keywords_for(q, [a, b, c, d])
                    db.add(PastQuestion(
                        semester=semester,
                        subject_id=subject_id,
                        question=q,
                        option_a=a, option_b=b, option_c=c, option_d=d,
                        correct_index=ci,
                        keywords=kws,
                        source_file=pdf.name,
                    ))
                    added += 1
                except Exception as e:
                    logger.warning("bad MCQ row: %s", e)

            db.commit()
            print(f"✓ stored {added} questions")
            total_added += added

        print(f"\n{'='*60}")
        total = db.query(PastQuestion).count()
        print(f"Done. Added {total_added} questions this run.")
        print(f"Total past questions in DB: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
