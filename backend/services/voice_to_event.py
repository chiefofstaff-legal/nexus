"""Parse a voice transcript into a calendar event draft using Claude Haiku.

Records token usage via the W3 ingestion cost meter.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ingestion_cost import record_call  # noqa: E402


_PROMPT = """Extract calendar event fields from this voice transcript. Return ONLY valid JSON:
{{
  "title": "event title",
  "start_iso": "YYYY-MM-DDTHH:MM:SS",
  "end_iso": "YYYY-MM-DDTHH:MM:SS",
  "attendees": ["email1@example.com"],
  "location": "location string or empty"
}}

Use ISO-8601 format. If no date is mentioned, use tomorrow 09:00–10:00.

Transcript: {transcript}"""

_MODEL = "claude-haiku-4-5-20251001"


def _heuristic_parse(transcript: str) -> dict:
    """Fallback when no Anthropic client is available."""
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    start = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    end = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    return {
        "title": transcript[:80].strip(),
        "start_iso": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_iso": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "attendees": [],
        "location": "",
    }


async def parse_voice_to_event(transcript: str, anthropic_client) -> dict:
    """Parse *transcript* into a calendar event draft dict.

    Returns {title, start_iso, end_iso, attendees, location}.
    Falls back to heuristics when *anthropic_client* is None.
    """
    if anthropic_client is None:
        return _heuristic_parse(transcript)

    response = await anthropic_client.messages.create(
        model=_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": _PROMPT.format(transcript=transcript)}],
    )

    usage = getattr(response, "usage", None)
    if usage is not None:
        try:
            record_call(
                model=_MODEL,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                purpose="voice_to_event",
            )
        except Exception:  # noqa: BLE001
            pass

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)
