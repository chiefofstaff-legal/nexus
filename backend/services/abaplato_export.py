"""AbaPlato CSV export for billable time entries.

Produces a CSV string suitable for import into AbaPlato time-tracking software.

TODO: Confirm exact column schema with Leandro before production use.
      Using standard Swiss law-firm timesheet shape as documented assumption.
"""

from __future__ import annotations

import csv
import io


# TODO: Leandro to confirm column order and header names match AbaPlato import spec.
_HEADERS = [
    "date",
    "duration_minutes",
    "matter",
    "description",
    "billable",
    "hourly_rate_chf",
    "total_chf",
]


def _total_chf(duration_minutes: int, hourly_rate_chf: float) -> float:
    """Compute CHF amount: duration_minutes / 60 * hourly_rate_chf."""
    return round(duration_minutes / 60.0 * hourly_rate_chf, 2)


def export_time_entries_to_csv(entries: list) -> str:
    """Return a CSV string for *entries* (list of TimeEntry-like objects).

    Columns: date (ISO YYYY-MM-DD), duration_minutes, matter, description,
    billable, hourly_rate_chf, total_chf.

    Empty list returns header row only.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(_HEADERS)

    for entry in entries:
        created_at = getattr(entry, "created_at", None)
        date_str = created_at.strftime("%Y-%m-%d") if created_at else ""
        writer.writerow([
            date_str,
            getattr(entry, "duration_minutes", 0),
            getattr(entry, "matter", ""),
            getattr(entry, "description", ""),
            "yes" if getattr(entry, "billable", True) else "no",
            getattr(entry, "hourly_rate_chf", 0.0),
            _total_chf(
                getattr(entry, "duration_minutes", 0),
                getattr(entry, "hourly_rate_chf", 0.0),
            ),
        ])

    return buf.getvalue()
