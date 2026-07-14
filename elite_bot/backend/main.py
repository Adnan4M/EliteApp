"""FastAPI application factory and entry point.

Run with:  uvicorn backend.main:app --reload
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import admin, auth, codes, notifications, profile, search, support
from config import settings
from database import init_db

_STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings.ensure_dirs()
    init_db()  # creates app tables alongside the bot's

    app = FastAPI(
        title="Elite Prep-Year API",
        version="0.1.0",
        description="Backend for the Elite prep-year study app (shared with the bot).",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    for router in (auth, profile, search, codes, notifications, support, admin):
        app.include_router(router.router)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/admin-panel", response_class=HTMLResponse, include_in_schema=False)
    def admin_panel() -> HTMLResponse:
        html = (_STATIC_DIR / "admin.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
