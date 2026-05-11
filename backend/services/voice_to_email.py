"""Parse a voice transcript into an email draft using Claude Haiku.

Records token usage via the W3 ingestion cost meter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ingestion_cost import record_call  # noqa: E402


_PROMPT = """Extract email fields from this voice transcript. Return ONLY valid JSON:
{{
  "recipient_hint": "name or address mentioned, or empty string",
  "subject": "concise subject line",
  "body": "full email body text"
}}

Transcript: {transcript}"""

_MODEL = "claude-haiku-4-5-20251001"


def _heuristic_parse(transcript: str) -> dict:
    """Fallback when no Anthropic client is available."""
    return {
        "recipient_hint": "",
        "subject": transcript[:60].strip(),
        "body": transcript,
    }


async def parse_voice_to_email(transcript: str, anthropic_client) -> dict:
    """Parse *transcript* into an email draft dict.

    Returns {recipient_hint, subject, body}.
    Falls back to heuristics when *anthropic_client* is None.
    """
    if anthropic_client is None:
        return _heuristic_parse(transcript)

    response = await anthropic_client.messages.create(
        model=_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": _PROMPT.format(transcript=transcript)}],
    )

    usage = getattr(response, "usage", None)
    if usage is not None:
        try:
            record_call(
                model=_MODEL,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                purpose="voice_to_email",
            )
        except Exception:  # noqa: BLE001
            pass

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)
