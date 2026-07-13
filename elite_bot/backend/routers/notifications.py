"""General prep-year announcements."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.deps import current_user, get_db
from backend.models import AppUser, Notification
from backend.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[NotificationOut]:
    rows = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()
    return [
        NotificationOut(
            id=n.id, title=n.title, body=n.body, created_at=n.created_at.isoformat()
        )
        for n in rows
    ]
