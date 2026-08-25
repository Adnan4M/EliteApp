"""Kahoot-style challenge rooms with real-time WebSocket game engine."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
import string
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from backend.content import get_subject
from backend.deps import current_user, get_db
from backend.models import (
    AppUser, Challenge, ChapterCompletion, ChallengePlayer,
    ChallengeQuestion, Skin, UserXp,
)
from backend.security import decode_token
from database import SessionLocal

router = APIRouter(prefix="/challenges", tags=["challenges"])
logger = logging.getLogger(__name__)

QUESTION_SECONDS = 30
QUESTIONS_PER_GAME = 10
XP_PER_WIN = 50
XP_PER_CORRECT = 10
LOBBY_TIMEOUT_SECONDS = 5 * 60  # 5 minutes


# ─── in-memory game state ────────────────────────────────────────────────────

class _Room:
    def __init__(self, challenge_id: int, host_id: int) -> None:
        self.challenge_id = challenge_id
        self.host_id = host_id
        self.connections: dict[int, WebSocket] = {}   # user_id -> ws
        self.names: dict[int, str] = {}               # user_id -> display name
        self.skins: dict[int, dict | None] = {}       # user_id -> skin dict
        self.genders: dict[int, str | None] = {}      # user_id -> gender
        self.scores: dict[int, int] = {}              # user_id -> cumulative score
        self.answers: dict[int, tuple[int, float]] = {}  # user_id -> (answer_idx, elapsed)
        self.questions: list[dict[str, Any]] = []
        self.current_q = -1
        self.status = "lobby"
        self._timer: asyncio.Task | None = None

    async def broadcast(self, msg: dict[str, Any]) -> None:
        dead = []
        for uid, ws in self.connections.items():
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.connections.pop(uid, None)

    def lobby_snapshot(self) -> dict[str, Any]:
        return {
            "type": "lobby",
            "challenge_id": self.challenge_id,
            "players": [
                {
                    "user_id": uid,
                    "name": self.names.get(uid, "?"),
                    "score": self.scores.get(uid, 0),
                    "skin": self.skins.get(uid),
                    "gender": self.genders.get(uid),
                }
                for uid in self.connections
            ],
        }

    async def start_game(self) -> None:
        if not self.questions:
            await self.broadcast({"type": "error", "message": "لم يتم توليد الأسئلة. حاول مرة أخرى."})
            return
        self.status = "active"
        await self.broadcast({"type": "start", "total_questions": len(self.questions)})
        await asyncio.sleep(3)
        await self._next_question()

    async def _next_question(self) -> None:
        self.current_q += 1
        if self.current_q >= len(self.questions):
            await self._finish()
            return
        self.answers = {}
        q = self.questions[self.current_q]
        await self.broadcast({
            "type": "question",
            "index": self.current_q,
            "total": len(self.questions),
            "question": q["question"],
            "options": q["options"],
            "seconds": QUESTION_SECONDS,
        })
        self._timer = asyncio.create_task(self._question_timer())

    async def _question_timer(self) -> None:
        await asyncio.sleep(QUESTION_SECONDS)
        await self._reveal()

    async def receive_answer(self, user_id: int, answer_idx: int, elapsed: float) -> None:
        if user_id in self.answers:
            return
        self.answers[user_id] = (answer_idx, elapsed)
        # If everyone answered, reveal early
        if len(self.answers) >= len(self.connections):
            if self._timer and not self._timer.done():
                self._timer.cancel()
            await self._reveal()

    async def _reveal(self) -> None:
        if self._timer and not self._timer.done():
            self._timer.cancel()
        q = self.questions[self.current_q]
        correct = q["correct_index"]
        round_scores: dict[int, int] = {}
        for uid, (ans, elapsed) in self.answers.items():
            if ans == correct:
                speed_bonus = max(0, int((QUESTION_SECONDS - elapsed) / QUESTION_SECONDS * 500))
                pts = 500 + speed_bonus
            else:
                pts = 0
            self.scores[uid] = self.scores.get(uid, 0) + pts
            round_scores[uid] = pts

        leaderboard = sorted(
            [{
                "user_id": uid,
                "name": self.names.get(uid, "?"),
                "score": self.scores.get(uid, 0),
                "skin": self.skins.get(uid),
                "gender": self.genders.get(uid),
            } for uid in self.scores],
            key=lambda x: x["score"], reverse=True,
        )
        await self.broadcast({
            "type": "reveal",
            "correct_index": correct,
            "round_scores": {str(k): v for k, v in round_scores.items()},
            "total_scores": {str(k): v for k, v in self.scores.items()},
            "leaderboard": leaderboard,
            "answers": {str(k): v[0] for k, v in self.answers.items()},
        })
        await asyncio.sleep(5)
        await self._next_question()

    async def _finish(self) -> None:
        self.status = "finished"
        leaderboard = sorted(
            [{
                "user_id": uid,
                "name": self.names.get(uid, "?"),
                "score": self.scores.get(uid, 0),
                "skin": self.skins.get(uid),
                "gender": self.genders.get(uid),
            } for uid in self.connections],
            key=lambda x: x["score"], reverse=True,
        )
        winner_id = leaderboard[0]["user_id"] if leaderboard else None
        xp_awards: dict[int, int] = {}
        for i, entry in enumerate(leaderboard):
            uid = entry["user_id"]
            xp = XP_PER_WIN if uid == winner_id else max(5, XP_PER_WIN - i * 10)
            xp_awards[uid] = xp

        # Persist to DB
        _persist_results(self.challenge_id, self.scores, xp_awards)

        await self.broadcast({
            "type": "finished",
            "leaderboard": leaderboard,
            "xp_awards": {str(k): v for k, v in xp_awards.items()},
        })


_rooms: dict[int, _Room] = {}


def _get_or_create_room(challenge_id: int, host_id: int) -> _Room:
    if challenge_id not in _rooms:
        _rooms[challenge_id] = _Room(challenge_id, host_id)
    return _rooms[challenge_id]


def _persist_results(challenge_id: int, scores: dict[int, int], xp: dict[int, int]) -> None:
    db = SessionLocal()
    try:
        challenge = db.get(Challenge, challenge_id)
        if challenge:
            challenge.status = "finished"
        for uid, score in scores.items():
            cp = db.query(ChallengePlayer).filter_by(
                challenge_id=challenge_id, user_id=uid
            ).first()
            if cp:
                cp.score = score
                cp.xp_earned = xp.get(uid, 0)
            xp_row = db.get(UserXp, uid)
            if xp_row is None:
                xp_row = UserXp(user_id=uid)
                db.add(xp_row)
            xp_row.xp += xp.get(uid, 0)
            xp_row.level = max(1, xp_row.xp // 100 + 1)
            xp_row.total_challenges = (xp_row.total_challenges or 0) + 1
        db.commit()
    except Exception as exc:
        logger.warning("persist_results error: %s", exc)
    finally:
        db.close()


# ─── question generation ─────────────────────────────────────────────────────

def _questions_for_challenge(db: Session, challenge: Challenge, count: int | None = None) -> list[dict[str, Any]]:
    """Pull from PastQuestion bank first, fill with AI-generated if needed."""
    from backend.models import PastQuestion
    n = count or challenge.question_count or QUESTIONS_PER_GAME

    bank = db.query(PastQuestion).filter(
        PastQuestion.semester == challenge.semester,
        PastQuestion.subject_id == challenge.subject_id,
    ).all()
    random.shuffle(bank)
    questions: list[dict[str, Any]] = []
    for pq in bank[:n]:
        questions.append({
            "question": pq.question,
            "options": [pq.option_a, pq.option_b, pq.option_c, pq.option_d],
            "correct_index": pq.correct_index,
        })

    # Fill remaining slots with AI-generated questions
    if len(questions) < n:
        from backend.models import SubjectChapter
        chapter_keys = json.loads(challenge.chapters)
        ch_rows = []
        if chapter_keys:
            ch_rows = db.query(SubjectChapter).filter(
                SubjectChapter.semester == challenge.semester,
                SubjectChapter.subject_id == challenge.subject_id,
                SubjectChapter.chapter_key.in_(chapter_keys),
            ).all()
        chapter_names = [c.chapter_name for c in ch_rows] if ch_rows else chapter_keys
        page_ranges = [(c.page_start, c.page_end) for c in ch_rows] if ch_rows else []
        needed = n - len(questions)
        ai_qs = _ai_questions(
            challenge.semester, challenge.subject_id,
            chapter_names, needed, page_ranges=page_ranges or None,
        )
        questions.extend(ai_qs)

    return questions[:n]


def _ai_questions(
    semester: str,
    subject_id: str,
    chapter_names: list[str],
    count: int,
    page_ranges: list[tuple[int | None, int | None]] | None = None,
) -> list[dict[str, Any]]:
    try:
        from backend.content import get_subject, scope_index_for
        from services.ai import get_study_ai
        from services.search_engine import SearchEngine

        with SessionLocal() as db:
            index = scope_index_for(semester, db)

        # Resolve subject_id (lowercase) → English name used in the index
        subj = get_subject(semester, subject_id)
        index_subject = subj.name_en if subj else subject_id.capitalize()

        by_key = {(p.subject, p.page): p.text for p in index.pages}
        seen_pages: set[tuple] = set()
        contexts: list[str] = []

        # 1️⃣ Use page ranges if admin specified them — most precise
        if page_ranges:
            for p_start, p_end in page_ranges:
                if p_start is None and p_end is None:
                    continue
                lo = p_start or 1
                hi = p_end or 9999
                for p in index.pages:
                    if p.subject == index_subject and lo <= p.page <= hi:
                        pk = (p.subject, p.page)
                        if pk not in seen_pages:
                            seen_pages.add(pk)
                            if p.text:
                                contexts.append(p.text)
                if len(contexts) >= 12:
                    break

        # 2️⃣ Fall back: keyword search with chapter names
        if not contexts:
            engine = SearchEngine()
            for name in chapter_names:
                hits = engine.search(name, index, limit=4)
                for h in hits:
                    pk = (h.subject, h.page)
                    if pk not in seen_pages:
                        seen_pages.add(pk)
                        text = by_key.get(pk, "")
                        if text:
                            contexts.append(text)
                if len(contexts) >= 12:
                    break

        # 3️⃣ Last resort: any page for this subject
        if not contexts:
            contexts = [p.text for p in index.pages if p.subject == index_subject][:8]

        ai = get_study_ai()
        if not ai.available():
            logger.warning("AI not configured — no questions for challenge")
            return []

        keyword = " ".join(chapter_names[:3]) or index_subject
        mcqs = ai.questions(keyword, contexts, n=count, scope=semester)
        return [
            {
                "question": m.question,
                "options": m.options,
                "correct_index": m.correct_index,
            }
            for m in mcqs
        ]
    except Exception as exc:
        logger.warning("AI question generation failed: %s", exc)
        return []


# ─── REST endpoints ──────────────────────────────────────────────────────────

def _make_invite_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


@router.get("/mine")
def my_challenges(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lobby challenges the user created that are still open."""
    cutoff = datetime.now(timezone.utc)
    rows = db.query(Challenge).filter(
        Challenge.host_id == user.id,
        Challenge.status == "lobby",
    ).all()
    result = []
    for c in rows:
        created = c.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created is not None and (cutoff - created).total_seconds() > LOBBY_TIMEOUT_SECONDS:
            continue
        players = db.query(ChallengePlayer).filter_by(challenge_id=c.id).all()
        subj = get_subject(c.semester, c.subject_id)
        result.append({
            "challenge_id": c.id,
            "type": c.type,
            "subject_id": c.subject_id,
            "subject_name": subj.name_ar if subj else c.subject_id,
            "invite_code": c.invite_code,
            "player_count": len(players),
        })
    return result


@router.get("/pending")
def pending_challenges(
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Pair challenges the user has been pre-invited to (not yet started)."""
    cutoff = datetime.now(timezone.utc)
    players = db.query(ChallengePlayer).filter_by(user_id=user.id).all()
    result = []
    for cp in players:
        c = db.get(Challenge, cp.challenge_id)
        if c is None or c.host_id == user.id or c.status != "lobby":
            continue
        created = c.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created is not None and (cutoff - created).total_seconds() > LOBBY_TIMEOUT_SECONDS:
            continue
        host = db.get(AppUser, c.host_id)
        subj = get_subject(c.semester, c.subject_id)
        result.append({
            "challenge_id": c.id,
            "type": c.type,
            "subject_id": c.subject_id,
            "subject_name": subj.name_ar if subj else c.subject_id,
            "invite_code": c.invite_code,
            "host_name": host.name or host.email if host else "?",
        })
    return result


@router.post("")
def create_challenge(
    body: dict[str, Any],
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ctype = body.get("type", "open")
    semester = body.get("semester", "first")
    subject_id = body.get("subject_id", "")
    chapters = body.get("chapters", [])
    if not subject_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "subject_id required")

    invite_code = _make_invite_code()
    is_private = bool(body.get("is_private", False))
    question_count = max(5, min(30, int(body.get("question_count", 10))))
    challenge = Challenge(
        type=ctype,
        semester=semester,
        subject_id=subject_id,
        chapters=json.dumps(chapters),
        host_id=user.id,
        invite_code=invite_code,
        is_private=is_private,
        question_count=question_count,
    )
    db.add(challenge)
    db.flush()

    db.add(ChallengePlayer(challenge_id=challenge.id, user_id=user.id))

    # Pre-add partner for pair challenges (so they see it in pending without a code)
    partner_id = body.get("partner_id")
    if partner_id and ctype == "pair":
        partner = db.get(AppUser, int(partner_id))
        if partner:
            db.add(ChallengePlayer(challenge_id=challenge.id, user_id=int(partner_id)))

    # Pre-generate questions and store
    try:
        questions = _questions_for_challenge(db, challenge)
    except Exception as exc:
        logger.warning("question generation failed: %s", exc)
        questions = []
    for i, q in enumerate(questions):
        db.add(ChallengeQuestion(
            challenge_id=challenge.id,
            q_index=i,
            question=q["question"],
            options=json.dumps(q["options"]),
            correct_index=q["correct_index"],
        ))

    db.commit()
    return {
        "challenge_id": challenge.id,
        "type": ctype,
        "invite_code": invite_code,
        "question_count": len(questions),
    }


@router.get("/open")
def open_challenges(
    subject_id: str | None = None,
    semester: str | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    already_in = {
        cp.challenge_id
        for cp in db.query(ChallengePlayer).filter_by(user_id=user.id).all()
    }
    q = db.query(Challenge).filter(
        Challenge.type == "open",
        Challenge.status == "lobby",
        Challenge.is_private == False,  # noqa: E712
        ~Challenge.id.in_(already_in),
    )
    if subject_id:
        q = q.filter(Challenge.subject_id == subject_id)
    if semester:
        q = q.filter(Challenge.semester == semester)
    challenges = q.order_by(Challenge.created_at.desc()).limit(20).all()
    result = []
    for c in challenges:
        host = db.get(AppUser, c.host_id)
        player_count = db.query(ChallengePlayer).filter_by(challenge_id=c.id).count()
        subj = get_subject(c.semester, c.subject_id)
        result.append({
            "challenge_id": c.id,
            "subject_id": c.subject_id,
            "subject_name": subj.name_ar if subj else c.subject_id,
            "semester": c.semester,
            "host_name": host.name or host.email if host else "?",
            "player_count": player_count,
            "created_at": c.created_at.isoformat(),
        })
    return result


@router.post("/{challenge_id}/join")
def join_challenge(
    challenge_id: int,
    body: dict[str, str] | None = None,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "challenge not found")
    if challenge.status != "lobby":
        raise HTTPException(status.HTTP_409_CONFLICT, "challenge already started")

    existing = db.query(ChallengePlayer).filter_by(
        challenge_id=challenge_id, user_id=user.id
    ).first()

    # Pair challenge: already pre-added players can join without code; others need code
    if challenge.type == "pair" and not existing:
        code = (body or {}).get("invite_code", "")
        if code != challenge.invite_code:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "wrong invite code")

    if not existing:
        db.add(ChallengePlayer(challenge_id=challenge_id, user_id=user.id))
        db.commit()
    return {"challenge_id": challenge_id, "status": "joined"}


@router.post("/join-by-code")
def join_by_code(
    body: dict[str, str],
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Join a pair challenge using only the 6-char invite code."""
    code = body.get("code", "").strip().upper()
    if not code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "code required")
    challenge = db.query(Challenge).filter(Challenge.invite_code == code).first()
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invalid code")
    if challenge.status != "lobby":
        raise HTTPException(status.HTTP_409_CONFLICT, "challenge already started")
    existing = db.query(ChallengePlayer).filter_by(
        challenge_id=challenge.id, user_id=user.id
    ).first()
    if not existing:
        db.add(ChallengePlayer(challenge_id=challenge.id, user_id=user.id))
        db.commit()
    return {"challenge_id": challenge.id, "status": "joined"}


@router.delete("/{challenge_id}")
def cancel_challenge(
    challenge_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Host cancels/deletes a lobby challenge."""
    c = db.get(Challenge, challenge_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    if c.host_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the host can cancel")
    if c.status != "lobby":
        raise HTTPException(status.HTTP_409_CONFLICT, "challenge already started")
    c.status = "cancelled"
    db.commit()
    # Notify connected players and close the room
    room = _rooms.pop(challenge_id, None)
    if room:
        asyncio.create_task(room.broadcast({"type": "cancelled"}))
    return {"status": "cancelled"}


@router.get("/{challenge_id}")
def get_challenge(
    challenge_id: int,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    c = db.get(Challenge, challenge_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    players = db.query(ChallengePlayer).filter_by(challenge_id=challenge_id).all()
    player_data = []
    for cp in players:
        u = db.get(AppUser, cp.user_id)
        player_data.append({
            "user_id": cp.user_id,
            "name": u.name or u.email if u else "?",
            "score": cp.score,
            "xp_earned": cp.xp_earned,
        })
    return {
        "challenge_id": c.id,
        "type": c.type,
        "status": c.status,
        "subject_id": c.subject_id,
        "semester": c.semester,
        "invite_code": c.invite_code,
        "is_host": c.host_id == user.id,
        "players": player_data,
    }


# ─── WebSocket game ──────────────────────────────────────────────────────────

@router.websocket("/ws/{challenge_id}")
async def challenge_ws(
    challenge_id: int,
    websocket: WebSocket,
    token: str = "",
) -> None:
    # Auth via query param token
    user_id = decode_token(token)
    if user_id is None:
        await websocket.close(code=4001)
        return

    db = SessionLocal()
    try:
        challenge = db.get(Challenge, challenge_id)
        if challenge is None:
            await websocket.close(code=4004)
            return
        user = db.get(AppUser, user_id)
        if user is None:
            await websocket.close(code=4001)
            return

        # Load pre-generated questions
        q_rows = db.query(ChallengeQuestion).filter_by(
            challenge_id=challenge_id
        ).order_by(ChallengeQuestion.q_index).all()

        # If questions were never generated (AI failed at creation), retry now
        if not q_rows:
            logger.warning("challenge %s has no questions — regenerating", challenge_id)
            generated = _questions_for_challenge(db, challenge)
            for i, q in enumerate(generated):
                db.add(ChallengeQuestion(
                    challenge_id=challenge.id,
                    q_index=i,
                    question=q["question"],
                    options=json.dumps(q["options"]),
                    correct_index=q["correct_index"],
                ))
            db.commit()
            q_rows = db.query(ChallengeQuestion).filter_by(
                challenge_id=challenge_id
            ).order_by(ChallengeQuestion.q_index).all()

        questions = [
            {
                "question": q.question,
                "options": json.loads(q.options),
                "correct_index": q.correct_index,
            }
            for q in q_rows
        ]
        host_id = challenge.host_id
    finally:
        db.close()

    await websocket.accept()
    room = _get_or_create_room(challenge_id, host_id)
    room.connections[user_id] = websocket
    room.names[user_id] = user.name or user.email
    room.genders[user_id] = user.gender
    if user.active_skin_id:
        with SessionLocal() as _db:
            skin = _db.get(Skin, user.active_skin_id)
            room.skins[user_id] = (
                {"id": skin.id, "name_ar": skin.name_ar, "emoji": skin.emoji, "bg_color": skin.bg_color}
                if skin else None
            )
    else:
        room.skins[user_id] = None
    if user_id not in room.scores:
        room.scores[user_id] = 0
    if not room.questions:
        room.questions = questions

    # If game already active, send current question directly to the reconnecting player.
    if room.status == "active" and 0 <= room.current_q < len(room.questions):
        q = room.questions[room.current_q]
        try:
            await websocket.send_json({
                "type": "question",
                "index": room.current_q,
                "total": len(room.questions),
                "question": q["question"],
                "options": q["options"],
                "seconds": QUESTION_SECONDS,
            })
        except Exception:
            pass
    else:
        # Send each client their own correct state; also notify others of the new join.
        async def _send_lobby_to(uid: int, ws) -> None:
            try:
                await ws.send_json({**room.lobby_snapshot(), "is_host": uid == host_id})
            except Exception:
                pass

        for uid, ws in list(room.connections.items()):
            await _send_lobby_to(uid, ws)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "start" and user_id == host_id and room.status == "lobby":
                await room.start_game()
            elif mtype == "answer" and room.status == "active":
                idx = msg.get("index", -1)
                elapsed = float(msg.get("elapsed", QUESTION_SECONDS))
                await room.receive_answer(user_id, idx, elapsed)
            elif mtype in ("ping", "hello"):
                if room.status == "active" and 0 <= room.current_q < len(room.questions):
                    q = room.questions[room.current_q]
                    await websocket.send_json({
                        "type": "question",
                        "index": room.current_q,
                        "total": len(room.questions),
                        "question": q["question"],
                        "options": q["options"],
                        "seconds": QUESTION_SECONDS,
                    })
                else:
                    await _send_lobby_to(user_id, websocket)
    except WebSocketDisconnect:
        room.connections.pop(user_id, None)
        if room.connections:
            for uid, ws in list(room.connections.items()):
                await _send_lobby_to(uid, ws)
        else:
            _rooms.pop(challenge_id, None)


# ─── Auto-expiry background task ─────────────────────────────────────────────

async def _expire_stale_challenges() -> None:
    """Mark lobby challenges older than 5 min as expired and close their rooms."""
    while True:
        await asyncio.sleep(60)  # check every minute
        try:
            db = SessionLocal()
            try:
                cutoff = datetime.now(timezone.utc)
                stale = db.query(Challenge).filter(
                    Challenge.status == "lobby",
                ).all()
                for c in stale:
                    created = c.created_at
                    if created is not None and created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age = (cutoff - created).total_seconds() if created else 0
                    if age > LOBBY_TIMEOUT_SECONDS:
                        c.status = "expired"
                        room = _rooms.pop(c.id, None)
                        if room:
                            asyncio.create_task(room.broadcast({"type": "expired"}))
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("expiry task error: %s", exc)


def start_expiry_task() -> None:
    asyncio.create_task(_expire_stale_challenges())
