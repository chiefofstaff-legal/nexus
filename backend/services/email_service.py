"""Email integration via MS Graph API.

Wraps the Microsoft Graph mail endpoint behind an injectable HTTP transport
so tests can mock network calls without real credentials.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional


class EmailServiceUnavailable(RuntimeError):
    """Raised when MS Graph credentials are not configured."""


def _build_token_url(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _build_send_url(user_email: str) -> str:
    return f"https://graph.microsoft.com/v1.0/users/{user_email}/sendMail"


class EmailService:
    """Send email via MS Graph on behalf of a licensed mailbox.

    Parameters
    ----------
    tenant_id, client_id, client_secret, user_email:
        MS Graph app-registration credentials. When omitted the service reads
        MS_GRAPH_TENANT_ID / MS_GRAPH_CLIENT_ID / MS_GRAPH_CLIENT_SECRET /
        MS_GRAPH_USER_EMAIL from the environment.
    transport:
        Optional httpx.AsyncBaseTransport — inject a MockTransport in tests.
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
        self._transport = transport  # None → real httpx; injected → mock

        if not all([self._tenant_id, self._client_id, self._client_secret, self._user_email]):
            raise EmailServiceUnavailable(
                "MS Graph credentials not configured. Set MS_GRAPH_TENANT_ID, "
                "MS_GRAPH_CLIENT_ID, MS_GRAPH_CLIENT_SECRET, and MS_GRAPH_USER_EMAIL "
                "in your environment (or pass them to EmailService directly)."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> dict:
        """Send an email and return {message_id, sent_at, status}.

        Parameters
        ----------
        to:      Recipient addresses.
        subject: Email subject line.
        body:    Plain-text body.
        cc:      Optional CC addresses.
        """
        cc = cc or []
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
            },
            "saveToSentItems": True,
        }
        with self._get_client() as client:
            token = self._acquire_token(client)
            resp = client.post(
                _build_send_url(self._user_email),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload).encode(),
            )
            resp.raise_for_status()
            message_id = resp.headers.get("x-ms-request-id", "sent")
            return {
                "message_id": message_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "status": "sent",
            }
