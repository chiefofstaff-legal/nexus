"""Export routes — AbaPlato CSV download.

New module: DO NOT modify routes.py or main.py.
Orchestrator wires export_router via include_router.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.persistence import get_connection, init_schema  # noqa: E402
from services.abaplato_export import export_time_entries_to_csv  # noqa: E402
from services.time_capture import TimeEntry  # noqa: E402


export_router = APIRouter(prefix="/api/exports", tags=["Exports"])


def _fetch_entries(from_date: str, to_date: str) -> list[TimeEntry]:
    """Load TimeEntry rows in [from_date, to_date] from SQLite.

    Uses the canonical persistence DB resolution (NEXUS_PERSISTENCE_DB env
    or the default in core.persistence). Hard-coding a home-relative path
    here would break on the VPS where the home is /home/grip not the
    developer's home.
    """
    init_schema()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, matter, matter_id, description, duration_minutes,
                   hourly_rate_chf, created_at, raw_transcript, billable
            FROM time_entries
            WHERE DATE(created_at) BETWEEN ? AND ?
            ORDER BY created_at
            """,
            (from_date, to_date),
        ).fetchall()

    entries = []
    for row in rows:
        entry = TimeEntry(
            id=row[0],
            matter=row[1] or "",
            matter_id=row[2],
            description=row[3] or "",
            duration_minutes=row[4] or 0,
            hourly_rate_chf=row[5] or 450.0,
            created_at=datetime.fromisoformat(row[6]) if row[6] else datetime.now(timezone.utc),
            raw_transcript=row[7] or "",
            billable=bool(row[8]),
        )
        entries.append(entry)
    return entries


@export_router.get("/abaplato")
def export_abaplato(
    from_date: str = Query(..., alias="from", description="Start date YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="End date YYYY-MM-DD"),
):
    """Download time entries as AbaPlato-compatible CSV.

    Query params: from=YYYY-MM-DD, to=YYYY-MM-DD.
    Returns text/csv with Content-Disposition attachment.
    """
    # Basic date validation
    for label, value in [("from", from_date), ("to", to_date)]:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date format for '{label}': expected YYYY-MM-DD",
            )

    entries = _fetch_entries(from_date, to_date)
    csv_content = export_time_entries_to_csv(entries)
    filename = f"abaplato-export-{from_date}-{to_date}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
