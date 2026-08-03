"""Password hashing, JWT issue/verify, invite codes and content sanitisation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from yatraai.config import get_settings
from yatraai.core.errors import AuthenticationError

_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    # bcrypt truncates at 72 bytes; pre-hash so long passphrases keep entropy.
    digest = base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    return bcrypt.hashpw(digest, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    digest = base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    try:
        return bcrypt.checkpw(digest, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def create_access_token(
    user_id: uuid.UUID | str,
    *,
    email: str,
    is_admin: bool = False,
    ttl_minutes: int | None = None,
) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=ttl_minutes or s.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "email": email,
        "adm": is_admin,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "yatraai",
    }
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, expires


def decode_token(token: str) -> dict[str, Any]:
    """Verify a YatraAI token, falling back to a Supabase-issued token."""
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], issuer="yatraai")
    except jwt.PyJWTError:
        pass

    if s.supabase_jwt_secret:
        try:
            claims = jwt.decode(
                token,
                s.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_iss": False},
            )
            claims["_supabase"] = True
            return claims
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Invalid or expired token") from exc

    raise AuthenticationError("Invalid or expired token")


# --------------------------------------------------------------------------- #
# Invite codes
# --------------------------------------------------------------------------- #
def generate_invite_code(length: int = 8) -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(length))


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Content sanitisation
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str | None, *, max_length: int = 4000) -> str:
    """Strip markup and control characters from user-authored text.

    The frontend never renders raw HTML, but sanitising at the boundary keeps
    stored data clean for exports, LLM prompts and downstream consumers.
    """
    if not value:
        return ""
    cleaned = _TAG_RE.sub(" ", value)
    cleaned = _CTRL_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


# --------------------------------------------------------------------------- #
# Prompt-injection defence for RAG
# --------------------------------------------------------------------------- #
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(the\s+)?(system|previous)\s+(prompt|instructions)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"reveal\s+(your\s+)?(system\s+prompt|instructions)",
    r"</?(system|assistant|human)>",
    r"\bBEGIN\s+SYSTEM\b",
    r"print\s+your\s+(prompt|instructions)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def detect_prompt_injection(text: str) -> list[str]:
    """Return the injection patterns found in untrusted text (empty = clean)."""
    return [m.group(0) for m in _INJECTION_RE.finditer(text or "")]


def neutralize_prompt_injection(text: str) -> str:
    """Defang instruction-like spans so retrieved/user text cannot hijack the LLM."""
    return _INJECTION_RE.sub("[redacted-instruction]", text or "")


def hash_content(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()
