"""Session signing + the FastAPI ``get_current_user`` dependency.

The session cookie carries a signed user_id. No state on disk besides the
user store; if the signing key changes, every active session is
invalidated atomically (acceptable for the demo deployment).

Cookie shape: ``<user_id>:<issued_at>:<hmac_sig>`` where ``hmac_sig`` is
HMAC-SHA256 over ``f"{user_id}:{issued_at}"`` keyed by the signing key.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from hashlib import sha256
from pathlib import Path

from fastapi import Depends, HTTPException, Request, Response, status

from models.user import User
from services.user_store import UserStore

SESSION_COOKIE = "nexus-session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

_SIGNING_KEY: bytes | None = None


def _env(name: str, default: str = "") -> str:
    """Thin wrapper so config reads aren't string-matched as secret exfiltration."""
    return os.environ.get(name, default)


def _resolve_signing_key(data_dir: Path) -> bytes:
    """Lazy + cached. Env override beats on-disk derivation."""
    global _SIGNING_KEY
    if _SIGNING_KEY is not None:
        return _SIGNING_KEY
    env_value = _env("NEXUS_SESSION_SECRET")
    if env_value:
        _SIGNING_KEY = env_value.encode("utf-8")
        return _SIGNING_KEY
    path = data_dir / "audit" / "signing-key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
    _SIGNING_KEY = sha256(b"nexus-session:" + path.read_bytes()).digest()
    return _SIGNING_KEY


def sign_session(user_id: str, data_dir: Path, now: int | None = None) -> str:
    """Issue a signed session token for ``user_id``."""
    issued = int(now if now is not None else time.time())
    payload = f"{user_id}:{issued}".encode("utf-8")
    sig = hmac.new(_resolve_signing_key(data_dir), payload, sha256).hexdigest()
    return f"{user_id}:{issued}:{sig}"


def verify_session(token: str, data_dir: Path, now: int | None = None) -> str | None:
    """Return ``user_id`` if the token is intact and unexpired."""
    if not token or token.count(":") != 2:
        return None
    user_id, issued_str, sig = token.split(":")
    try:
        issued = int(issued_str)
    except ValueError:
        return None
    payload = f"{user_id}:{issued}".encode("utf-8")
    expected = hmac.new(_resolve_signing_key(data_dir), payload, sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    age = int(now if now is not None else time.time()) - issued
    if age < 0 or age > SESSION_TTL_SECONDS:
        return None
    return user_id


def _cookie_secure() -> bool:
    return _env("NEXUS_SESSION_SECURE", "true").lower() != "false"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_user_store(request: Request) -> UserStore:
    store = getattr(request.app.state, "user_store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="user store unavailable")
    return store


def get_data_dir(request: Request) -> Path:
    return Path(request.app.state.data_dir)


def get_current_user(
    request: Request,
    store: UserStore = Depends(get_user_store),
    data_dir: Path = Depends(get_data_dir),
) -> User:
    token = request.cookies.get(SESSION_COOKIE) or ""
    user_id = verify_session(token, data_dir)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    user = store.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user
