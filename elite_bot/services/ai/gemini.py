"""Google Gemini provider (via the ``google-genai`` SDK)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from services.ai.base import AIError, AINotConfigured, AIProvider, AIQuotaError

logger = logging.getLogger(__name__)

#: Transient failures (API blips, truncated JSON) are retried this many times.
_MAX_ATTEMPTS = 3


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _is_model_level_error(exc: Exception) -> bool:
    """True for errors where retrying the SAME model is pointless.

    Quota exhaustion (429) and model-unavailable (404) won't clear on a quick
    retry, so we skip straight to the fallback model instead of burning retries.
    """
    msg = str(exc).lower()
    return _is_quota_error(exc) or any(k in msg for k in (
        "404", "not_found", "not found", "unavailable",
    ))


def _attempt(operation: Callable[[], Any], model: str) -> Any:
    """Run one model's operation, retrying only genuinely transient failures."""
    last: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return operation()
        except AINotConfigured:
            raise
        except AIError as exc:
            last = exc
            if _is_model_level_error(exc):
                raise  # let the caller fall back to the next model
            logger.warning("gemini %s failed (attempt %d/%d): %s",
                           model, attempt, _MAX_ATTEMPTS, exc)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(0.6 * attempt)
    raise last if last else AIError(f"gemini {model} failed")


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-flash-latest",
                 fallback_model: str = "") -> None:
        self._api_key = api_key
        # Primary first, then the fallback (each free-tier model has its own quota).
        self._models = [m for m in (model, fallback_model) if m]
        self._client = None

    def available(self) -> bool:
        return bool(self._api_key)

    def _run(self, call_for_model: Callable[[str], Any]) -> Any:
        """Try each model in order; advance to the next on a model-level error."""
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

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise AINotConfigured("GEMINI_API_KEY is not set")
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise AINotConfigured("google-genai is not installed") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _config(self, *, system, temperature, max_tokens, json_mode: bool):
        from google.genai import types

        kwargs = dict(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json" if json_mode else None,
        )
        # These are short, factual generations; disable "thinking" so the whole
        # output budget goes to the answer (thinking models otherwise spend it
        # reasoning and can truncate the JSON). Ignored by non-thinking models.
        try:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except (AttributeError, TypeError):  # pragma: no cover -- older SDKs
            pass
        return types.GenerateContentConfig(**kwargs)

    def complete(self, prompt, *, system=None, temperature=0.3, max_tokens=1024) -> str:
        client = self._ensure_client()

        def _once(model: str) -> str:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=self._config(
                        system=system, temperature=temperature,
                        max_tokens=max_tokens, json_mode=False,
                    ),
                )
            except Exception as exc:  # noqa: BLE001 -- SDK raises many types
                raise AIError(f"gemini request failed: {exc}") from exc
            text = (resp.text or "").strip()
            if not text:
                raise AIError("gemini returned an empty response")
            return text

        return self._run(_once)

    def complete_json(self, prompt, *, schema=None, system=None,
                      temperature=0.2, max_tokens=2048) -> Any:
        # Note: the ``schema`` dict is only used by the fake provider to
        # synthesize test data. Here we rely on JSON mode plus the concrete
        # example the caller embeds in the prompt -- passing a JSON Schema in
        # the prompt makes the model echo the schema instead of producing data.
        client = self._ensure_client()

        def _once(model: str) -> Any:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=self._config(
                        system=system, temperature=temperature,
                        max_tokens=max_tokens, json_mode=True,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                raise AIError(f"gemini json request failed: {exc}") from exc
            return _parse_json(resp.text or "")

        return self._run(_once)


def _parse_json(text: str) -> Any:
    """Parse JSON, tolerating a stray markdown fence if the model adds one."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
        text = text.removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIError(f"gemini returned non-JSON: {text[:200]!r}") from exc
