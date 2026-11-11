import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, status

from .config import settings

password_hash = PasswordHasher()

_COMMON = {
    "password1234", "password12345", "passw0rd1234", "123456789012", "qwertyuiop12", "letmein12345",
    "welcome12345", "administrator", "iloveyou1234", "changeme1234", "pepai1234567", "admin1234567",
}


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return password_hash.check_needs_rehash(hashed)
    except Exception:
        return False


_dummy_hash: str | None = None


def dummy_verify(password: str) -> None:
    """Spend comparable time when the account does not exist (reduces user-enumeration timing)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _dummy_hash)


def validate_password_strength(password: str, email: str = "", full_name: str = "") -> list[str]:
    """Return a list of problems (empty = acceptable). Length >= 12 is enforced by the schema too."""
    problems: list[str] = []
    if len(password) < 12:
        problems.append("Password must be at least 12 characters long")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("Password must combine at least three of: lowercase, uppercase, digits, symbols")
    low = password.lower()
    if low in _COMMON or len(set(low)) < 5:
        problems.append("Password is too common or too repetitive")
    local = email.split("@")[0].lower() if email else ""
    if len(local) >= 4 and local in low:
        problems.append("Password must not contain your e-mail name")
    for part in re.split(r"\s+", full_name.lower().strip()):
        if len(part) >= 4 and part in low:
            problems.append("Password must not contain your name")
            break
    return problems


# ---------------------------------------------------------------- tokens
def create_access_token(user_id: int, token_version: int = 0) -> tuple[str, int]:
    expires = settings.access_token_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id), "iss": settings.jwt_issuer, "iat": now, "exp": now + timedelta(seconds=expires),
        "type": "access", "ver": int(token_version), "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), expires


def decode_access_claims(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        if payload.get("type") != "access":
            raise ValueError("Wrong token type")
        int(payload["sub"])
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token")


def decode_access_token(token: str) -> int:
    """Backward-compatible helper from the first package: returns the user id."""
    return int(decode_access_claims(token)["sub"])


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_opaque_token() -> tuple[str, str]:
    """(raw, sha256-hex). Only the hash is ever stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)
