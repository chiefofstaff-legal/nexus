"""User repository — JSONL on disk, bcrypt password hashing.

Single-writer assumption holds because the FastAPI app runs in a single
uvicorn process under pm2; if the deployment topology ever changes to
multi-process, swap this for SQLite without changing the public API.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import bcrypt

from models.user import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailTakenError(Exception):
    """Raised when signup tries to reuse an existing email."""


class InvalidEmailError(Exception):
    """Raised when the email syntax is rejected."""


class UserStore:
    """JSONL-backed user store. Atomic writes, in-process locking."""

    def __init__(self, data_dir: Path):
        self._path = Path(data_dir) / "users.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create(self, email: str, password: str) -> User:
        email = self._normalise_email(email)
        with self._lock:
            if self._find_by_email_unlocked(email) is not None:
                raise EmailTakenError(email)
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                password_hash=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._append(user)
            return user

    def get_by_email(self, email: str) -> User | None:
        try:
            email = self._normalise_email(email)
        except InvalidEmailError:
            return None
        with self._lock:
            return self._find_by_email_unlocked(email)

    def get_by_id(self, user_id: str) -> User | None:
        with self._lock:
            for entry in self._iter():
                if entry["id"] == user_id:
                    return User(**entry)
        return None

    def verify_password(self, user: User, password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8"))

    def _normalise_email(self, email: str) -> str:
        candidate = (email or "").strip().lower()
        if not _EMAIL_RE.match(candidate):
            raise InvalidEmailError(candidate)
        return candidate

    def _find_by_email_unlocked(self, email: str) -> User | None:
        for entry in self._iter():
            if entry["email"] == email:
                return User(**entry)
        return None

    def _iter(self):
        if not self._path.exists():
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def _append(self, user: User) -> None:
        existing = self._path.read_bytes() if self._path.exists() else b""
        new_line = (json.dumps(user.model_dump()) + "\n").encode("utf-8")
        fd, tmp_path = tempfile.mkstemp(
            prefix=".users.", suffix=".jsonl", dir=self._path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(existing)
                f.write(new_line)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
