"""W6 — AbaPlato CSV export tests.

Verifies the export shape, escaping, math, and date format.

NOTE: column schema is a documented placeholder pending Leandro
clarification (see services/abaplato_export.py docstring).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from types import SimpleNamespace

from services.abaplato_export import export_time_entries_to_csv


def _entry(**kwargs) -> SimpleNamespace:
    """Build a TimeEntry-like duck object for the writer."""
    defaults = {
        "created_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
        "duration_minutes": 60,
        "matter": "Helvetica Corp v. Schmidt",
        "description": "Drafting brief",
        "billable": True,
        "hourly_rate_chf": 450.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_empty_list_returns_header_only():
    csv_str = export_time_entries_to_csv([])
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert len(rows) == 1
    assert rows[0] == [
        "date", "duration_minutes", "matter", "description",
        "billable", "hourly_rate_chf", "total_chf",
    ]


def test_single_entry_produces_two_rows():
    csv_str = export_time_entries_to_csv([_entry()])
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert len(rows) == 2  # header + 1 row
    header, data = rows
    assert data[0] == "2026-04-29"
    assert data[1] == "60"
    assert data[4] == "yes"


def test_total_chf_computation():
    """120 minutes at 450 CHF/h = 900.00 CHF."""
    csv_str = export_time_entries_to_csv([
        _entry(duration_minutes=120, hourly_rate_chf=450.0),
    ])
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert rows[1][6] == "900.0"


def test_csv_escaping_for_description_with_commas_and_quotes():
    """csv.writer must quote-escape fields containing commas or quotes."""
    csv_str = export_time_entries_to_csv([
        _entry(description='Drafted "memo, review, sign"'),
    ])
    # Round-trip: parse and verify the escaped field decodes correctly.
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert rows[1][3] == 'Drafted "memo, review, sign"'


def test_billable_false_renders_as_no():
    csv_str = export_time_entries_to_csv([_entry(billable=False)])
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert rows[1][4] == "no"


def test_iso_date_format():
    """Date must be ISO YYYY-MM-DD regardless of source datetime."""
    csv_str = export_time_entries_to_csv([
        _entry(created_at=datetime(2025, 12, 1, 14, 30, tzinfo=timezone.utc)),
    ])
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert rows[1][0] == "2025-12-01"


def test_multiple_entries_preserve_order():
    csv_str = export_time_entries_to_csv([
        _entry(description="first"),
        _entry(description="second"),
        _entry(description="third"),
    ])
    rows = list(csv.reader(io.StringIO(csv_str)))
    assert [r[3] for r in rows[1:]] == ["first", "second", "third"]
