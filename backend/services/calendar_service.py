"""Calendar integration via MS Graph API.

Mirrors email_service.py structure: injectable transport for test mocking.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional


class CalendarServiceUnavailable(RuntimeError):
    """Raised when MS Graph credentials are not configured."""


def _build_token_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _build_events_url(user_email: str) -> str:
    return f"https://graph.microsoft.com/v1.0/users/{user_email}/calendar/events"


class CalendarService:
    """Create calendar events via MS Graph on behalf of a licensed mailbox.

    Parameters
    ----------
    tenant_id, client_id, client_secret, user_email:
        MS Graph credentials. Falls back to MS_GRAPH_* env vars when omitted.
    transport:
        Optional httpx transport — inject MockTransport in tests.
    """

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_email: Optional[str] = None,
        transport=None,
    ) -> None:
        self._tenant_id = tenant_id or os.getenv("MS_GRAPH_TENANT_ID", "")
        self._client_id = client_id or os.getenv("MS_GRAPH_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("MS_GRAPH_CLIENT_SECRET", "")
        self._user_email = user_email or os.getenv("MS_GRAPH_USER_EMAIL", "")
        self._transport = transport

        if not all([self._tenant_id, self._client_id, self._client_secret, self._user_email]):
            raise CalendarServiceUnavailable(
                "MS Graph credentials not configured. Set MS_GRAPH_TENANT_ID, "
                "MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, and MS_GRAPH_USER_EMAIL "
                "in your environment (or pass them to CalendarService directly)."
            )

    def _get_client(self):
        import httpx
        kwargs = {"timeout": 15.0}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _acquire_token(self, client) -> str:
        resp = client.post(
            _build_token_url(self._tenant_id),
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        attendees: list[str],
        location: str = "",
        body: str = "",
    ) -> dict:
        """Create a calendar event and return {event_id, meeting_url, created_at}.

        Parameters
        ----------
        title:     Event subject.
        start:     ISO-8601 datetime string (e.g. "2026-05-01T09:00:00").
        end:       ISO-8601 datetime string.
        attendees: List of attendee email addresses.
        location:  Optional location string.
        body:      Optional event description.
        """
        payload = {
            "subject": title,
            "start": {"dateTime": start, "timeZone": "Europe/Zurich"},
            "end": {"dateTime": end, "timeZone": "Europe/Zurich"},
            "location": {"displayName": location},
            "body": {"contentType": "Text", "content": body},
            "attendees": [
                {"emailAddress": {"address": a}, "type": "required"}
                for a in attendees
            ],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }
        with self._get_client() as client:
            token = self._acquire_token(client)
            resp = client.post(
                _build_events_url(self._user_email),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload).encode(),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "event_id": data.get("id", ""),
                "meeting_url": (data.get("onlineMeeting") or {}).get("joinUrl", ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
