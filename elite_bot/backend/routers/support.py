"""Technical support: a deep link to the support Telegram chat."""

from __future__ import annotations

from fastapi import APIRouter

from config import settings

router = APIRouter(prefix="/support", tags=["support"])


@router.get("")
def support() -> dict[str, str]:
    return {"telegram_url": settings.support_telegram}
