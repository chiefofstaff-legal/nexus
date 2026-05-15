"""AgentMail email-send shim (stdlib + Bearer auth).

Single responsibility: POST a message to AgentMail's HTTP API. Returns a
bool so callers in the password-reset path can swallow send failures
without exposing whether the email exists in the user store (avoids
user enumeration via timing or error surface).

Key resolution order: env ``AGENTMAIL_API_KEY`` first (canonical name),
``AGENTMAIL_KEY`` fallback, then macOS Keychain ``grip-agentmail`` for
local dev. No third-party deps.

Outbound sender MUST be ``grip-trial-out@agentmail.to`` — only that inbox
has confirmed Gmail-inbox deliverability. ``v.01@agentmail.to`` has
unverified placement and silently fails to reach external Gmail recipients.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request

_API_BASE = "https://api.agentmail.to"
_TIMEOUT_SECONDS = 8.0


def _resolve_key() -> str | None:
    for var in ("AGENTMAIL_API_KEY", "AGENTMAIL_KEY"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    if not shutil.which("security"):
        return None
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "grip-agentmail", "-w"],
            capture_output=True, text=True, timeout=2.0,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def send(inbox_id: str, to: str, subject: str, html_body: str) -> bool:
    """Send an email via the inbox's messages endpoint.

    ``inbox_id`` is the full email address of the sending inbox,
    e.g. ``grip-trial-out@agentmail.to``. The API path is
    ``/inboxes/{inbox_id}/messages`` (no /v1/ prefix).

    Returns True on HTTP 2xx, False on any failure (key missing,
    network error, non-2xx response).
    """
    key = _resolve_key()
    if not key:
        return False
    url = f"{_API_BASE}/inboxes/{inbox_id}/messages"
    payload = json.dumps({
        "to": [{"email": to}],
        "subject": subject,
        "html": html_body,
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False
