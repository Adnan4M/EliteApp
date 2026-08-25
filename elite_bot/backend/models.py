"""SQLAlchemy models for the app backend.

These live in the same database as the bot's tables but are entirely separate:
the app authenticates by email/password and gates access per (year, semester)
with single-use codes, whereas the bot uses Telegram identity.

Year IDs
--------
"prep"   — السنة التحضيرية  (current)
"year1"  — السنة الأولى
"year2"  — السنة الثانية
… and so on as content is added.

Every content-bearing table carries a ``year`` column (default "prep") so that
all existing rows remain valid after the column is added via migration.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from database import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class AppUser(Base):
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=True)
    year = Column(String, default="prep")  # active academic year, e.g. "prep", "year1"
    created_at = Column(DateTime, default=_utcnow)
    last_login = Column(DateTime, nullable=True)
    gender = Column(String, nullable=True)          # 'male' | 'female'
    active_skin_id = Column(Integer, nullable=True)

    # Free trial applies to the FIRST semester only.
    trial_end = Column(DateTime, nullable=True)

    def start_trial(self, days: int) -> None:
        self.trial_end = _utcnow() + datetime.timedelta(days=days)


class SemesterAccess(Base):
    """Records that a user has access to one (year, semester) pair."""

    __tablename__ = "semester_access"
    __table_args__ = (UniqueConstraint("user_id", "year", "semester", name="uq_user_year_semester"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    year = Column(String, nullable=False, default="prep")
    semester = Column(String, nullable=False)  # "first" / "second"
    source = Column(String, default="code")    # "trial" / "code"
    granted_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=True)  # null = no expiry


class ActivationCode(Base):
    """A subscription code the admin issues; single- or multi-use per config."""

    __tablename__ = "activation_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    year = Column(String, nullable=False, default="prep")    # which academic year it unlocks
    semester = Column(String, nullable=False)                 # which semester it unlocks
    max_uses = Column(Integer, default=1)
    used_count = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    valid_days = Column(Integer, nullable=True)  # access duration; null = unlimited
    created_at = Column(DateTime, default=_utcnow)

    @property
    def is_available(self) -> bool:
        return self.enabled and self.used_count < self.max_uses


class CodeRedemption(Base):
    """Audit trail linking a code use to a user (prevents double-spend)."""

    __tablename__ = "code_redemptions"
    __table_args__ = (UniqueConstraint("code_id", "user_id", name="uq_code_user"),)

    id = Column(Integer, primary_key=True)
    code_id = Column(Integer, ForeignKey("activation_codes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    redeemed_at = Column(DateTime, default=_utcnow)


class AppProgress(Base):
    """Per-chapter progress percentage for one subject."""

    __tablename__ = "app_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "year", "semester", "subject_id", "chapter", name="uq_progress"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    year = Column(String, nullable=False, default="prep")
    semester = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    chapter = Column(String, nullable=False)
    percent = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class SubjectBook(Base):
    """The uploaded PDF backing one (semester, subject) and its index status.

    Subject *names* live in ``backend/content.py``; this table only records which
    file backs a subject, where it is indexed, and how indexing is going.
    """

    __tablename__ = "subject_books"
    __table_args__ = (UniqueConstraint("year", "semester", "subject_id", "source_file", name="uq_subject_book_file"),)

    id = Column(Integer, primary_key=True)
    year = Column(String, nullable=False, default="prep")
    semester = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)

    source_file = Column(String, nullable=False)   # relative to settings.pdf_dir
    index_grade = Column(String, nullable=False)    # scope used in indexes/{..}__{..}
    index_subject = Column(String, nullable=False)
    book_name = Column(String, nullable=True)       # display title for grouping
    academic_year = Column(String, nullable=True)   # e.g. "البكالوريا", "2024"
    ocr_lang = Column(String, default="ara+eng")
    has_text_layer = Column(Boolean, default=False)

    status = Column(String, default="indexing")     # indexing / ready / error
    error = Column(String, nullable=True)
    pages_indexed = Column(Integer, default=0)
    pages_total = Column(Integer, default=0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class PastQuestion(Base):
    """A real MCQ extracted from a past-year exam PDF."""

    __tablename__ = "past_questions"

    id            = Column(Integer, primary_key=True)
    year          = Column(String, nullable=False, index=True, default="prep")
    semester      = Column(String, nullable=False, index=True)
    subject_id    = Column(String, nullable=False, index=True)
    question      = Column(String, nullable=False)
    option_a      = Column(String, nullable=False)
    option_b      = Column(String, nullable=False)
    option_c      = Column(String, nullable=False)
    option_d      = Column(String, nullable=False)
    correct_index = Column(Integer, nullable=False)   # 0-3
    keywords      = Column(String, nullable=True)     # space-separated normalized keywords
    source_file   = Column(String, nullable=True)     # which PDF this came from
    created_at    = Column(DateTime, default=_utcnow)


class UserXp(Base):
    """XP and level for gamification."""

    __tablename__ = "user_xp"

    user_id = Column(Integer, ForeignKey("app_users.id"), primary_key=True)
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    total_challenges = Column(Integer, default=0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class StudyPair(Base):
    """Two students studying together."""

    __tablename__ = "study_pairs"

    id = Column(Integer, primary_key=True)
    user_a_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    user_b_id = Column(Integer, ForeignKey("app_users.id"), nullable=True, index=True)
    invite_code = Column(String, unique=True, nullable=True, index=True)
    status = Column(String, default="pending")  # pending / active / declined
    created_at = Column(DateTime, default=_utcnow)


class ChapterCompletion(Base):
    """A user marking a chapter as done."""

    __tablename__ = "chapter_completions"
    __table_args__ = (
        UniqueConstraint("user_id", "year", "semester", "subject_id", "chapter_key",
                         name="uq_chapter_completion"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    year = Column(String, nullable=False, default="prep")
    semester = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    chapter_key = Column(String, nullable=False)
    done_at = Column(DateTime, default=_utcnow)


class Challenge(Base):
    """A Kahoot-style challenge room."""

    __tablename__ = "challenges"

    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)           # "pair" / "open"
    year = Column(String, nullable=False, default="prep")
    semester = Column(String, nullable=False)
    subject_id = Column(String, nullable=False)
    chapters = Column(String, nullable=False)        # JSON list of chapter_key strings
    status = Column(String, default="lobby")         # lobby / active / finished
    host_id = Column(Integer, ForeignKey("app_users.id"), nullable=False)
    invite_code = Column(String, unique=True, nullable=True)  # 6-char code for pair challenges
    is_private = Column(Boolean, default=False)               # private open rooms hidden from list
    question_count = Column(Integer, default=10)              # how many questions in this game
    created_at = Column(DateTime, default=_utcnow)


class ChallengePlayer(Base):
    """A user who has joined a challenge."""

    __tablename__ = "challenge_players"
    __table_args__ = (UniqueConstraint("challenge_id", "user_id", name="uq_cp"),)

    id = Column(Integer, primary_key=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False)
    score = Column(Integer, default=0)
    xp_earned = Column(Integer, default=0)
    joined_at = Column(DateTime, default=_utcnow)


class ChallengeQuestion(Base):
    """One MCQ question belonging to a challenge."""

    __tablename__ = "challenge_questions"

    id = Column(Integer, primary_key=True)
    challenge_id = Column(Integer, ForeignKey("challenges.id"), nullable=False, index=True)
    q_index = Column(Integer, nullable=False)
    question = Column(String, nullable=False)
    options = Column(String, nullable=False)   # JSON list of 4 option strings
    correct_index = Column(Integer, nullable=False)


class SubjectMeta(Base):
    """Admin-editable display metadata for one subject."""

    __tablename__ = "subject_meta"
    __table_args__ = (
        UniqueConstraint("year", "semester", "subject_id", name="uq_subject_meta"),
    )

    id = Column(Integer, primary_key=True)
    year = Column(String, nullable=False, index=True, default="prep")
    semester = Column(String, nullable=False, index=True)
    subject_id = Column(String, nullable=False, index=True)
    name_ar = Column(String, nullable=True)   # Arabic display name


class SubjectChapter(Base):
    """Admin-defined chapter list for one subject."""

    __tablename__ = "subject_chapters"
    __table_args__ = (
        UniqueConstraint("year", "semester", "subject_id", "chapter_key", name="uq_subject_chapter"),
    )

    id = Column(Integer, primary_key=True)
    year = Column(String, nullable=False, index=True, default="prep")
    semester = Column(String, nullable=False, index=True)
    subject_id = Column(String, nullable=False, index=True)
    chapter_key = Column(String, nullable=False)
    chapter_name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    chapter_number = Column(Integer, nullable=True)  # display number, may have gaps
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)


class Skin(Base):
    """A character skin purchasable with XP."""

    __tablename__ = "skins"

    id = Column(Integer, primary_key=True)
    name_ar = Column(String, nullable=False)
    emoji = Column(String, nullable=False)     # displayed as avatar icon
    bg_color = Column(String, nullable=False)  # hex color e.g. "#3B82F6"
    price_xp = Column(Integer, default=0)      # 0 = free default
    gender = Column(String, nullable=True)     # 'male' | 'female' | null = any
    sort_order = Column(Integer, default=0)


class UserSkin(Base):
    """A skin the user owns (purchased or free)."""

    __tablename__ = "user_skins"
    __table_args__ = (UniqueConstraint("user_id", "skin_id", name="uq_user_skin"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    skin_id = Column(Integer, ForeignKey("skins.id"), nullable=False)
    purchased_at = Column(DateTime, default=_utcnow)


class Notification(Base):
    """A general announcement shown to all prep-year students."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
