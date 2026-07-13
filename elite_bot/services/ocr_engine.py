"""Tesseract OCR wrapper producing text *and* word bounding boxes.

The scanned Arabic textbooks have no text layer, so bounding boxes recovered
here are the only way to highlight a search hit on the page. See
``services/pdf_engine.py`` for the drawing side.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Tesseract TSV columns, in order.
_TSV_COLUMNS = 12
_COL_BLOCK, _COL_PAR, _COL_LINE = 2, 3, 4
_COL_LEFT, _COL_TOP, _COL_WIDTH, _COL_HEIGHT = 6, 7, 8, 9
_COL_CONF, _COL_TEXT = 10, 11

#: Words below this confidence are almost always noise read out of figures.
MIN_CONFIDENCE = 30.0


@dataclass(frozen=True, slots=True)
class Word:
    """A single OCR'd word and its pixel box, at the DPI the page was rendered."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float

    @property
    def box(self) -> tuple[int, int, int, int]:
        """``(x0, y0, x1, y1)`` pixel rectangle."""
        return self.left, self.top, self.left + self.width, self.top + self.height


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    words: tuple[Word, ...]


class OcrError(RuntimeError):
    """Raised when the Tesseract binary is missing or fails."""


class OcrEngine:
    """Thin, stateless wrapper around the ``tesseract`` CLI.

    Args:
        tesseract_cmd: Path to the ``tesseract`` executable.
        tessdata_prefix: Optional custom tessdata directory. If given it **must**
            also contain Tesseract's ``configs/`` folder, otherwise output
            configs such as ``tsv`` are silently ignored and Tesseract emits
            plain text instead of TSV.
    """

    def __init__(self, tesseract_cmd: str, tessdata_prefix: str = "") -> None:
        self._cmd = tesseract_cmd
        self._tessdata_prefix = tessdata_prefix

    def available(self) -> bool:
        try:
            subprocess.run([self._cmd, "--version"], capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return False
        return True

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self._tessdata_prefix:
            env["TESSDATA_PREFIX"] = self._tessdata_prefix
        return env

    def run(self, image_path: Path | str, lang: str = "ara", psm: int = 3) -> OcrResult:
        """OCR one page image, returning reconstructed text plus word boxes."""
        try:
            proc = subprocess.run(
                [str(self._cmd), str(image_path), "stdout", "-l", lang, "--psm", str(psm), "tsv"],
                capture_output=True,
                env=self._env(),
            )
        except OSError as exc:
            raise OcrError(f"Cannot run tesseract at {self._cmd!r}: {exc}") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", "replace").strip()
            raise OcrError(f"tesseract failed on {image_path}: {stderr[:300]}")

        return self._parse_tsv(proc.stdout.decode("utf-8", "replace"))

    @staticmethod
    def _parse_tsv(raw: str) -> OcrResult:
        words: list[Word] = []
        # Group words back into lines so the reconstructed text reads naturally.
        lines: dict[tuple[str, str, str], list[str]] = {}

        for row in raw.splitlines()[1:]:  # skip header
            parts = row.split("\t")
            if len(parts) < _TSV_COLUMNS:
                continue
            text = parts[_COL_TEXT].strip()
            if not text:
                continue
            try:
                confidence = float(parts[_COL_CONF])
            except ValueError:
                continue
            if confidence < MIN_CONFIDENCE:
                continue

            words.append(
                Word(
                    text=text,
                    left=int(parts[_COL_LEFT]),
                    top=int(parts[_COL_TOP]),
                    width=int(parts[_COL_WIDTH]),
                    height=int(parts[_COL_HEIGHT]),
                    confidence=confidence,
                )
            )
            key = (parts[_COL_BLOCK], parts[_COL_PAR], parts[_COL_LINE])
            lines.setdefault(key, []).append(text)

        text = "\n".join(" ".join(w) for w in lines.values())
        return OcrResult(text=text, words=tuple(words))
