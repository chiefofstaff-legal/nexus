"""W6 — Calendar service tests.

Mirrors the email_service test shape using injected httpx.MockTransport.
"""

from __future__ import annotations

import json

import httpx
import pytest

from services.calendar_service import (
    CalendarService,
    CalendarServiceUnavailable,
)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/oauth2/v2.0/token"):
        return httpx.Response(200, json={"access_token": "tok"})
    if request.url.path.endswith("/calendar/events"):
        return httpx.Response(
            201,
            json={
                "id": "evt_xyz",
                "onlineMeeting": {"joinUrl": "https://teams.example.com/meet/abc"},
            },
        )
    return httpx.Response(404)


def _service_with_creds(transport=None) -> CalendarService:
    return CalendarService(
        tenant_id="tnt", client_id="cid",
        client_secret="sec", user_email="lawyer@example.com",
        transport=transport,
    )


def test_create_event_returns_event_id_and_meeting_url():
    transport = httpx.MockTransport(_ok_handler)
    svc = _service_with_creds(transport)
    result = svc.create_event(
        title="Client meeting",
        start="2026-05-01T09:00:00",
        end="2026-05-01T10:00:00",
        attendees=["client@example.com"],
        location="Zurich Office",
        body="Quarterly review",
    )
    assert result["event_id"] == "evt_xyz"
    assert "teams.example.com" in result["meeting_url"]
    assert "created_at" in result


def test_create_event_payload_uses_zurich_timezone():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/calendar/events"):
            captured["payload"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"id": "evt"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    svc = _service_with_creds(transport)
    svc.create_event(
        title="t", start="2026-05-01T09:00:00",
        end="2026-05-01T10:00:00", attendees=[],
    )
    assert captured["payload"]["start"]["timeZone"] == "Europe/Zurich"
    assert captured["payload"]["end"]["timeZone"] == "Europe/Zurich"


def test_create_event_attendees_serialised_as_required():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/calendar/events"):
            captured["payload"] = json.loads(request.content.decode())
            return httpx.Response(201, json={"id": "evt"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    svc = _service_with_creds(transport)
    svc.create_event(
        title="t", start="2026-05-01T09:00:00",
        end="2026-05-01T10:00:00",
        attendees=["a@example.com", "b@example.com"],
    )
    types = [a["type"] for a in captured["payload"]["attendees"]]
    assert all(t == "required" for t in types)


def test_missing_credentials_raises_unavailable(monkeypatch):
    for var in (
        "MS_GRAPH_TENANT_ID", "MS_GRAPH_CLIENT_ID",
        "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_USER_EMAIL",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(CalendarServiceUnavailable):
        CalendarService()


@pytest.mark.asyncio
async def test_voice_to_event_heuristic_fallback_when_no_client():
    from services.voice_to_event import parse_voice_to_event
    result = await parse_voice_to_event(
        "Schedule a meeting with Maria tomorrow at 10am about the Schmidt matter",
        anthropic_client=None,
    )
    assert "title" in result
    assert "start_iso" in result or "start" in result
    assert "end_iso" in result or "end" in result
    assert "attendees" in result
