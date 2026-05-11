"""Voice Delegation + Task Management.

Parses delegation transcripts via Claude Haiku and stores structured tasks.

Differentiation from time entries (critical client-validated distinction):
- Task: what needs doing (future, unbilled, assignable).
- Time entry: what was done and billed (past, recorded).

Never conflate the two.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from core.persistence import get_connection, init_schema
from core.roster_config import RosterConfigError, load_roster
from services.task_notifier import notify_assignee


# --- Enums ---

class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


# Roster externalised to ``config/roster.yaml`` (W3). Lazy-loaded on first
# read so module import stays cheap and tests can monkeypatch the path.
# Fallback to the historical NEXUS team roster only when the YAML is
# genuinely missing — RosterConfigError on malformed YAML must surface.
_FALLBACK_ASSIGNEES: tuple[str, ...] = ("Andre", "Arnold", "Fabio", "Mia", "Laurie")
_FALLBACK_ALIASES: dict[str, str] = {
    "andray": "Andre", "andré": "Andre", "andrew": "Andre", "andrei": "Andre",
    "arnot": "Arnold", "arnould": "Arnold",
    "fabio": "Fabio", "fabia": "Fabio",
    "mia": "Mia", "maya": "Mia", "mya": "Mia",
    "laurie": "Laurie", "lori": "Laurie", "lowry": "Laurie", "lourens": "Laurie",
}

_roster_cache: Optional[tuple[tuple[str, ...], dict[str, str]]] = None


def _get_roster() -> tuple[tuple[str, ...], dict[str, str]]:
    """Lazy-load and cache the roster. Falls back only when YAML missing."""
    global _roster_cache
    if _roster_cache is None:
        try:
            _roster_cache = load_roster()
        except RosterConfigError:
            # Missing file → fall back so the POC keeps running. Malformed
            # YAML still raises (RosterConfigError subclasses ValueError).
            _roster_cache = (_FALLBACK_ASSIGNEES, _FALLBACK_ALIASES)
    return _roster_cache


def reset_roster_cache() -> None:
    """Test hook — drop the cached roster so a new YAML path can load."""
    global _roster_cache
    _roster_cache = None


def _known_assignees() -> tuple[str, ...]:
    return _get_roster()[0]


def _alias_map() -> dict[str, str]:
    return _get_roster()[1]


class _RosterProxy(tuple):
    """Tuple-shaped read-through proxy so ``KNOWN_ASSIGNEES`` stays a public
    name while the underlying data loads from YAML on first access. Keeps
    backward compat for ``from services.task_manager import KNOWN_ASSIGNEES``.
    """

    def __new__(cls):
        return super().__new__(cls, ())

    def __iter__(self):
        return iter(_known_assignees())

    def __contains__(self, item):
        return item in _known_assignees()

    def __len__(self):
        return len(_known_assignees())

    def __getitem__(self, index):
        return _known_assignees()[index]


KNOWN_ASSIGNEES = _RosterProxy()

# Lazy spaCy instance (loaded on first NER call, None means not attempted yet).
_nlp = None


def _load_spacy():
    """Load the spaCy small English model once and cache it at module level."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except (ImportError, OSError):
            _nlp = False  # permanently skip if not available


def _extract_persons_spacy(text: str) -> list[str]:
    """Return unique PERSON entity surface forms via spaCy NER + roster scan.

    en_core_web_sm misses short or uncommon first names (e.g. "Fabio", "Mia")
    when they appear mid-sentence without surrounding context. The roster scan
    supplements spaCy by looking for KNOWN_ASSIGNEES names as whole words.
    """
    _load_spacy()
    seen: set[str] = set()
    persons: list[str] = []

    # spaCy pass
    if _nlp:
        doc = _nlp(text[:2000])
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                name = ent.text.strip()
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    persons.append(name)

    # Roster supplement — whole-word search for each known name
    for canonical in KNOWN_ASSIGNEES:
        if re.search(r"\b" + re.escape(canonical) + r"\b", text, re.IGNORECASE):
            if canonical.lower() not in seen:
                seen.add(canonical.lower())
                persons.append(canonical)

    return persons

_WEEKDAY_INDEX: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


# --- Pydantic models ---

class Task(BaseModel):
    """A delegated task. Distinct from a time entry."""
    id: str
    title: str
    description: str = ""
    assignee: str
    matter: str = ""
    matter_id: Optional[str] = None
    deadline: Optional[date] = None
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_transcript: str = ""


class ParsedDelegation(BaseModel):
    """Claude's structured extraction of a voice delegation."""
    title: str
    description: str = ""
    assignee: str = ""
    matter: str = ""
    deadline: Optional[date] = None
    priority: Priority = Priority.MEDIUM


# --- Helpers (DRY / JIT) ---

def _make_task_id(transcript: str, created_at: datetime) -> str:
    seed = f"{transcript}:{created_at.isoformat()}".encode()
    return "task_" + hashlib.sha256(seed).hexdigest()[:12]


def _next_weekday(from_date: date, weekday: int) -> date:
    """Return the next occurrence of ``weekday`` strictly after ``from_date``.

    If today is Thursday and weekday=Thursday, returns next Thursday
    (7 days ahead) — delegations rarely mean "today".
    """
    days_ahead = (weekday - from_date.weekday() + 7) % 7
    if days_ahead == 0:
        days_ahead = 7
    return from_date + timedelta(days=days_ahead)


def resolve_deadline(raw: Optional[str], today: Optional[date] = None) -> Optional[date]:
    """Convert Claude's textual deadline hint to an absolute date.

    Handles: ISO dates, weekday names, "tomorrow", "end of week".
    Returns None when no parse is possible — never guess.
    """
    if not raw:
        return None
    today = today or date.today()
    text = raw.strip().lower()

    try:
        return date.fromisoformat(text)
    except ValueError:
        pass

    if text in ("today",):
        return today
    if text in ("tomorrow",):
        return today + timedelta(days=1)
    if text in ("end of week", "eow", "this week"):
        return _next_weekday(today, 4)  # Friday

    for name, idx in _WEEKDAY_INDEX.items():
        if name in text:
            return _next_weekday(today, idx)
    return None


def _extract_json_block(raw: str) -> dict:
    """Pull the first JSON object out of an LLM response."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(match.group())


def _match_known_assignee(name: str) -> str:
    """Normalise a raw name to a canonical roster entry.

    Resolution order:
    1. Alias map (exact phonetic variants from voice STT).
    2. Exact substring match against KNOWN_ASSIGNEES (case-insensitive).
    3. Fuzzy match via difflib (cutoff 0.72) to catch minor transcription errors.
    4. Return the raw name as-is when all else fails.
    """
    if not name:
        return ""
    trimmed = name.strip()
    lower = trimmed.lower()

    # 1. Alias map
    aliases = _alias_map()
    if lower in aliases:
        return aliases[lower]

    # 2. Exact substring
    for canonical in KNOWN_ASSIGNEES:
        if canonical.lower() in lower or lower in canonical.lower():
            return canonical

    # 3. Fuzzy match — catches "Andrey" → "Andre", "Fabbia" → "Fabio"
    roster_lower = [c.lower() for c in KNOWN_ASSIGNEES]
    close = difflib.get_close_matches(lower, roster_lower, n=1, cutoff=0.72)
    if close:
        idx = roster_lower.index(close[0])
        return KNOWN_ASSIGNEES[idx]

    return trimmed


# --- Claude parsing ---

_PARSE_PROMPT_TEMPLATE = """Extract a delegated task from this voice transcript.

Known colleagues (prefer these if the speaker mentions them): {assignees}.
{spacy_hint}Today's date: {today}.

Rules for assignee:
- The transcript often starts with the assignee's name followed by a comma or "please".
- If a name from Known colleagues appears anywhere in the transcript, use it.
- If an unfamiliar name appears, return it exactly — do NOT invent a match.

Return ONLY valid JSON matching this schema:
{{
  "title": "short imperative title, under 12 words",
  "description": "any extra context from the transcript, may be empty",
  "assignee": "first name of the person to do it, or empty string",
  "matter": "case/matter name mentioned, e.g. 'Richter divorce', or empty string",
  "deadline": "ISO date YYYY-MM-DD, a weekday name, 'tomorrow', 'end of week', or null",
  "priority": "high|medium|low"
}}

Transcript:
{transcript}"""


async def parse_delegation(
    transcript: str,
    anthropic_client,
    today: Optional[date] = None,
) -> ParsedDelegation:
    """Call Claude Haiku to extract a structured delegation from voice text.

    Falls back to a heuristic when the Anthropic client is unavailable or
    the response cannot be parsed — the UI never deadlocks on LLM failure.
    """
    today = today or date.today()

    # spaCy PERSON extraction — provides a name hint to both Claude and heuristic
    spacy_persons = _extract_persons_spacy(transcript)
    if anthropic_client is None:
        return _heuristic_parse(transcript, spacy_persons)

    spacy_hint = (
        f"NER pre-extracted persons from transcript: {', '.join(spacy_persons)}.\n"
        if spacy_persons else ""
    )
    prompt = _PARSE_PROMPT_TEMPLATE.format(
        assignees=", ".join(KNOWN_ASSIGNEES),
        spacy_hint=spacy_hint,
        today=today.isoformat(),
        transcript=transcript.strip(),
    )

    try:
        response = await anthropic_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
        data = _extract_json_block(raw)
    except Exception:
        return _heuristic_parse(transcript)

    return _parsed_from_claude(data, today)


def _parsed_from_claude(data: dict, today: date) -> ParsedDelegation:
    """Coerce Claude's JSON into a ParsedDelegation with safe defaults."""
    deadline_raw = data.get("deadline")
    deadline = resolve_deadline(
        deadline_raw if isinstance(deadline_raw, str) else None,
        today,
    )
    priority_raw = str(data.get("priority", "medium")).lower()
    try:
        priority = Priority(priority_raw)
    except ValueError:
        priority = Priority.MEDIUM

    return ParsedDelegation(
        title=str(data.get("title") or "Untitled task").strip(),
        description=str(data.get("description") or "").strip(),
        assignee=_match_known_assignee(str(data.get("assignee") or "")),
        matter=str(data.get("matter") or "").strip(),
        deadline=deadline,
        priority=priority,
    )


def _heuristic_parse(
    transcript: str,
    spacy_persons: Optional[list[str]] = None,
) -> ParsedDelegation:
    """Deterministic fallback — no LLM required.

    Assignee resolution order:
    1. spaCy-extracted PERSON entities (if provided).
    2. Transcript starts with a known name + comma/please pattern.
    3. Any known assignee name found anywhere in the transcript.
    """
    lowered = transcript.lower()

    assignee = ""

    # 1. spaCy persons — try to match each to roster
    for person in (spacy_persons or []):
        candidate = _match_known_assignee(person)
        if candidate:
            assignee = candidate
            break

    # 2. "Name, please ..." or "Name please ..." at transcript start
    if not assignee:
        lead = re.match(r"^([A-Z][a-z]{1,20})[,\s]+(?:please\b)?", transcript.strip())
        if lead:
            assignee = _match_known_assignee(lead.group(1))

    # 3. Scan whole transcript for any roster name
    if not assignee:
        assignee = next(
            (n for n in KNOWN_ASSIGNEES if n.lower() in lowered),
            "",
        )

    deadline = resolve_deadline(lowered)
    title = transcript.strip()
    if len(title) > 80:
        title = title[:77] + "..."
    return ParsedDelegation(
        title=title or "Untitled task",
        description="",
        assignee=assignee,
        matter="",
        deadline=deadline,
        priority=Priority.MEDIUM,
    )


# --- Store ---

def _row_to_task(row: sqlite3.Row) -> Task:
    """Reconstruct a Task from a DB row.

    ``deadline`` is stored as ISO date string and rebuilt as ``date``;
    enums are coerced from their string values.
    """
    deadline_raw = row["deadline"]
    deadline_value = date.fromisoformat(deadline_raw) if deadline_raw else None
    return Task(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        assignee=row["assignee"],
        matter=row["matter"],
        matter_id=row["matter_id"],
        deadline=deadline_value,
        priority=Priority(row["priority"]),
        status=TaskStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        raw_transcript=row["raw_transcript"],
    )


class TaskStore:
    """SQLite-backed task store. Public API preserved verbatim from RAM POC."""

    def __init__(self) -> None:
        self._db_path: Optional[Path] = None
        self._initialised = False

    def _ensure_init(self) -> None:
        if not self._initialised:
            init_schema(self._db_path)
            self._initialised = True

    def _conn(self) -> sqlite3.Connection:
        self._ensure_init()
        return get_connection(self._db_path)

    def add(self, task: Task) -> Task:
        deadline_iso = task.deadline.isoformat() if task.deadline else None
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tasks"
                " (id, title, description, assignee, matter, matter_id,"
                "  deadline, priority, status, created_at, raw_transcript)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task.id, task.title, task.description, task.assignee,
                    task.matter, task.matter_id, deadline_iso,
                    task.priority.value, task.status.value,
                    task.created_at.isoformat(), task.raw_transcript,
                ),
            )
        return task

    def find(self, task_id: str) -> Optional[Task]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,),
            ).fetchone()
        return _row_to_task(row) if row else None

    def update_status(self, task_id: str, status: TaskStatus) -> Task:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status = ? WHERE id = ?",
                (status.value, task_id),
            )
            if cur.rowcount == 0:
                raise KeyError(task_id)
        result = self.find(task_id)
        if result is None:  # defensive — race between UPDATE and SELECT
            raise KeyError(task_id)
        return result

    def update_transcript(self, task_id: str, transcript: str) -> Task:
        """Correct the raw STT transcript on a delegated task."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE tasks SET raw_transcript = ? WHERE id = ?",
                (transcript, task_id),
            )
            if cur.rowcount == 0:
                raise KeyError(task_id)
        result = self.find(task_id)
        if result is None:
            raise KeyError(task_id)
        return result

    def list(
        self,
        assignee: Optional[str] = None,
        matter: Optional[str] = None,
        status: Optional[TaskStatus] = None,
    ) -> list[Task]:
        clauses, values = [], []
        if assignee:
            clauses.append("LOWER(assignee) = ?")
            values.append(assignee.lower())
        if matter:
            clauses.append("INSTR(LOWER(matter), ?) > 0")
            values.append(matter.lower())
        if status:
            clauses.append("status = ?")
            values.append(status.value)
        sql = "SELECT * FROM tasks"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(sql, values).fetchall()
        return [_row_to_task(r) for r in rows]


# --- Orchestration (route layer) ---

async def delegate_from_transcript(
    transcript: str,
    store: TaskStore,
    anthropic_client,
    today: Optional[date] = None,
) -> Task:
    """Parse a transcript into a task and persist it."""
    parsed = await parse_delegation(transcript, anthropic_client, today=today)
    now = datetime.utcnow()
    task = Task(
        id=_make_task_id(transcript, now),
        title=parsed.title,
        description=parsed.description,
        assignee=parsed.assignee,
        matter=parsed.matter,
        deadline=parsed.deadline,
        priority=parsed.priority,
        status=TaskStatus.PENDING,
        created_at=now,
        raw_transcript=transcript.strip(),
    )
    stored = store.add(task)
    notify_assignee(stored)
    return stored
