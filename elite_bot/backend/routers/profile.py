"""Profile: subject progress, achievement updates, and class ranking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.content import (
    SEMESTER_FIRST,
    get_subject,
    is_valid_semester,
    subjects_for,
)
from backend.deps import current_user, get_db, has_semester_access
from backend.models import AppProgress, AppUser
from backend.schemas import ProfileOut, ProgressIn, RankOut, SubjectProgress

router = APIRouter(tags=["profile"])


def _subject_percent(db: Session, user_id: int, semester: str, subject_id: str) -> float:
    """Average chapter percentage for one subject (0 when nothing recorded)."""
    rows = (
        db.query(AppProgress.percent)
        .filter(
            AppProgress.user_id == user_id,
            AppProgress.semester == semester,
            AppProgress.subject_id == subject_id,
        )
        .all()
    )
    if not rows:
        return 0.0
    return round(sum(r[0] for r in rows) / len(rows), 1)


def _overall_percent(db: Session, user_id: int) -> float:
    rows = db.query(AppProgress.percent).filter(AppProgress.user_id == user_id).all()
    return round(sum(r[0] for r in rows) / len(rows), 1) if rows else 0.0


@router.get("/me", response_model=ProfileOut)
def me(
    semester: str = SEMESTER_FIRST,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    if not is_valid_semester(semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")

    unlocked = has_semester_access(db, user, semester)
    subjects = [
        SubjectProgress(
            subject_id=s.id,
            name_ar=s.name_ar,
            name_en=s.name_en,
            percent=_subject_percent(db, user.id, semester, s.id),
            locked=not unlocked,
        )
        for s in subjects_for(semester)
    ]

    rank, total = _rank(db, user.id)
    return ProfileOut(
        name=user.name,
        email=user.email,
        year=user.year,
        current_semester=semester,
        subjects=subjects,
        rank=rank,
        total_students=total,
    )


@router.post("/progress", status_code=status.HTTP_204_NO_CONTENT)
def update_progress(
    body: ProgressIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    if not is_valid_semester(body.semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    if get_subject(body.semester, body.subject_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown subject")
    if not has_semester_access(db, user, body.semester):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "semester not subscribed")

    row = (
        db.query(AppProgress)
        .filter(
            AppProgress.user_id == user.id,
            AppProgress.semester == body.semester,
            AppProgress.subject_id == body.subject_id,
            AppProgress.chapter == body.chapter,
        )
        .first()
    )
    if row is None:
        row = AppProgress(
            user_id=user.id,
            semester=body.semester,
            subject_id=body.subject_id,
            chapter=body.chapter,
        )
        db.add(row)
    row.percent = body.percent
    db.commit()


@router.get("/rank", response_model=RankOut)
def rank(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> RankOut:
    position, total = _rank(db, user.id)
    return RankOut(
        rank=position, total_students=total, overall_percent=_overall_percent(db, user.id)
    )


def _rank(db: Session, user_id: int) -> tuple[int | None, int]:
    """Rank a user among all students by overall average progress.

    Students with no progress rows are counted in the total but unranked.
    """
    from collections import defaultdict

    percents: dict[int, list[float]] = defaultdict(list)
    for uid, percent in db.query(AppProgress.user_id, AppProgress.percent).all():
        percents[uid].append(percent)

    scored = {uid: sum(values) / len(values) for uid, values in percents.items() if values}

    total = db.query(AppUser).count()
    if user_id not in scored:
        return (None, total)

    my_score = scored[user_id]
    higher = sum(1 for score in scored.values() if score > my_score)
    return (higher + 1, total)
