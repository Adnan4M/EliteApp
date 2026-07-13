"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


# -- auth -----------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str | None = Field(default=None, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -- profile --------------------------------------------------------------
class SubjectProgress(BaseModel):
    subject_id: str
    name_ar: str
    name_en: str
    percent: float
    locked: bool  # true when the semester is not subscribed


class ProfileOut(BaseModel):
    name: str | None
    email: EmailStr
    year: str
    current_semester: str
    subjects: list[SubjectProgress]
    rank: int | None
    total_students: int


class ProgressIn(BaseModel):
    semester: str
    subject_id: str
    chapter: str = Field(max_length=120)
    percent: float = Field(ge=0, le=100)


class RankOut(BaseModel):
    rank: int | None
    total_students: int
    overall_percent: float


# -- search ---------------------------------------------------------------
class SuggestOut(BaseModel):
    suggestions: list[str]


class LocationOut(BaseModel):
    semester: str
    subject_id: str
    subject_name: str
    book_id: str       # groups pages by the book they came from
    book_name: str
    academic_year: str
    source: str
    page: int          # zero-based PDF index
    printed: str       # page number printed on the page
    occurrences: int
    position: int      # index into the ordered result list, for /search/page


class SearchOut(BaseModel):
    query: str
    query_id: str
    total: int
    summary: str | None
    locations: list[LocationOut]


class SummaryOut(BaseModel):
    keyword: str
    summary: str
    ai_generated: bool  # false when it fell back to the extractive baseline


class ExplanationOut(BaseModel):
    keyword: str
    simple: str
    advanced: str
    real_life: str
    related: list[str]


class MCQOut(BaseModel):
    question: str
    options: list[str]
    correct_index: int


class QuestionsOut(BaseModel):
    keyword: str
    questions: list[MCQOut]


# -- codes ----------------------------------------------------------------
class RedeemIn(BaseModel):
    code: str = Field(min_length=3, max_length=64)


class RedeemOut(BaseModel):
    semester: str
    granted: bool
    message: str


# -- notifications --------------------------------------------------------
class NotificationOut(BaseModel):
    id: int
    title: str
    body: str
    created_at: str


# -- admin ----------------------------------------------------------------
class CreateCodeIn(BaseModel):
    semester: str
    count: int = Field(default=1, ge=1, le=1000)
    max_uses: int = Field(default=1, ge=1)
    valid_days: int | None = None


class CreateCodeOut(BaseModel):
    codes: list[str]


class BookStatusOut(BaseModel):
    semester: str
    subject_id: str
    source_file: str
    status: str          # indexing / ready / error
    error: str | None
    pages_indexed: int
    pages_total: int
    has_text_layer: bool
    updated_at: str


class SubjectStatusOut(BaseModel):
    subject_id: str
    name_ar: str
    name_en: str
    has_book: bool
    status: str | None       # book indexing status, or null if no upload
    pages_indexed: int
    pages_total: int


class CodeOut(BaseModel):
    code: str
    semester: str
    max_uses: int
    used_count: int
    enabled: bool
    available: bool


class StatsOut(BaseModel):
    total_users: int
    active_first: int
    active_second: int
    codes_total: int
    codes_available: int
    books_ready: int


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None
    created_at: str
    has_first: bool
    has_second: bool


class GrantAccessIn(BaseModel):
    semester: str
    days: int | None = Field(default=None, description="access length; null = unlimited")
    revoke: bool = False


class GrantAccessOut(BaseModel):
    user_id: int
    semester: str
    granted: bool
    expires_at: str | None
