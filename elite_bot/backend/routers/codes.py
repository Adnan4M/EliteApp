"""Redeem a single-use activation code to unlock one semester."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.content import is_valid_semester
from backend.deps import current_user, get_db
from backend.models import ActivationCode, CodeRedemption, SemesterAccess
from backend.models import AppUser
from backend.schemas import RedeemIn, RedeemOut

router = APIRouter(prefix="/codes", tags=["codes"])


@router.post("/redeem", response_model=RedeemOut)
def redeem(
    body: RedeemIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> RedeemOut:
    code = (
        db.query(ActivationCode)
        .filter(ActivationCode.code == body.code.strip())
        .with_for_update(nowait=False)
        .first()
    )
    if code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "code not found")
    if not is_valid_semester(code.semester):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "code has an invalid semester")

    # Already redeemed by this user? Idempotent success -- checked BEFORE the
    # availability check so a single-use code re-entered by its owner still works.
    already = (
        db.query(CodeRedemption)
        .filter(CodeRedemption.code_id == code.id, CodeRedemption.user_id == user.id)
        .first()
    )
    if already:
        return RedeemOut(semester=code.semester, granted=True, message="already activated")

    if not code.is_available:
        raise HTTPException(status.HTTP_409_CONFLICT, "code disabled or fully used")

    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(days=code.valid_days) if code.valid_days else None

    db.add(CodeRedemption(code_id=code.id, user_id=user.id))
    code.used_count += 1

    access = (
        db.query(SemesterAccess)
        .filter(SemesterAccess.user_id == user.id, SemesterAccess.semester == code.semester)
        .first()
    )
    if access is None:
        db.add(
            SemesterAccess(
                user_id=user.id, semester=code.semester, source="code", expires_at=expires
            )
        )
    else:
        access.source = "code"
        access.expires_at = expires

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "code already redeemed")

    return RedeemOut(
        semester=code.semester, granted=True, message="semester activated successfully"
    )
