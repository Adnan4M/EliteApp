"""Study-with-me: pair management + chapter completion tracking."""
from __future__ import annotations

import datetime
import random
import string
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.deps import current_user, get_db
from backend.models import AppProgress, AppUser, ChapterCompletion, StudyPair, SubjectChapter, SubjectMeta, UserXp

router = APIRouter(prefix="/study", tags=["study"])


def _xp_row(db: Session, user_id: int) -> UserXp:
    row = db.get(UserXp, user_id)
    if row is None:
        row = UserXp(user_id=user_id)
        db.add(row)
        db.flush()
    return row


def _sync_progress(db: Session, user_id: int, semester: str, subject_id: str, year: str = "prep"):
    """Recalculate AppProgress percentage from ChapterCompletion vs SubjectChapter counts."""
    total = db.query(SubjectChapter).filter_by(semester=semester, subject_id=subject_id).count()
    if total == 0:
        return
    done = db.query(ChapterCompletion).filter_by(
        user_id=user_id, semester=semester, subject_id=subject_id,
    ).count()
    pct = round(done / total * 100, 1)
    row = (
        db.query(AppProgress)
        .filter_by(user_id=user_id, year=year, semester=semester, subject_id=subject_id)
        .first()
    )
    if row is None:
        row = AppProgress(
            user_id=user_id, year=year, semester=semester,
            subject_id=subject_id, chapter="__overall__",
        )
        db.add(row)
    row.percent = pct


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/curriculum")
def get_curriculum(
    semester: str = "first",
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return subjects and their admin-defined chapter lists."""
    rows = (
        db.query(SubjectChapter)
        .filter(SubjectChapter.semester == semester)
        .order_by(SubjectChapter.subject_id, SubjectChapter.sort_order)
        .all()
    )
    meta_rows = db.query(SubjectMeta).filter(SubjectMeta.semester == semester).all()
    name_ar_map = {m.subject_id: m.name_ar for m in meta_rows}

    subjects: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        subjects.setdefault(r.subject_id, []).append(
            {"key": r.chapter_key, "name": r.chapter_name, "number": r.chapter_number}
        )
    return [
        {"subject_id": sid, "name_ar": name_ar_map.get(sid) or sid, "chapters": chs}
        for sid, chs in subjects.items()
    ]


@router.get("/chapters")
def my_completions(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = db.query(ChapterCompletion).filter(
        ChapterCompletion.user_id == user.id
    ).all()
    return [
        {
            "semester": r.semester,
            "subject_id": r.subject_id,
            "chapter_key": r.chapter_key,
            "done_at": r.done_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/chapters/done")
def mark_chapter_done(
    body: dict[str, str],
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    semester = body.get("semester", "")
    subject_id = body.get("subject_id", "")
    chapter_key = body.get("chapter_key", "")
    if not all([semester, subject_id, chapter_key]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "missing fields")

    existing = db.query(ChapterCompletion).filter_by(
        user_id=user.id, semester=semester,
        subject_id=subject_id, chapter_key=chapter_key,
    ).first()
    if existing:
        return {"status": "already_done"}

    db.add(ChapterCompletion(
        user_id=user.id, semester=semester,
        subject_id=subject_id, chapter_key=chapter_key,
    ))
    # Award 10 XP for completing a chapter
    xp_row = _xp_row(db, user.id)
    xp_row.xp += 10
    xp_row.level = max(1, xp_row.xp // 100 + 1)
    _sync_progress(db, user.id, semester, subject_id)
    db.commit()
    return {"status": "done", "xp_awarded": 10}


@router.delete("/chapters/done")
def unmark_chapter(
    semester: str,
    subject_id: str,
    chapter_key: str,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.query(ChapterCompletion).filter_by(
        user_id=user.id, semester=semester,
        subject_id=subject_id, chapter_key=chapter_key,
    ).first()
    if row:
        db.delete(row)
        _sync_progress(db, user.id, semester, subject_id)
        db.commit()
    return {"status": "ok"}


# ── study pairs (code-based) ─────────────────────────────────────────────────

def _make_pair_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


@router.post("/pair/create")
def create_pair(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a new study pair and return the invite code to share."""
    # Reuse an existing pending pair the user already created
    existing = db.query(StudyPair).filter(
        StudyPair.user_a_id == user.id,
        StudyPair.status == "pending",
        StudyPair.user_b_id.is_(None),
    ).first()
    if existing:
        return {"pair_id": existing.id, "invite_code": existing.invite_code}

    code = _make_pair_code()
    while db.query(StudyPair).filter(StudyPair.invite_code == code).first():
        code = _make_pair_code()

    pair = StudyPair(user_a_id=user.id, user_b_id=None,
                     invite_code=code, status="pending")
    db.add(pair)
    db.commit()
    return {"pair_id": pair.id, "invite_code": code}


@router.post("/pair/join")
def join_pair(
    body: dict[str, str],
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Join a study pair using the invite code."""
    code = body.get("code", "").strip().upper()
    if not code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "code required")

    pair = db.query(StudyPair).filter(StudyPair.invite_code == code).first()
    if pair is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invalid code")
    if pair.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "code already used")
    if pair.user_a_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot join your own pair")

    pair.user_b_id = user.id
    pair.status = "active"
    db.commit()

    host = db.get(AppUser, pair.user_a_id)
    return {
        "pair_id": pair.id,
        "status": "active",
        "partner_name": host.name or host.email if host else "?",
    }


@router.delete("/pair/{pair_id}")
def leave_pair(
    pair_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    pair = db.get(StudyPair, pair_id)
    if pair is None or user.id not in (pair.user_a_id, pair.user_b_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pair not found")
    db.delete(pair)
    db.commit()
    return {"status": "left"}


@router.get("/pairs")
def my_pairs(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    pairs = db.query(StudyPair).filter(
        (StudyPair.user_a_id == user.id) | (StudyPair.user_b_id == user.id)
    ).all()
    result = []
    for p in pairs:
        is_host = p.user_a_id == user.id
        partner_id = p.user_b_id if is_host else p.user_a_id
        partner = db.get(AppUser, partner_id) if partner_id else None
        result.append({
            "pair_id": p.id,
            "partner_id": partner_id,
            "partner_name": (partner.name or partner.email) if partner else "في انتظار الانضمام",
            "partner_email": partner.email if partner else "",
            "status": p.status,
            "is_host": is_host,
        })
    return result


@router.get("/pair/{pair_id}/progress")
def pair_progress(
    pair_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    pair = db.get(StudyPair, pair_id)
    if pair is None or user.id not in (pair.user_a_id, pair.user_b_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pair not found")

    partner_id = pair.user_b_id if pair.user_a_id == user.id else pair.user_a_id
    partner = db.get(AppUser, partner_id)

    def _completions(uid: int) -> list[str]:
        rows = db.query(ChapterCompletion).filter(
            ChapterCompletion.user_id == uid
        ).all()
        return [r.chapter_key for r in rows]

    return {
        "me": {
            "user_id": user.id,
            "name": user.name or user.email,
            "done": _completions(user.id),
        },
        "partner": {
            "user_id": partner_id,
            "name": partner.name or partner.email if partner else "?",
            "done": _completions(partner_id),
        },
    }


@router.get("/word-of-day")
def word_of_day(
    semester: str = "first",
    user: AppUser = Depends(current_user),
) -> dict[str, Any]:
    """Return a daily Arabic medical term extracted from the search index."""
    import hashlib
    import json
    from config import settings

    today = datetime.date.today().isoformat()
    seed = int(hashlib.md5(f"{today}:{semester}".encode()).hexdigest(), 16)

    # Collect unique Arabic words (5+ chars) from all JSONL index files for this semester
    seen: set[str] = set()
    candidates: list[str] = []
    for path in sorted(settings.index_dir.glob(f"{semester}__*.jsonl")):
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    for word_entry in (entry.get("words") or []):
                        # word_entry is either a string or [text, x, y, w, h, conf]
                        w = (word_entry[0] if isinstance(word_entry, list) else str(word_entry)).strip()
                        arabic_chars = sum(1 for c in w if '؀' <= c <= 'ۿ')
                        if (
                            len(w) >= 5
                            and ' ' not in w          # single word only, no phrases
                            and w not in seen
                            and not any(c.isdigit() for c in w)
                            and arabic_chars >= 4     # mostly Arabic letters
                            and arabic_chars / len(w) >= 0.8  # not mixed with Latin
                        ):
                            seen.add(w)
                            candidates.append(w)
                    if len(candidates) >= 3000:
                        break
        except Exception:
            continue
        if len(candidates) >= 3000:
            break

    _FALLBACK_WORDS = [
        "الإرقاء", "الاستقلاب", "التنفس", "الهضم", "الدورة الدموية",
        "المناعة", "الهرمونات", "الأنزيمات", "التوازن الحمضي القاعدي",
        "الانتشار", "الأسموزية", "الالتهاب", "الفاجوسيتوزية", "الانتروبيا",
        "البروتين", "الكربوهيدرات", "الدهون", "الفيتامينات", "المعادن",
        "الخلية", "النواة", "الميتوكوندريا", "الريبوسوم", "الغشاء الخلوي",
        "الجهاز العصبي", "الجهاز الهضمي", "الجهاز التنفسي", "الجهاز البولي",
        "الأنسجة الضامة", "الأنسجة الظهارية", "الأنسجة العضلية", "الأنسجة العصبية",
        "الانقسام الخيطي", "الانقسام الاختزالي", "الجينات", "الكروموسومات",
        "التركيب الضوئي", "التنفس الخلوي", "دورة كريبس", "الفسفرة التأكسدية",
        "الناقلات العصبية", "الجهد الكهربائي", "الإرسال المشبكي", "مستقبلات الحس",
        "ضغط الدم", "معدل ضربات القلب", "الحجم الضربي", "النتاج القلبي",
        "أكسجة الدم", "ثاني أكسيد الكربون", "الهيموغلوبين", "مجموعة الدم",
        "الكليتان", "الترشيح الكبيبي", "إعادة الامتصاص", "الإفراز الكلوي",
    ]
    if not candidates:
        candidates = _FALLBACK_WORDS

    word = random.Random(seed).choice(candidates)

    definition = ""
    example = ""
    ai_debug = ""
    try:
        from services.ai import get_study_ai
        ai = get_study_ai()
        ai_debug = f"provider={type(ai.provider).__name__} available={ai.available()}"
        prompt = (
            f'اشرح المصطلح الطبي "{word}" في جملتين باللغة العربية لطالب سنة تحضيرية. '
            'الجملة الأولى: تعريف مباشر وبسيط. '
            'الجملة الثانية: مثال طبي واقعي يوضّح المفهوم. '
            'لا تستخدم تنسيق Markdown. لا تكتب عناوين أو نقاط. فقط الجملتين.'
        )
        raw = ai.provider.complete(prompt, temperature=0.2, max_tokens=200)
        ai_debug += f" | raw={raw[:80]!r}"
        raw = raw.strip().strip('*').strip()
        sentences = [s.strip() for s in raw.replace('\n', ' ').split('.')
                     if len(s.strip()) > 10]
        if sentences:
            definition = sentences[0] + '.'
        if len(sentences) > 1:
            example = '. '.join(sentences[1:]) + '.'
    except Exception as _e:
        ai_debug += f" | ERROR: {_e}"

    return {"word": word, "definition": definition, "example": example, "date": today, "semester": semester}


@router.get("/xp")
def my_xp(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = _xp_row(db, user.id)
    db.commit()
    return {
        "xp": row.xp,
        "level": row.level,
        "total_challenges": row.total_challenges,
        "next_level_xp": row.level * 100,
    }
