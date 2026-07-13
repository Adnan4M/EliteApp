"""Shared FastAPI dependencies: DB session, current user, access gate."""

from __future__ import annotations

import datetime
from typing import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.models import AppUser, SemesterAccess
from backend.security import decode_token
from database import SessionLocal

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AppUser:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    user_id = decode_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user = db.get(AppUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


def _aware(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def has_semester_access(db: Session, user: AppUser, semester: str) -> bool:
    """True when a live trial or an unexpired grant covers this semester."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # Free trial covers the FIRST semester only.
    if semester == "first" and _aware(user.trial_end) and now <= _aware(user.trial_end):
        return True

    grant = (
        db.query(SemesterAccess)
        .filter(SemesterAccess.user_id == user.id, SemesterAccess.semester == semester)
        .first()
    )
    if grant is None:
        return False
    expires = _aware(grant.expires_at)
    return expires is None or now <= expires


def require_semester_access(semester: str):
    """Dependency factory that 402s when the user lacks access to ``semester``."""

    def _dep(user: AppUser = Depends(current_user), db: Session = Depends(get_db)) -> AppUser:
        if not has_semester_access(db, user, semester):
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"no active subscription for the {semester} semester",
            )
        return user

    return _dep
