"""Google Gemini provider (via the ``google-generativeai`` SDK)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from services.ai.base import AIError, AINotConfigured, AIProvider, AIQuotaError

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _is_model_level_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return _is_quota_error(exc) or any(k in msg for k in (
        "404", "not_found", "not found", "unavailable",
    ))


def _attempt(operation: Callable[[], Any], model: str) -> Any:
    last: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return operation()
        except AINotConfigured:
            raise
        except AIError as exc:
            last = exc
            if _is_model_level_error(exc):
                raise
            logger.warning("gemini %s failed (attempt %d/%d): %s",
                           model, attempt, _MAX_ATTEMPTS, exc)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(0.6 * attempt)
    raise last if last else AIError(f"gemini {model} failed")


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash",
                 fallback_model: str = "", extra_models: str = "") -> None:
        self._api_key = api_key
        extras = [m.strip() for m in extra_models.split(",") if m.strip()]
        self._models = [m for m in (model, fallback_model, *extras) if m]
        self._configured = False

    def available(self) -> bool:
        return bool(self._api_key)

    def _ensure_configured(self):
        if self._configured:
            return
        if not self._api_key:
            raise AINotConfigured("GEMINI_API_KEY is not set")
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._configured = True
        except ImportError as exc:
            raise AINotConfigured("google-generativeai is not installed") from exc

    def _run(self, call_for_model: Callable[[str], Any]) -> Any:
        last: Exception | None = None
        for model in self._models:
            try:
                return _attempt(lambda: call_for_model(model), model)
            except AINotConfigured:
                raise
            except AIError as exc:
                last = exc
                if len(self._models) > 1:
                    logger.warning("gemini model %s unavailable, trying fallback: %s",
                                   model, str(exc)[:120])
        if last and _is_quota_error(last):
            raise AIQuotaError("all AI models are rate-limited or out of quota") from last
        raise last if last else AIError("all gemini models failed")

    def complete(self, prompt, *, system=None, temperature=0.3, max_tokens=1024) -> str:
        self._ensure_configured()
        import google.generativeai as genai
        from google.generativeai.types import GenerationConfig

        def _once(model_name: str) -> str:
            try:
                kwargs: dict = {"model_name": model_name}
                if system:
                    kwargs["system_instruction"] = system
                model = genai.GenerativeModel(**kwargs)
                resp = model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                text = (resp.text or "").strip()
                if not text:
                    raise AIError("gemini returned an empty response")
                return text
            except AIError:
                raise
            except Exception as exc:
                raise AIError(f"gemini request failed: {exc}") from exc

        return self._run(_once)

    def complete_json(self, prompt, *, schema=None, system=None,
                      temperature=0.2, max_tokens=2048) -> Any:
        self._ensure_configured()
        import google.generativeai as genai
        from google.generativeai.types import GenerationConfig

        def _once(model_name: str) -> Any:
            try:
                kwargs2: dict = {"model_name": model_name}
                if system:
                    kwargs2["system_instruction"] = system
                model = genai.GenerativeModel(**kwargs2)
                resp = model.generate_content(
                    prompt,
                    generation_config=GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                        response_mime_type="application/json",
                    ),
                )
                return _parse_json(resp.text or "")
            except AIError:
                raise
            except Exception as exc:
                raise AIError(f"gemini json request failed: {exc}") from exc

        return self._run(_once)


def _parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
        text = text.removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIError(f"gemini returned non-JSON: {text[:200]!r}") from exc
