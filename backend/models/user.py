"""User identity model — per-user partitioning key."""

from pydantic import BaseModel


class User(BaseModel):
    id: str
    email: str
    password_hash: str
    created_at: str


class UserPublic(BaseModel):
    id: str
    email: str
