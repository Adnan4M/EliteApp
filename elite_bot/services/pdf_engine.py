"""PDF page rendering, text extraction, and search-hit highlighting.

Two kinds of page live in this corpus:

* **Digital pages** (``bio.pdf``) carry a real text layer; word boxes come from
  PyMuPDF directly.
* **Scanned pages** (``chem/hist/phys/bbio.pdf``) are images. They have no text
  layer at all, so word boxes must come from OCR.

Both paths end up as pixel boxes at a known DPI, which is what
:meth:`PdfEngine.render_page` draws onto.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from services.ocr_engine import Word

logger = logging.getLogger(__name__)

#: A page with fewer extractable characters than this is treated as a scan.
TEXT_LAYER_MIN_CHARS = 100

_POINTS_PER_INCH = 72.0

_HIGHLIGHT_FILL = (255, 235, 0, 80)
_HIGHLIGHT_OUTLINE = (235, 110, 0)


@dataclass(frozen=True, slots=True)
class PageText:
    """Text and word boxes for one page, in pixels at ``dpi``."""

    text: str
    words: tuple[Word, ...]
    dpi: int
    from_ocr: bool


class PdfEngine:
    """Renders and reads pages of a single PDF.

    The document handle is opened lazily and reused; call :meth:`close` (or use
    it as a context manager) when finished.
    """

    def __init__(self, pdf_path: Path | str, dpi: int = 300) -> None:
        self.pdf_path = Path(pdf_path)
        self.dpi = dpi
        self._doc: fitz.Document | None = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "PdfEngine":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def doc(self) -> fitz.Document:
        if self._doc is None:
            self._doc = fitz.open(self.pdf_path)
        return self._doc

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def _zoom(self) -> float:
        return self.dpi / _POINTS_PER_INCH

    # -- reading -----------------------------------------------------------
    def has_text_layer(self, page_number: int) -> bool:
        """True when the page carries enough real text to skip OCR."""
        return len(self.doc[page_number].get_text().strip()) >= TEXT_LAYER_MIN_CHARS

    def native_text(self, page_number: int) -> PageText:
        """Extract text and word boxes from a page's own text layer.

        Raises:
            ValueError: if the page has no usable text layer.
        """
        if not self.has_text_layer(page_number):
            raise ValueError(f"page {page_number} of {self.pdf_path.name} has no text layer")

        page = self.doc[page_number]
        zoom = self._zoom
        words: list[Word] = []
        # get_text("words") -> (x0, y0, x1, y1, word, block_no, line_no, word_no)
        for x0, y0, x1, y1, token, *_rest in page.get_text("words"):
            words.append(
                Word(
                    text=token,
                    left=int(x0 * zoom),
                    top=int(y0 * zoom),
                    width=int((x1 - x0) * zoom),
                    height=int((y1 - y0) * zoom),
                    confidence=100.0,
                )
            )
        return PageText(text=page.get_text(), words=tuple(words), dpi=self.dpi, from_ocr=False)

    def printed_label(self, page_number: int) -> str:
        """The page number *printed on the page*, which differs from the index.

        Falls back to the 1-based PDF index when the document has no page labels.
        """
        try:
            label = self.doc[page_number].get_label()
        except (AttributeError, RuntimeError):
            label = ""
        return label or str(page_number + 1)

    # -- rendering ---------------------------------------------------------
    def render_page(
        self,
        page_number: int,
        highlights: tuple[Word, ...] = (),
        scale: float = 1.0,
    ) -> bytes:
        """Render one page to PNG bytes, boxing every word in ``highlights``.

        Args:
            page_number: Zero-based page index.
            highlights: Words whose boxes are drawn. Their coordinates are
                assumed to be pixels at ``self.dpi``.
            scale: Downscale factor applied after drawing, to keep the image
                inside Telegram's upload limits.
        """
        page = self.doc[page_number]
        zoom = self._zoom * scale
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        png = pix.tobytes("png")

        if not highlights:
            return png

        # Import lazily: Pillow is only needed when something is highlighted.
        from PIL import Image, ImageDraw

        image = Image.open(io.BytesIO(png)).convert("RGB")
        overlay = ImageDraw.Draw(image, "RGBA")
        pad = max(2, int(4 * scale))
        for word in highlights:
            x0, y0, x1, y1 = (int(v * scale) for v in word.box)
            overlay.rectangle(
                [x0 - pad, y0 - pad, x1 + pad, y1 + pad],
                fill=_HIGHLIGHT_FILL,
                outline=_HIGHLIGHT_OUTLINE,
                width=max(2, int(4 * scale)),
            )

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    def render_page_image(self, page_number: int, path: Path) -> Path:
        """Render a page to ``path`` as PNG (used to feed the OCR engine)."""
        pix = self.doc[page_number].get_pixmap(matrix=fitz.Matrix(self._zoom, self._zoom))
        pix.save(str(path))
        return path
