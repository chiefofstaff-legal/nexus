"""Task notification dispatch — soft-fail, never raises.

Reads channel config from ``config/notification-channels.yaml``.
Default "log" channel appends a JSONL record to ``data/notifications.jsonl``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml  # PyYAML is in requirements
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "notification-channels.yaml"
_NOTIFICATIONS_PATH = Path(__file__).parent.parent / "data" / "notifications.jsonl"


def _load_channels(config_path: Optional[Path] = None) -> list[dict]:
    """Return the channels list from config. Falls back to log-only on any error."""
    path = config_path or _CONFIG_PATH
    if yaml is None or not path.exists():
        return [{"type": "log"}]
    try:
        raw = yaml.safe_load(path.read_text())
        channels = (raw or {}).get("channels", [])
        return channels if isinstance(channels, list) else [{"type": "log"}]
    except Exception:
        return [{"type": "log"}]


def _write_log(task, notifications_path: Optional[Path] = None) -> None:
    """Append one JSONL record to data/notifications.jsonl."""
    path = notifications_path or _NOTIFICATIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "task_id": task.id,
        "assignee": task.assignee,
        "matter": task.matter,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "notified_at": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def notify_assignee(
    task,
    config_path: Optional[Path] = None,
    notifications_path: Optional[Path] = None,
) -> None:
    """Dispatch task notification through configured channels. Never raises."""
    try:
        channels = _load_channels(config_path)
        for channel in channels:
            channel_type = (channel or {}).get("type", "")
            if channel_type == "log":
                _write_log(task, notifications_path)
            elif channel_type == "slack":
                _notify_slack(channel, task)
            else:
                logger.warning("Unknown notification channel type: %r", channel_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("notify_assignee failed (soft-fail): %s", exc)


def _notify_slack(channel: dict, task) -> None:
    """POST to a Slack incoming webhook. Soft-fail on any error."""
    import os
    import urllib.request

    webhook_url = channel.get("webhook_url", "")
    if not webhook_url:
        return
    webhook_url = os.path.expandvars(webhook_url)
    deadline_str = task.deadline.isoformat() if task.deadline else "no deadline"
    text = (
        f"Task assigned to *{task.assignee}*: {task.title} "
        f"(matter: {task.matter or 'none'}, deadline: {deadline_str})"
    )
    payload = json.dumps({"text": text}).encode()
    try:
        req = urllib.request.Request(
            webhook_url, data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)  # noqa: S310
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack notification failed: %s", exc)
