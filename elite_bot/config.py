"""Central configuration for Elite AI Study Assistant.

All secrets are read from the environment (``.env``). Nothing sensitive lives in
source control. Import :data:`settings` rather than reading ``os.environ``
directly, so that validation happens in exactly one place.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR: Path = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()



@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable, validated application settings."""

    database_url: str
    ai_provider: str
    ai_model: str
    ai_model_fallback: str
    gemini_api_key: str
    tesseract_cmd: str
    tessdata_prefix: str
    app_jwt_secret: str
    app_admin_key: str
    support_telegram: str

    # Directories (created on demand by :meth:`ensure_dirs`)
    pdf_dir: Path = field(default=BASE_DIR)
    index_dir: Path = field(default=BASE_DIR / "indexes")
    cache_dir: Path = field(default=BASE_DIR / "cache")
    log_dir: Path = field(default=BASE_DIR / "logs")

    render_dpi: int = 300

    @classmethod
    def load(cls) -> "Settings":
        # Tesseract resolves TESSDATA_PREFIX against the process CWD, which
        # varies. Anchor it to the package directory instead.
        tessdata = _get("TESSDATA_PREFIX")
        if tessdata and not Path(tessdata).is_absolute():
            tessdata = str((BASE_DIR / tessdata).resolve())
        return cls(
            database_url=_get("DATABASE_URL", "sqlite:///elite.db"),
            ai_provider=_get("AI_PROVIDER", "gemini").lower(),
            ai_model=_get("GEMINI_MODEL", "gemini-flash-latest"),
            ai_model_fallback=_get("GEMINI_MODEL_FALLBACK"),
            gemini_api_key=_get("GEMINI_API_KEY"),
            tesseract_cmd=_get("TESSERACT_CMD", "tesseract"),
            tessdata_prefix=tessdata,
            app_jwt_secret=_get("APP_JWT_SECRET", "dev-only-insecure-change-me"),
            app_admin_key=_get("APP_ADMIN_KEY"),
            support_telegram=_get("SUPPORT_TELEGRAM", "https://t.me/EliteSupport"),
        )

    def ensure_dirs(self) -> None:
        """Create the runtime directories the app writes into."""
        for path in (self.index_dir, self.cache_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)


settings: Settings = Settings.load()
