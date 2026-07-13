"""Arabic text normalization for search.

Students type without hamza, without harakat, and with inconsistent alef/ya
forms. The index and the query both pass through :func:`normalize` so that
``الاسكندرية`` matches the printed ``الإسكندرية``.
"""

from __future__ import annotations

import re
import unicodedata

# Harakat U+064B..U+0652, superscript alef U+0670, and tatweel U+0640.
_DIACRITICS = re.compile("[ً-ْٰـ]")
# Alef with hamza/madda variants, plus the bare alef wasla.
_ALEF = re.compile("[آأإٱ]")
# Anything that is neither Arabic-block nor word character becomes a separator.
_SEPARATOR = re.compile(r"[^؀-ۿ\w]+")

# Arabic-Indic digits -> ASCII, so "٦٢" and "62" both work.
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(text: str) -> str:
    """Fold a string into its search-canonical form.

    Strips diacritics and tatweel, unifies alef/ya/ta-marbuta variants, maps
    Arabic-Indic digits to ASCII, and lowercases Latin text. Punctuation is
    removed entirely, so this returns a single unbroken token for one word.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ARABIC_DIGITS)
    text = _DIACRITICS.sub("", text)
    text = _ALEF.sub("ا", text)          # أ إ آ ٱ -> ا
    text = text.replace("ى", "ي")   # ى -> ي
    text = text.replace("ة", "ه")   # ة -> ه
    text = text.replace("ؤ", "و")   # ؤ -> و
    text = text.replace("ئ", "ي")   # ئ -> ي
    text = _SEPARATOR.sub("", text)
    return text.strip().lower()


def tokenize(text: str) -> list[str]:
    """Split free text into normalized, non-empty search tokens."""
    if not text:
        return []
    raw = re.split(r"[^؀-ۿ\w]+", unicodedata.normalize("NFKC", text))
    return [t for t in (normalize(part) for part in raw) if t]


def matches(query_token: str, word: str) -> bool:
    """True when ``word`` contains ``query_token`` after normalization.

    Substring rather than equality so that a query for ``ضوء`` still hits
    ``الضوء`` (definite article) and simple plural/suffix forms.
    """
    if not query_token:
        return False
    return query_token in normalize(word)
