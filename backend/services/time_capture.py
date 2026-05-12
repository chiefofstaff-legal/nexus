"""
Voice Time Capture Service
==========================

Voice-first billable time logging for Swiss law firms. Accepts a free-form
transcript (from the browser Web Speech API), uses Claude Haiku to parse
it into structured fields (matter, duration, description), stores the
entry in memory, and exposes a running CHF total at the default Swiss
hourly rate.

Design notes
------------
- Claude parsing is isolated behind ``transcribe_and_parse`` — if the API
  is unavailable the route layer can fall back to heuristic parsing
  without rewiring the service.
- The default hourly rate (450 CHF) matches the Swiss law firm average
  from the client discovery call.
- ``TimeEntryStore`` mirrors the in-memory pattern used by
  ``embedding_service`` and ``sop_engine`` so the POC stays consistent.
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from core.persistence import get_connection, init_schema
from services.pii_shield import PiiSession


DEFAULT_HOURLY_RATE_CHF = 450.0


class TimeEntry(BaseModel):
    """A single billable time entry."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    matter: str = ""
    matter_id: Optional[str] = None
    description: str = ""
    duration_minutes: int = 0
    hourly_rate_chf: float = DEFAULT_HOURLY_RATE_CHF
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_transcript: str = ""
    billable: bool = True

    @computed_field
    @property
    def value_chf(self) -> float:
        """CHF value of this entry based on duration and rate."""
        return round((self.duration_minutes / 60.0) * self.hourly_rate_chf, 2)


class ParseError(ValueError):
    """Raised when a transcript cannot be parsed into a time entry."""


_PARSE_SYSTEM = (
    "You are a Swiss legal time-capture assistant. Extract billable time "
    "fields from a single free-form lawyer dictation. Respond ONLY with "
    "minified JSON on a single line, no prose, no markdown fencing.\n"
    "Schema: "
    '{"matter": string, "description": string, "duration_minutes": int}\n'
    "- matter: the client or file name (e.g. 'Müller family', 'ACME AG v. Credit Suisse').\n"
    "- description: a crisp one-line summary of the work performed.\n"
    "- duration_minutes: the total time in minutes as an integer.\n"
    "If a field is genuinely missing, use '' for strings and 0 for the integer."
)


def _strip_fences(text: str) -> str:
    """Remove Markdown code fences Claude sometimes adds despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def _heuristic_duration(transcript: str) -> int:
    """Last-resort regex duration parser (e.g. '45 minutes', '1 hour 30')."""
    minutes = 0
    hr_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b", transcript, re.I)
    min_match = re.search(r"(\d+)\s*(?:minutes?|mins?|m)\b", transcript, re.I)
    if hr_match:
        minutes += int(float(hr_match.group(1)) * 60)
    if min_match:
        minutes += int(min_match.group(1))
    return minutes


def _claude_parse(transcript: str, client) -> dict:
    """Call Claude Haiku to structure a transcript. Raises ParseError on failure.

    PII Shield: client names, matter references, and person names are
    replaced with stable placeholders BEFORE the transcript leaves this
    process. Claude sees only placeholders. The de-anonymisation step
    restores the original strings on return so the stored entry is
    faithful to what the lawyer said. No real client data ever leaves
    the German server in this path.
    """
    if not client:
        raise ParseError("Anthropic client not configured")
    shield = PiiSession()
    anonymised, _mappings = shield.anonymize(transcript)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_PARSE_SYSTEM,
            messages=[{"role": "user", "content": anonymised}],
        )
        raw = _strip_fences(response.content[0].text)
        parsed = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        raise ParseError(f"Claude parse failed: {e}") from e
    # De-anonymise the string fields Claude can populate. Numeric fields
    # carry no PII and pass through untouched.
    if isinstance(parsed.get("matter"), str):
        parsed["matter"] = shield.deanonymize(parsed["matter"])
    if isinstance(parsed.get("description"), str):
        parsed["description"] = shield.deanonymize(parsed["description"])
    return parsed


def transcribe_and_parse(transcript: str, anthropic_client=None) -> dict:
    """Parse a free-form transcript into a structured time-entry dict.

    Falls back to a heuristic duration parser if Claude is unavailable so
    the feature remains usable offline for the POC demo. The PII Shield
    is applied inside ``_claude_parse`` — the heuristic fallback never
    contacts a remote LLM so no shield is needed there.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        raise ParseError("Transcript is empty")
    try:
        parsed = _claude_parse(transcript, anthropic_client)
    except ParseError:
        parsed = {
            "matter": "",
            "description": transcript[:200],
            "duration_minutes": _heuristic_duration(transcript),
        }
    return {
        "matter": str(parsed.get("matter") or "").strip(),
        "description": str(parsed.get("description") or "").strip(),
        "duration_minutes": max(int(parsed.get("duration_minutes") or 0), 0),
    }


_TIME_COLUMNS = (
    "id", "matter", "matter_id", "description", "duration_minutes",
    "hourly_rate_chf", "created_at", "raw_transcript", "billable",
)


def _row_to_time_entry(row: sqlite3.Row) -> TimeEntry:
    """Reconstruct a TimeEntry from a DB row.

    ``value_chf`` is a Pydantic computed field: derived on serialisation,
    never persisted. Don't pass it through here.
    """
    return TimeEntry(
        id=row["id"],
        matter=row["matter"],
        matter_id=row["matter_id"],
        description=row["description"],
        duration_minutes=row["duration_minutes"],
        hourly_rate_chf=row["hourly_rate_chf"],
        created_at=datetime.fromisoformat(row["created_at"]),
        raw_transcript=row["raw_transcript"],
        billable=bool(row["billable"]),
    )


class TimeEntryStore:
    """SQLite-backed store of billable time entries.

    Public API preserved verbatim from the in-memory version so the route
    layer needs no changes. Schema is initialised lazily on first call to
    avoid import-time DB creation during module load.
    """

    def __init__(self, default_rate_chf: float = DEFAULT_HOURLY_RATE_CHF):
        self.default_rate_chf = default_rate_chf
        self._db_path: Optional[Path] = None
        self._initialised = False

    def _ensure_init(self) -> None:
        if not self._initialised:
            init_schema(self._db_path)
            self._initialised = True

    def _conn(self) -> sqlite3.Connection:
        self._ensure_init()
        return get_connection(self._db_path)

    def log_time_entry(self, entry: TimeEntry, user_id: str = "") -> TimeEntry:
        """Persist an entry owned by ``user_id`` and return it.

        MT-FU W7: ``user_id`` partitions the table so multiple visitors
        on the public demo never see each other's entries. Legacy callers
        that pass no ``user_id`` get the empty-string bucket — that bucket
        is intentionally NOT readable from any authenticated GET path
        below, so legacy data is fenced off.
        """
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO time_entries"
                " (id, matter, matter_id, description, duration_minutes,"
                "  hourly_rate_chf, created_at, raw_transcript, billable,"
                "  user_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id, entry.matter, entry.matter_id, entry.description,
                    entry.duration_minutes, entry.hourly_rate_chf,
                    entry.created_at.isoformat(), entry.raw_transcript,
                    1 if entry.billable else 0,
                    user_id,
                ),
            )
        return entry

    def get_time_entries(self, user_id: str = "") -> list[TimeEntry]:
        """Return entries owned by ``user_id``, newest first.

        MT-FU W7 tenant filter. An empty ``user_id`` returns ONLY entries
        with an empty user_id — never a global join. A fresh signup with
        no entries yet sees an empty list, full stop.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM time_entries WHERE user_id = ?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [_row_to_time_entry(r) for r in rows]

    def update_matter(
        self, entry_id: str, matter: str, user_id: str = ""
    ) -> Optional[TimeEntry]:
        """Edit ``matter`` only if the caller owns the entry.

        MT-FU W7: returns None if the entry is not owned by ``user_id``,
        so an attacker who guesses an entry id from another tenant cannot
        mutate it.
        """
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE time_entries SET matter = ?"
                " WHERE id = ? AND user_id = ?",
                (matter.strip(), entry_id, user_id),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM time_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
        return _row_to_time_entry(row) if row else None

    def update_transcript(
        self, entry_id: str, transcript: str, user_id: str = ""
    ) -> Optional[TimeEntry]:
        """Edit the raw transcript only if the caller owns the entry."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE time_entries SET raw_transcript = ?"
                " WHERE id = ? AND user_id = ?",
                (transcript, entry_id, user_id),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM time_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
        return _row_to_time_entry(row) if row else None

    def get_daily_total_chf(
        self, rate: Optional[float] = None, user_id: str = ""
    ) -> dict:
        """Sum today's entries owned by ``user_id`` at the supplied rate."""
        effective_rate = rate if rate is not None else self.default_rate_chf
        today_iso = datetime.now(timezone.utc).date().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT duration_minutes FROM time_entries"
                " WHERE billable = 1 AND user_id = ?"
                " AND substr(created_at, 1, 10) = ?",
                (user_id, today_iso),
            ).fetchall()
        total_minutes = sum(int(r["duration_minutes"]) for r in rows)
        total_chf = round((total_minutes / 60.0) * effective_rate, 2)
        return {
            "entry_count": len(rows),
            "total_minutes": total_minutes,
            "total_hours": round(total_minutes / 60.0, 2),
            "hourly_rate_chf": effective_rate,
            "total_chf": total_chf,
            "total_value_chf": total_chf,
        }


def build_entry_from_transcript(
    transcript: str,
    anthropic_client=None,
    hourly_rate_chf: float = DEFAULT_HOURLY_RATE_CHF,
) -> TimeEntry:
    """Parse + construct a TimeEntry in one step. Raises ParseError on empty input."""
    parsed = transcribe_and_parse(transcript, anthropic_client)
    return TimeEntry(
        matter=parsed["matter"],
        description=parsed["description"],
        duration_minutes=parsed["duration_minutes"],
        hourly_rate_chf=hourly_rate_chf,
        raw_transcript=transcript,
    )
