"""Password hashing and JWT issue/verify for the app backend."""

from __future__ import annotations

import datetime

import bcrypt
from jose import JWTError, jwt

from config import settings

# In production set APP_JWT_SECRET in .env; the fallback keeps dev running.
_SECRET = settings.app_jwt_secret
_ALGO = "HS256"
_TOKEN_TTL_HOURS = 24 * 14

# bcrypt hashes at most the first 72 bytes; truncate explicitly so long inputs
# don't raise (passlib's own probe is broken against bcrypt>=4.1, so we use the
# bcrypt library directly).
_BCRYPT_MAX = 72


def _prepare(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prepare(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + datetime.timedelta(hours=_TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGO)


def decode_token(token: str) -> int | None:
    """Return the user id encoded in a valid token, else ``None``."""
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None
