"""Build the page-level search index for every book in ``curriculum.yaml``.

For each page we store the text and the pixel box of every word. Pages with a
real text layer are read directly; scanned pages go through Tesseract. The
result is one JSONL file per subject under ``indexes/``, plus a ``.meta.json``
fingerprint so an unchanged PDF is never re-indexed.

Run it directly::

    python indexer.py              # index everything that changed
    python indexer.py --force      # rebuild from scratch
    python indexer.py --subject الكيمياء --limit 20
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

from config import settings
from services.ocr_engine import OcrEngine, OcrError, Word
from services.pdf_engine import PdfEngine

logger = logging.getLogger(__name__)


def index_stem(grade: str, subject: str) -> str:
    """Filesystem-safe stem for the ``indexes/{grade}__{subject}`` files."""
    return f"{grade}__{subject}".replace(os.sep, "_").replace(" ", "_")


@dataclass(frozen=True, slots=True)
class Book:
    """One indexable PDF, resolved from ``curriculum.yaml``."""

    grade: str
    subject: str
    path: Path
    ocr_lang: str
    has_text_layer: bool

    @property
    def index_stem(self) -> str:
        return index_stem(self.grade, self.subject)

    def fingerprint(self) -> str:
        stat = self.path.stat()
        return f"{stat.st_size}-{stat.st_mtime_ns}-{self.ocr_lang}"


def load_curriculum(path: Path | None = None) -> list[Book]:
    """Parse ``curriculum.yaml`` into :class:`Book` records."""
    path = path or (settings.pdf_dir / "curriculum.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    books: list[Book] = []
    for grade, gdata in (data.get("grades") or {}).items():
        for subject, sdata in (gdata.get("subjects") or {}).items():
            pdf_path = settings.pdf_dir / sdata["file"]
            if not pdf_path.exists():
                logger.warning("skipping %s/%s: %s not found", grade, subject, pdf_path.name)
                continue
            books.append(
                Book(
                    grade=grade,
                    subject=subject,
                    path=pdf_path,
                    ocr_lang=str(sdata.get("ocr_lang", "ara")),
                    has_text_layer=bool(sdata.get("has_text_layer", False)),
                )
            )
    return books


def _serialize_words(words: tuple[Word, ...]) -> list[list[Any]]:
    return [[w.text, w.left, w.top, w.width, w.height, round(w.confidence, 1)] for w in words]


def _index_one_page(job: tuple) -> dict[str, Any] | None:
    """Worker: index a single page. Must be module-level for Windows spawn."""
    pdf_path, page_no, ocr_lang, dpi, tesseract_cmd, tessdata_prefix = job[:6]
    force_ocr: bool = job[6] if len(job) > 6 else False
    engine = PdfEngine(pdf_path, dpi=dpi)
    try:
        if not force_ocr and engine.has_text_layer(page_no):
            page = engine.native_text(page_no)
            text, words, from_ocr = page.text, page.words, False
        else:
            ocr = OcrEngine(tesseract_cmd, tessdata_prefix)
            with tempfile.TemporaryDirectory() as tmp:
                image = engine.render_page_image(page_no, Path(tmp) / f"p{page_no}.png")
                result = ocr.run(image, lang=ocr_lang)
            text, words, from_ocr = result.text, result.words, True

        if not text.strip():
            return None

        return {
            "page": page_no,
            "printed": engine.printed_label(page_no),
            "from_ocr": from_ocr,
            "text": text,
            "words": _serialize_words(words),
        }
    except (OcrError, ValueError, RuntimeError) as exc:
        logger.warning("page %s of %s failed: %s", page_no, Path(pdf_path).name, exc)
        return None
    finally:
        engine.close()


class Indexer:
    """Builds and refreshes the on-disk page index."""

    def __init__(self, dpi: int | None = None, workers: int | None = None) -> None:
        self.dpi = dpi or settings.render_dpi
        self.workers = workers or max(1, (os.cpu_count() or 4) - 2)
        settings.ensure_dirs()

    def _paths(self, book: Book) -> tuple[Path, Path]:
        base = settings.index_dir / book.index_stem
        return base.with_suffix(".jsonl"), base.with_suffix(".meta.json")

    def is_current(self, book: Book) -> bool:
        _, meta_path = self._paths(book)
        if not meta_path.exists():
            return False
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return meta.get("fingerprint") == book.fingerprint()

    def build(self, book: Book, force: bool = False, limit: int | None = None) -> int:
        """Index one book. Returns the number of pages written."""
        jsonl_path, meta_path = self._paths(book)
        if not force and self.is_current(book):
            logger.info("%s / %s is up to date", book.grade, book.subject)
            return 0

        with PdfEngine(book.path, dpi=self.dpi) as engine:
            total = engine.page_count
        pages = range(min(total, limit) if limit else total)

        jobs = [
            (str(book.path), n, book.ocr_lang, self.dpi,
             settings.tesseract_cmd, settings.tessdata_prefix)
            for n in pages
        ]

        started = time.perf_counter()
        written = 0
        logger.info(
            "indexing %s / %s -- %d pages, %d workers%s",
            book.grade, book.subject, len(jobs), self.workers,
            "" if book.has_text_layer else " (OCR)",
        )

        with jsonl_path.open("w", encoding="utf-8") as sink:
            with futures.ProcessPoolExecutor(max_workers=self.workers) as pool:
                for record in pool.map(_index_one_page, jobs, chunksize=4):
                    if record is None:
                        continue
                    sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
                    if written % 25 == 0:
                        logger.info("  ... %d/%d pages", written, len(jobs))

        elapsed = time.perf_counter() - started
        meta_path.write_text(
            json.dumps(
                {
                    "fingerprint": book.fingerprint(),
                    "grade": book.grade,
                    "subject": book.subject,
                    "source": book.path.name,
                    "dpi": self.dpi,
                    "pages_indexed": written,
                    "pages_total": len(jobs),
                    "seconds": round(elapsed, 1),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info(
            "  done: %d/%d pages in %.1fs (%.2fs/page)",
            written, len(jobs), elapsed, elapsed / max(len(jobs), 1),
        )
        return written

    def build_all(self, force: bool = False, subject: str | None = None,
                  limit: int | None = None) -> None:
        books = load_curriculum()
        if subject:
            books = [b for b in books if b.subject == subject]
            if not books:
                raise SystemExit(f"no subject named {subject!r} in curriculum.yaml")
        for book in books:
            self.build(book, force=force, limit=limit)


def iter_index(grade: str, subject: str) -> Iterator[dict[str, Any]]:
    """Stream the indexed pages of one subject."""
    path = settings.index_dir / f"{index_stem(grade, subject)}.jsonl"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def detect_text_layer(pdf_path: Path | str, sample: int = 8) -> bool:
    """Guess whether a PDF has a usable text layer (so OCR can be skipped)."""
    with PdfEngine(pdf_path, dpi=settings.render_dpi) as engine:
        total = engine.page_count
        if total == 0:
            return False
        step = max(total // sample, 1)
        checked = with_text = 0
        for page_no in range(0, total, step):
            checked += 1
            if engine.has_text_layer(page_no):
                with_text += 1
    # Call it digital only if most sampled pages carry real text.
    return checked > 0 and with_text / checked >= 0.6


def index_pdf(
    grade: str,
    subject: str,
    pdf_path: Path | str,
    ocr_lang: str = "ara+eng",
    has_text_layer: bool | None = None,
    dpi: int | None = None,
    workers: int | None = None,
    progress=None,
) -> tuple[int, int]:
    """Index one arbitrary PDF into ``indexes/{grade}__{subject}``.

    Unlike :class:`Indexer`, this uses a *thread* pool rather than a process
    pool, so it is safe to call from inside a running server: OCR shells out to
    the ``tesseract`` process per page, which parallelizes across threads, and
    each thread opens its own PyMuPDF document.

    Args:
        has_text_layer: force digital/scanned handling; auto-detected if ``None``.
        progress: optional callback ``(done, total)`` for status reporting.

    Returns:
        ``(pages_indexed, pages_total)``.
    """
    import concurrent.futures as _futures

    settings.ensure_dirs()
    pdf_path = Path(pdf_path)
    dpi = dpi or settings.render_dpi
    workers = workers or min(8, max(1, (os.cpu_count() or 4) - 1))

    if has_text_layer is None:
        has_text_layer = detect_text_layer(pdf_path)

    with PdfEngine(pdf_path, dpi=dpi) as engine:
        total = engine.page_count

    force_ocr = has_text_layer is False
    jobs = [
        (str(pdf_path), n, ocr_lang, dpi, settings.tesseract_cmd, settings.tessdata_prefix, force_ocr)
        for n in range(total)
    ]

    stem = index_stem(grade, subject)
    jsonl_path = settings.index_dir / f"{stem}.jsonl"
    written = 0
    started = time.perf_counter()

    with jsonl_path.open("w", encoding="utf-8") as sink:
        with _futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for done, record in enumerate(pool.map(_index_one_page, jobs), start=1):
                if record is not None:
                    sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
                if progress is not None and done % 10 == 0:
                    progress(done, total)

    (settings.index_dir / f"{stem}.meta.json").write_text(
        json.dumps(
            {
                "grade": grade,
                "subject": subject,
                "source": pdf_path.name,
                "dpi": dpi,
                "ocr_lang": ocr_lang,
                "has_text_layer": has_text_layer,
                "pages_indexed": written,
                "pages_total": total,
                "seconds": round(time.perf_counter() - started, 1),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("index_pdf %s/%s: %d/%d pages", grade, subject, written, total)
    return written, total


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Elite Bot page index.")
    parser.add_argument("--force", action="store_true", help="rebuild even if unchanged")
    parser.add_argument("--subject", help="only this subject")
    parser.add_argument("--limit", type=int, help="only the first N pages (smoke test)")
    parser.add_argument("--workers", type=int, help="parallel workers")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    ocr = OcrEngine(settings.tesseract_cmd, settings.tessdata_prefix)
    if not ocr.available():
        logger.warning("tesseract not found at %r -- scanned pages will be skipped",
                       settings.tesseract_cmd)

    Indexer(workers=args.workers).build_all(
        force=args.force, subject=args.subject, limit=args.limit
    )


if __name__ == "__main__":
    main()
