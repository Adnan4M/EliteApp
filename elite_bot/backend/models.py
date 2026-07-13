"""SQLAlchemy models for the app backend.

These live in the same database as the bot's tables but are entirely separate:
the app authenticates by email/password and gates access per semester with
single-use codes, whereas the bot uses Telegram identity.
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
    year = Column(String, default="prep")  # only prep year for now
    created_at = Column(DateTime, default=_utcnow)
    last_login = Column(DateTime, nullable=True)

    # Free trial applies to the FIRST semester only.
    trial_end = Column(DateTime, nullable=True)

    def start_trial(self, days: int) -> None:
        self.trial_end = _utcnow() + datetime.timedelta(days=days)


class SemesterAccess(Base):
    """Records that a user has access to one semester (trial or redeemed code)."""

    __tablename__ = "semester_access"
    __table_args__ = (UniqueConstraint("user_id", "semester", name="uq_user_semester"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
    semester = Column(String, nullable=False)  # "first" / "second"
    source = Column(String, default="code")    # "trial" / "code"
    granted_at = Column(DateTime, default=_utcnow)
    expires_at = Column(DateTime, nullable=True)  # null = no expiry


class ActivationCode(Base):
    """A subscription code the admin issues; single- or multi-use per config."""

    __tablename__ = "activation_codes"

    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    semester = Column(String, nullable=False)  # which semester it unlocks
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
        UniqueConstraint("user_id", "semester", "subject_id", "chapter", name="uq_progress"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False, index=True)
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
    __table_args__ = (UniqueConstraint("semester", "subject_id", "source_file", name="uq_subject_book_file"),)

    id = Column(Integer, primary_key=True)
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


class Notification(Base):
    """A general announcement shown to all prep-year students."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
