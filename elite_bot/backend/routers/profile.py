"""Profile: subject progress, achievement updates, and class ranking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.content import (
    SEMESTER_FIRST,
    YEAR_PREP,
    available_years,
    get_subject,
    is_valid_semester,
    is_valid_year,
    subjects_for,
    year_label,
)
from backend.deps import current_user, get_db, has_semester_access
from backend.models import AppProgress, AppUser, SemesterAccess, Skin, StudyPair, UserXp
from backend.schemas import ProfileOut, ProgressIn, RankOut, SkinOut, SubjectProgress, YearOut

router = APIRouter(tags=["profile"])


def _subject_percent(db: Session, user_id: int, year: str, semester: str, subject_id: str) -> float:
    """Average chapter percentage for one subject (0 when nothing recorded)."""
    rows = (
        db.query(AppProgress.percent)
        .filter(
            AppProgress.user_id == user_id,
            AppProgress.year == year,
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
    year: str = YEAR_PREP,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    if not is_valid_semester(semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    if not is_valid_year(year):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown year")

    unlocked = has_semester_access(db, user, semester, year)
    subjects = [
        SubjectProgress(
            subject_id=s.id,
            name_ar=s.name_ar,
            name_en=s.name_en,
            percent=_subject_percent(db, user.id, year, semester, s.id),
            locked=not unlocked,
        )
        for s in subjects_for(semester, year=year)
    ]

    rank, total = _rank_among_friends(db, user.id)
    xp_row = db.query(UserXp).filter_by(user_id=user.id).first()
    active_skin = db.get(Skin, user.active_skin_id) if user.active_skin_id else None

    # Return all (year, semester) pairs the user has access to as "year:semester" strings
    activated = [
        f"{row.year}:{row.semester}"
        for row in db.query(SemesterAccess).filter_by(user_id=user.id).all()
    ]

    return ProfileOut(
        name=user.name,
        email=user.email,
        year=user.year,
        current_semester=semester,
        activated_semesters=activated,
        available_years=[
            YearOut(id=y, label_ar=year_label(y)) for y in available_years()
        ],
        subjects=subjects,
        rank=rank,
        total_students=total,
        gender=user.gender,
        active_skin=SkinOut(
            id=active_skin.id,
            name_ar=active_skin.name_ar,
            emoji=active_skin.emoji,
            bg_color=active_skin.bg_color,
        ) if active_skin else None,
        xp=xp_row.xp if xp_row else 0,
    )


@router.post("/progress", status_code=status.HTTP_204_NO_CONTENT)
def update_progress(
    body: ProgressIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    if not is_valid_semester(body.semester):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown semester")
    if not is_valid_year(body.year):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown year")
    if get_subject(body.semester, body.subject_id, year=body.year) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown subject")
    if not has_semester_access(db, user, body.semester, body.year):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "semester not subscribed")

    row = (
        db.query(AppProgress)
        .filter(
            AppProgress.user_id == user.id,
            AppProgress.year == body.year,
            AppProgress.semester == body.semester,
            AppProgress.subject_id == body.subject_id,
            AppProgress.chapter == body.chapter,
        )
        .first()
    )
    if row is None:
        row = AppProgress(
            user_id=user.id,
            year=body.year,
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
    """Rank a user among all students by overall average progress."""
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


def _rank_among_friends(db: Session, user_id: int) -> tuple[int | None, int]:
    """Rank a user among their study partners (friends) only."""
    from collections import defaultdict
    from sqlalchemy import or_

    # Collect friend IDs from StudyPair
    pairs = (
        db.query(StudyPair)
        .filter(
            or_(StudyPair.user_a_id == user_id, StudyPair.user_b_id == user_id),
            StudyPair.user_b_id.isnot(None),
        )
        .all()
    )
    friend_ids = set()
    for p in pairs:
        friend_ids.add(p.user_a_id)
        friend_ids.add(p.user_b_id)
    friend_ids.add(user_id)  # include self

    percents: dict[int, list[float]] = defaultdict(list)
    for uid, percent in (
        db.query(AppProgress.user_id, AppProgress.percent)
        .filter(AppProgress.user_id.in_(friend_ids))
        .all()
    ):
        percents[uid].append(percent)

    scored = {uid: sum(v) / len(v) for uid, v in percents.items() if v}

    total = len(friend_ids)
    if user_id not in scored:
        return (None, total)

    my_score = scored[user_id]
    higher = sum(1 for score in scored.values() if score > my_score)
    return (higher + 1, total)
