"""Pydantic model for a SummarySnapshot — one versioned summary of a matter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List


from pydantic import BaseModel, Field


class SummarySnapshot(BaseModel):
    """Immutable record of one auto-generated summary for a matter."""

    matter_id: str
    version_id: int
    content: str
    source_citations: List[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
