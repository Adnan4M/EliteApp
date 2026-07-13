"""AI provider factory.

``get_provider()`` returns the configured provider (Gemini today), or a
:class:`NullProvider` when nothing is configured, so callers can always check
``.available()`` and fall back gracefully. Tests inject a provider via
``set_provider()``.
"""

from __future__ import annotations

import functools
import logging

from services.ai.base import AINotConfigured, AIError, AIProvider, AIQuotaError
from services.ai.features import Explanation, MCQ, StudyAI

logger = logging.getLogger(__name__)


class NullProvider(AIProvider):
    """Used when no provider is configured; every call reports unavailability."""

    name = "null"

    def available(self) -> bool:
        return False

    def complete(self, prompt, *, system=None, temperature=0.3, max_tokens=1024) -> str:
        raise AINotConfigured("no AI provider configured (set GEMINI_API_KEY)")

    def complete_json(self, prompt, *, schema=None, system=None,
                      temperature=0.2, max_tokens=2048):
        raise AINotConfigured("no AI provider configured (set GEMINI_API_KEY)")


_override: AIProvider | None = None


def set_provider(provider: AIProvider | None) -> None:
    """Inject a provider (e.g. a fake in tests); ``None`` restores the default."""
    global _override
    _override = provider
    get_provider.cache_clear()


@functools.lru_cache(maxsize=1)
def get_provider() -> AIProvider:
    if _override is not None:
        return _override

    from config import settings

    if settings.ai_provider == "gemini" and settings.gemini_api_key:
        from services.ai.gemini import GeminiProvider

        return GeminiProvider(
            settings.gemini_api_key,
            model=settings.ai_model,
            fallback_model=settings.ai_model_fallback,
        )

    logger.info("no AI provider configured; AI features will report unavailable")
    return NullProvider()


@functools.lru_cache(maxsize=1)
def _ai_cache():
    from config import settings
    from services.ai.cache import AICache

    return AICache(settings.cache_dir / "ai")


def get_study_ai() -> StudyAI:
    return StudyAI(get_provider(), cache=_ai_cache())


__all__ = [
    "AIError",
    "AINotConfigured",
    "AIQuotaError",
    "AIProvider",
    "Explanation",
    "MCQ",
    "NullProvider",
    "StudyAI",
    "get_provider",
    "get_study_ai",
    "set_provider",
]
