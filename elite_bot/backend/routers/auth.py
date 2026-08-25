"""Registration and login. New users get a 7-day first-semester trial."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.deps import get_db
from backend.models import AppUser, SemesterAccess
from backend.schemas import LoginIn, RegisterIn, TokenOut
from backend.security import create_token, hash_password, verify_password
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    if db.query(AppUser).filter(AppUser.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    user = AppUser(email=email, password_hash=hash_password(body.password), name=body.name)
    user.start_trial(settings.trial_days)
    db.add(user)
    db.flush()

    # Grant both semesters during the trial so new users see everything.
    for sem in ("first", "second"):
        db.add(
            SemesterAccess(
                user_id=user.id,
                semester=sem,
                source="trial",
                expires_at=user.trial_end,
            )
        )
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(AppUser).filter(AppUser.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    user.last_login = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return TokenOut(access_token=create_token(user.id))
