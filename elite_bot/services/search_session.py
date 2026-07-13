"""Short-lived, in-memory store for a user's active search.

Telegram callback payloads are capped at 64 bytes, so we cannot round-trip a
query and its results through ``callback_data``. Instead each search is given a
short id; the hits live here and the buttons carry only ``id`` + position.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from services.search_engine import PageHit

#: Sessions older than this are evicted lazily on the next access.
TTL_SECONDS = 60 * 30
_MAX_SESSIONS = 500


@dataclass(slots=True)
class SearchSession:
    query: str
    grade: str
    hits: list[PageHit]
    created_at: float = field(default_factory=time.monotonic)


class SearchSessionStore:
    """Process-local map of ``query_id -> SearchSession`` with TTL eviction."""

    def __init__(self) -> None:
        self._sessions: dict[str, SearchSession] = {}

    def _evict_expired(self) -> None:
        now = time.monotonic()
        stale = [k for k, s in self._sessions.items() if now - s.created_at > TTL_SECONDS]
        for key in stale:
            del self._sessions[key]
        # Hard cap as a safety net against unbounded growth.
        if len(self._sessions) > _MAX_SESSIONS:
            oldest = sorted(self._sessions.items(), key=lambda kv: kv[1].created_at)
            for key, _ in oldest[: len(self._sessions) - _MAX_SESSIONS]:
                del self._sessions[key]

    def create(self, query: str, grade: str, hits: list[PageHit]) -> str:
        self._evict_expired()
        query_id = secrets.token_urlsafe(6)
        self._sessions[query_id] = SearchSession(query=query, grade=grade, hits=hits)
        return query_id

    def get(self, query_id: str) -> SearchSession | None:
        self._evict_expired()
        return self._sessions.get(query_id)


#: Single shared store for the running bot.
store = SearchSessionStore()
