"""Tests for task notification dispatch (W6-C).

Three scenarios:
1. Log channel writes a JSONL record to notifications.jsonl.
2. Bad config (malformed channels list) soft-fails — no exception raised.
3. Task store still has the task when the notifier errors.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from pathlib import Path

import pytest

from services.task_manager import Task, Priority, TaskStatus, TaskStore
from services.task_notifier import notify_assignee


def _make_task(**kwargs) -> Task:
    defaults = dict(
        id="task_test001",
        title="Review contract",
        description="",
        assignee="Andre",
        matter="Müller",
        deadline=date(2026, 6, 1),
        priority=Priority.MEDIUM,
        status=TaskStatus.PENDING,
        created_at=datetime(2026, 5, 3, 12, 0, 0),
        raw_transcript="Andre please review the Müller contract by June 1",
    )
    defaults.update(kwargs)
    return Task(**defaults)


# --- Test 1: log channel writes JSONL record ---------------------------------

def test_log_channel_writes_jsonl_record(tmp_path: Path) -> None:
    config_path = tmp_path / "channels.yaml"
    config_path.write_text("channels:\n  - type: log\n")
    notifications_path = tmp_path / "notifications.jsonl"

    task = _make_task()
    notify_assignee(task, config_path=config_path, notifications_path=notifications_path)

    assert notifications_path.exists(), "notifications.jsonl was not created"
    lines = notifications_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["task_id"] == "task_test001"
    assert record["assignee"] == "Andre"
    assert record["matter"] == "Müller"
    assert record["deadline"] == "2026-06-01"
    assert "notified_at" in record


# --- Test 2: bad config soft-fails — no exception raised ---------------------

def test_bad_config_soft_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "channels.yaml"
    config_path.write_text("channels: not_a_list\n")  # malformed — not a list
    notifications_path = tmp_path / "notifications.jsonl"

    task = _make_task()
    # Must not raise — soft-fail contract
    notify_assignee(task, config_path=config_path, notifications_path=notifications_path)
    # Falls back to log channel, so record should still be written
    assert notifications_path.exists()


# --- Test 3: task store still has task when notifier errors ------------------

def test_task_store_intact_when_notifier_errors(tmp_path: Path) -> None:
    config_path = tmp_path / "bad_config.yaml"
    config_path.write_text(": invalid: yaml: [\n")  # unparseable YAML

    db_path = tmp_path / "test.db"
    store = TaskStore()
    store._db_path = db_path

    task = _make_task(id="task_store_check")
    stored = store.add(task)

    # Notifier with a deliberately broken config — must not raise
    notify_assignee(stored, config_path=config_path)

    # Task must still be retrievable from the store
    found = store.find("task_store_check")
    assert found is not None
    assert found.assignee == "Andre"
