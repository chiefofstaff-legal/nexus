"""
Regression test: double-create bug in the task delegation flow.

Bug: POST /api/tasks/delegate calls delegate_from_transcript() which adds the
task to the store immediately. When the user clicks Confirm in the UI, a
second POST /api/tasks/create adds the same task again — resulting in 2 tasks.

Fix: POST /api/tasks/delegate must be parse-only. It returns the AI-parsed
preview for the user to review. POST /api/tasks/create is the sole storage
point.

TDD protocol:
  1. Run this file — tests fail (2 tasks, not 1).
  2. Fix the delegate route to call parse_delegation() without store.add().
  3. Run again — tests pass.
  Do NOT edit this test to make it pass; fix the code instead.
"""

import pytest
from httpx import AsyncClient, ASGITransport

import app.routes as routes_module
from app.main import app
from core.persistence import get_connection


def _clear_tasks_table() -> None:
    """Drop all rows from the SQLite tasks table (post-W1 migration)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM tasks")


@pytest.fixture(autouse=True)
def clear_task_store():
    """Isolate each test: empty the SQLite-backed task store before and after."""
    # Touch the store to ensure schema is initialised before DELETE.
    routes_module._task_store._ensure_init()
    _clear_tasks_table()
    yield
    _clear_tasks_table()


@pytest.mark.asyncio
async def test_delegate_does_not_persist_task():
    """
    /api/tasks/delegate must not write to the task store.
    It is a parse-only preview step; persistence is /api/tasks/create's job.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/tasks/delegate",
            json={
                "transcript": (
                    "Fabio, please review the Hauser employment contract by Thursday"
                )
            },
        )
    assert resp.status_code == 200

    stored = routes_module._task_store.list()
    assert len(stored) == 0, (
        f"/api/tasks/delegate persisted {len(stored)} task(s). "
        "It must only parse — use parse_delegation(), not delegate_from_transcript()."
    )


@pytest.mark.asyncio
async def test_full_delegation_flow_creates_exactly_one_task():
    """
    delegate (parse-only) → confirm (create) = exactly 1 task in the store.

    This is the core regression guard for the double-create bug.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Step 1: Delegate — AI parses the transcript into a preview.
        delegate_resp = await client.post(
            "/api/tasks/delegate",
            json={"transcript": "Andre, please draft the Schneider NDA by Friday"},
        )
        assert delegate_resp.status_code == 200
        preview = delegate_resp.json()

        # Step 2: User reviews the preview and clicks Confirm.
        confirm_resp = await client.post(
            "/api/tasks/create",
            json={
                "title": preview.get("title") or "Untitled task",
                "assignee": preview.get("assignee") or "",
                "matter": preview.get("matter") or "",
                "deadline": preview.get("deadline"),
                "priority": preview.get("priority") or "medium",
                "description": preview.get("description") or "",
                "raw_transcript": "Andre, please draft the Schneider NDA by Friday",
            },
        )
        assert confirm_resp.status_code == 200

        # Step 3: List — must contain exactly 1 task, not 2.
        list_resp = await client.get("/api/tasks/list")
        assert list_resp.status_code == 200
        tasks = list_resp.json().get("tasks", [])

    assert len(tasks) == 1, (
        f"Expected exactly 1 task after delegate+confirm, got {len(tasks)}. "
        "Double-create bug: /delegate must not call store.add()."
    )
    assert tasks[0]["title"] == preview.get("title"), (
        "Confirmed task title must match the delegate preview."
    )
