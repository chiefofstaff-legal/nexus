"""Matter and MatterDocument Pydantic models.

A Matter represents a legal case/file. Documents, time entries, and tasks
can all be linked to a matter via ``matter_id``. Soft-delete is preferred
(``archived_at``) so historic billing remains intact.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _matter_id() -> str:
    return f"matter_{uuid.uuid4().hex[:12]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Matter(BaseModel):
    """A legal matter (case/file)."""

    id: str = Field(default_factory=_matter_id)
    name: str
    client: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=_utc_now)
    archived_at: Optional[datetime] = None


class MatterDocument(BaseModel):
    """Membership row linking a document to a matter."""

    matter_id: str
    document_id: str
    added_at: datetime = Field(default_factory=_utc_now)
