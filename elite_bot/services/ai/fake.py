"""Deterministic in-process provider for tests and offline development.

Synthesizes structurally valid responses from the requested JSON schema, so
feature code can be exercised end-to-end without any API key or network.
"""

from __future__ import annotations

from typing import Any

from services.ai.base import AIProvider


class FakeProvider(AIProvider):
    name = "fake"

    def available(self) -> bool:
        return True

    def complete(self, prompt, *, system=None, temperature=0.3, max_tokens=1024) -> str:
        # Echo a deterministic, obviously-fake sentence for assertions.
        head = prompt.strip().splitlines()[0][:60] if prompt.strip() else ""
        return f"[fake-summary] {head}"

    def complete_json(self, prompt, *, schema=None, system=None,
                      temperature=0.2, max_tokens=2048) -> Any:
        if schema is None:
            return {}
        return _synthesize(schema)


def _synthesize(schema: dict[str, Any], salt: str = "") -> Any:
    kind = schema.get("type")
    if kind == "object":
        return {k: _synthesize(v, salt) for k, v in schema.get("properties", {}).items()}
    if kind == "array":
        count = schema.get("minItems", 2)
        # Distinct salt per item so string values differ (e.g. MCQ options).
        return [_synthesize(schema["items"], f"{salt}{i}") for i in range(count)]
    if kind == "integer":
        return 0
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return True
    return f"sample{salt}"
