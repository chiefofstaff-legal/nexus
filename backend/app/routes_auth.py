"""Auth routes: signup, login, logout, me."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth import (
    clear_session_cookie,
    get_current_user,
    get_data_dir,
    get_user_store,
    set_session_cookie,
    sign_session,
)
from models.user import User, UserPublic
from services.user_store import (
    EmailTakenError,
    InvalidEmailError,
    UserStore,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=8)


def _issue_session(response: Response, user: User, data_dir: Path) -> UserPublic:
    token = sign_session(user.id, data_dir)
    set_session_cookie(response, token)
    return UserPublic(id=user.id, email=user.email)


@router.post("/signup", response_model=UserPublic)
def signup(
    creds: Credentials,
    response: Response,
    store: UserStore = Depends(get_user_store),
    data_dir: Path = Depends(get_data_dir),
) -> UserPublic:
    try:
        user = store.create(creds.email, creds.password)
    except EmailTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    except InvalidEmailError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email")
    return _issue_session(response, user, data_dir)


@router.post("/login", response_model=UserPublic)
def login(
    creds: Credentials,
    response: Response,
    store: UserStore = Depends(get_user_store),
    data_dir: Path = Depends(get_data_dir),
) -> UserPublic:
    user = store.get_by_email(creds.email)
    if user is None or not store.verify_password(user, creds.password):
        # Same message for both branches to avoid user enumeration.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _issue_session(response, user, data_dir)


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(id=current_user.id, email=current_user.email)
