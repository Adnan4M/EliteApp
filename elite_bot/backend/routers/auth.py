"""Registration, login, and email verification."""

from __future__ import annotations

import datetime
import logging
import random
import smtplib
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.deps import get_db
from backend.models import AppUser, SemesterAccess
from backend.schemas import LoginIn, RegisterIn, TokenOut, VerifyIn
from backend.security import create_token, hash_password, verify_password
from config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = {"gmail.com", "outlook.com", "hotmail.com"}


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def _send_verification_email(to_email: str, code: str) -> None:
    if not settings.smtp_email or not settings.smtp_password:
        logger.warning("SMTP not configured — skipping verification email")
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = f"X Word <{settings.smtp_email}>"
    msg["To"] = to_email
    msg["Subject"] = f"X Word — رمز التحقق: {code}"

    text = f"رمز التحقق الخاص بك هو: {code}\n\nصالح لمدة 10 دقائق."
    html = f"""\
<div dir="rtl" style="font-family:Arial,sans-serif;max-width:400px;margin:0 auto;padding:24px;">
  <h2 style="color:#00D4AA;text-align:center;">X Word</h2>
  <p style="text-align:center;font-size:16px;">رمز التحقق الخاص بك هو:</p>
  <div style="text-align:center;font-size:36px;font-weight:bold;letter-spacing:8px;
              background:#f0f2f5;padding:16px;border-radius:8px;margin:16px 0;">
    {code}
  </div>
  <p style="text-align:center;color:#666;font-size:13px;">صالح لمدة 10 دقائق</p>
</div>"""

    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.smtp_email, settings.smtp_password)
            server.sendmail(settings.smtp_email, to_email, msg.as_string())
    except Exception as exc:
        logger.error("failed to send verification email to %s: %s", to_email, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "فشل إرسال رمز التحقق") from exc


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower().strip()

    # Restrict to allowed domains
    domain = email.rsplit("@", 1)[-1]
    if domain not in ALLOWED_DOMAINS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "يُسمح فقط بالبريد من Gmail أو Outlook أو Hotmail",
        )

    if db.query(AppUser).filter(AppUser.email == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    # Check phone uniqueness if provided
    phone = (body.phone or "").strip()
    if phone:
        existing_phone = db.query(AppUser).filter(AppUser.phone == phone).first()
        if existing_phone:
            raise HTTPException(status.HTTP_409_CONFLICT, "رقم الهاتف مسجّل بالفعل")

    code = _generate_code()
    user = AppUser(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name,
        phone=phone or None,
        email_verified=False,
        verify_code=code,
        verify_code_expires=datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=10),
    )
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

    _send_verification_email(email, code)

    return TokenOut(access_token=create_token(user.id))


@router.post("/verify")
def verify_email(body: VerifyIn, db: Session = Depends(get_db)) -> dict[str, str]:
    email = body.email.lower().strip()
    user = db.query(AppUser).filter(AppUser.email == email).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "المستخدم غير موجود")
    if user.email_verified:
        return {"status": "already_verified"}
    if user.verify_code != body.code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "الرمز غير صحيح")
    if user.verify_code_expires and user.verify_code_expires < datetime.datetime.now(
        datetime.timezone.utc
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "انتهت صلاحية الرمز")

    user.email_verified = True
    user.verify_code = None
    user.verify_code_expires = None
    db.commit()
    return {"status": "verified"}


@router.post("/resend-code")
def resend_code(body: LoginIn, db: Session = Depends(get_db)) -> dict[str, str]:
    """Resend verification code (uses LoginIn since we just need email+password)."""
    email = body.email.lower().strip()
    user = db.query(AppUser).filter(AppUser.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "بيانات غير صحيحة")
    if user.email_verified:
        return {"status": "already_verified"}

    code = _generate_code()
    user.verify_code = code
    user.verify_code_expires = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(minutes=10)
    db.commit()

    _send_verification_email(email, code)
    return {"status": "sent"}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(AppUser).filter(AppUser.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "EMAIL_NOT_VERIFIED")
    user.last_login = datetime.datetime.now(datetime.timezone.utc)
    db.commit()
    return TokenOut(access_token=create_token(user.id))
