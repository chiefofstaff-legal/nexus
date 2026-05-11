"""W6 — Email service tests.

Verifies the EmailService MS Graph wrapper using injected httpx.MockTransport.
No real network calls.
"""

from __future__ import annotations

import json

import httpx
import pytest

from services.email_service import (
    EmailService,
    EmailServiceUnavailable,
)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    """Return the right shape for both token + sendMail endpoints."""
    if request.url.path.endswith("/oauth2/v2.0/token"):
        return httpx.Response(
            200,
            json={"access_token": "fake_token", "expires_in": 3600},
        )
    if request.url.path.endswith("/sendMail"):
        return httpx.Response(
            202,
            headers={"x-ms-request-id": "req_abc123"},
            content=b"",
        )
    return httpx.Response(404, content=b"")


def _service_with_creds(transport=None) -> EmailService:
    return EmailService(
        tenant_id="tnt", client_id="cid",
        client_secret="sec", user_email="lawyer@example.com",
        transport=transport,
    )


def test_send_email_returns_message_id():
    transport = httpx.MockTransport(_ok_handler)
    svc = _service_with_creds(transport)
    result = svc.send_email(
        to=["alice@example.com"],
        subject="Test",
        body="Hello",
    )
    assert result["message_id"] == "req_abc123"
    assert result["status"] == "sent"
    assert "sent_at" in result


def test_send_email_includes_cc_in_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path.endswith("/sendMail"):
            captured["payload"] = json.loads(request.content.decode())
            return httpx.Response(202, headers={"x-ms-request-id": "ok"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    svc = _service_with_creds(transport)
    svc.send_email(
        to=["a@example.com"],
        subject="S",
        body="B",
        cc=["c@example.com"],
    )
    cc_addrs = [
        r["emailAddress"]["address"]
        for r in captured["payload"]["message"]["ccRecipients"]
    ]
    assert cc_addrs == ["c@example.com"]


def test_missing_credentials_raises_unavailable(monkeypatch):
    """Goodhart anchor — empty env vars must NOT silently succeed."""
    for var in (
        "MS_GRAPH_TENANT_ID", "MS_GRAPH_CLIENT_ID",
        "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_USER_EMAIL",
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(EmailServiceUnavailable, match="MS Graph credentials"):
        EmailService()


def test_send_email_propagates_4xx_as_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(403, json={"error": "Forbidden"})

    transport = httpx.MockTransport(handler)
    svc = _service_with_creds(transport)
    with pytest.raises(httpx.HTTPStatusError):
        svc.send_email(to=["a@example.com"], subject="S", body="B")


@pytest.mark.asyncio
async def test_voice_to_email_heuristic_fallback_when_no_client():
    from services.voice_to_email import parse_voice_to_email
    result = await parse_voice_to_email(
        "Send Andre a note about the Helvetica matter",
        anthropic_client=None,
    )
    assert "Send Andre a note" in result["body"]
    assert result["recipient_hint"] == ""
    assert len(result["subject"]) <= 60
