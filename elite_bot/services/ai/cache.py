"""Disk-backed cache for AI feature results.

Summaries and explanations are the same for every student and cost an API call
each, so they are cached by ``(feature, scope, normalized-keyword)`` and reused
across users and restarts. Questions are cacheable too, but the bot's
"Generate More" passes ``force=True`` to bypass and regenerate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from utils.arabic import normalize

logger = logging.getLogger(__name__)

#: Bump when the cached value shape changes, to invalidate old entries.
_SCHEMA_VERSION = 1


class AICache:
    """Thread-safe JSON cache under ``<dir>/`` with an in-memory front."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._memory: dict[str, Any] = {}

    def _key(self, feature: str, scope: str, keyword: str) -> str:
        raw = f"{_SCHEMA_VERSION}|{feature}|{scope}|{normalize(keyword)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, feature: str, scope: str, keyword: str) -> Any | None:
        key = self._key(feature, scope, keyword)
        if key in self._memory:
            return self._memory[key]
        path = self._path(key)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))["value"]
        except (OSError, json.JSONDecodeError, KeyError):
            return None
        self._memory[key] = value
        return value

    def set(self, feature: str, scope: str, keyword: str, value: Any) -> None:
        key = self._key(feature, scope, keyword)
        self._memory[key] = value
        payload = {"feature": feature, "scope": scope, "keyword": keyword,
                   "ts": time.time(), "value": value}
        with self._lock:
            try:
                self._path(key).write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
            except OSError as exc:
                logger.warning("could not persist AI cache entry: %s", exc)
