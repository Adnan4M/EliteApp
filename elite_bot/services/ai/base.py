"""Provider-agnostic LLM interface.

Every concrete provider (Gemini now; OpenAI/Claude/local later) implements
:class:`AIProvider`. Feature code in ``features.py`` depends only on this
interface, so swapping providers is a config change, never a code change.
"""

from __future__ import annotations

import abc
from typing import Any


class AIError(RuntimeError):
    """A provider call failed (network, quota, malformed response)."""


class AINotConfigured(AIError):
    """No usable provider is configured (e.g. missing API key)."""


class AIQuotaError(AIError):
    """Every model's quota is exhausted (or rate-limited). Retry later."""


class AIProvider(abc.ABC):
    """Minimal text + JSON completion surface shared by all providers."""

    #: Human-readable provider name, e.g. ``"gemini"``.
    name: str = "base"

    @abc.abstractmethod
    def available(self) -> bool:
        """True when the provider can actually serve requests."""

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """Return a plain-text completion for ``prompt``."""

    @abc.abstractmethod
    def complete_json(
        self,
        prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Any:
        """Return a parsed JSON value for ``prompt`` (dict or list)."""
