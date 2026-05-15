"""Auth routes: signup, login, logout, me, forgot, reset."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.auth import (
    clear_session_cookie,
    get_current_user,
    get_data_dir,
    get_user_store,
    set_session_cookie,
    sign_reset_token,
    sign_session,
    verify_reset_token,
)
from lib.rate_limit import AUTH_LIMITER, rate_limit_dependency
from models.user import User, UserPublic
from services import agentmail_shim
from services.user_store import (
    EmailTakenError,
    InvalidEmailError,
    UserStore,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_auth_rate_limit = rate_limit_dependency(AUTH_LIMITER)

_RESET_INBOX = "grip-trial-out@agentmail.to"
_RESET_LINK_BASE = os.environ.get(
    "NEXUS_RESET_LINK_BASE", "https://free.donnaoss.com/reset",
)


class Credentials(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=8)


class ForgotRequest(BaseModel):
    email: str = Field(min_length=1)


class ResetRequest(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


def _issue_session(
    response: Response, user: User, data_dir: Path, store: UserStore,
) -> UserPublic:
    token = sign_session(user.id, data_dir, store=store)
    set_session_cookie(response, token)
    return UserPublic(id=user.id, email=user.email)


def _build_reset_email_body(reset_url: str) -> str:
    return (
        "<p>You requested a password reset for your ChiefOfStaff.pro account.</p>"
        f'<p><a href="{reset_url}">Click here to reset your password</a>.</p>'
        "<p>This link expires in 1 hour. If you did not request this, ignore this email.</p>"
    )


@router.post("/signup", response_model=UserPublic, dependencies=[Depends(_auth_rate_limit)])
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
    return _issue_session(response, user, data_dir, store)


@router.post("/login", response_model=UserPublic, dependencies=[Depends(_auth_rate_limit)])
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
    return _issue_session(response, user, data_dir, store)


@router.post("/logout")
def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(id=current_user.id, email=current_user.email)


@router.post(
    "/forgot",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_auth_rate_limit)],
)
def forgot(
    body: ForgotRequest,
    store: UserStore = Depends(get_user_store),
    data_dir: Path = Depends(get_data_dir),
) -> Response:
    """Always 204 — never reveal whether the email is registered."""
    user = store.get_by_email(body.email)
    if user is not None:
        token = sign_reset_token(user.email, data_dir)
        reset_url = f"{_RESET_LINK_BASE}?token={token}"
        agentmail_shim.send(
            inbox_id=_RESET_INBOX,
            to=user.email,
            subject="Reset your ChiefOfStaff.pro password",
            html_body=_build_reset_email_body(reset_url),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reset",
    response_model=UserPublic,
    dependencies=[Depends(_auth_rate_limit)],
)
def reset(
    body: ResetRequest,
    response: Response,
    store: UserStore = Depends(get_user_store),
    data_dir: Path = Depends(get_data_dir),
) -> UserPublic:
    email = verify_reset_token(body.token, data_dir)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link expired or invalid",
        )
    user = store.get_by_email(email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link expired or invalid",
        )
    updated = store.update_password(user.id, body.new_password)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link expired or invalid",
        )
    return _issue_session(response, updated, data_dir, store)
