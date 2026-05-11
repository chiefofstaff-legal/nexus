"""
Voice transcription endpoint tests.

Covers:
1. Happy path — mocked Groq returns transcript string.
2. Empty upload — 400 response.
3. Route registered — /api/voice/transcribe present in OpenAPI schema.
"""

import io
import math
import os
import struct
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

_client = TestClient(app)


def _wav_bytes() -> bytes:
    """1-second 440 Hz sine-wave WAV (16-bit mono 16 kHz)."""
    sample_rate = 16_000
    samples = [
        int(32767 * math.sin(2 * math.pi * 440 * t / sample_rate))
        for t in range(sample_rate)
    ]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def test_route_registered():
    """Smoke-test: endpoint appears in the OpenAPI schema."""
    resp = _client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/voice/transcribe" in resp.json()["paths"]


@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="requires GROQ_API_KEY")
def test_transcribe_returns_transcript_key():
    """Mocked Groq — endpoint returns {transcript: str}."""
    with patch("groq.Groq") as MockGroq:
        mock_instance = MagicMock()
        MockGroq.return_value = mock_instance
        mock_instance.audio.transcriptions.create.return_value = (
            "Spent 45 minutes reviewing the Müller NDA"
        )

        resp = _client.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "transcript" in data
    assert data["transcript"] == "Spent 45 minutes reviewing the Müller NDA"


def test_transcribe_empty_audio_returns_400():
    """Empty body should be rejected before reaching Groq."""
    resp = _client.post(
        "/api/voice/transcribe",
        files={"audio": ("empty.webm", b"", "audio/webm")},
    )
    assert resp.status_code == 400


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
def test_transcribe_lang_param_forwarded_to_groq():
    """?lang=de must reach Groq as language='de' — not overridden to 'en'."""
    with patch("groq.Groq") as MockGroq:
        mock_instance = MagicMock()
        MockGroq.return_value = mock_instance
        mock_instance.audio.transcriptions.create.return_value = "Guten Tag"

        resp = _client.post(
            "/api/voice/transcribe?lang=de",
            files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        )

    assert resp.status_code == 200
    call_kwargs = mock_instance.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs.get("language") == "de"


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
def test_transcribe_no_lang_uses_autodetect():
    """No ?lang param must pass language=None to Groq (Whisper autodetect)."""
    with patch("groq.Groq") as MockGroq:
        mock_instance = MagicMock()
        MockGroq.return_value = mock_instance
        mock_instance.audio.transcriptions.create.return_value = "Bonjour"

        resp = _client.post(
            "/api/voice/transcribe",
            files={"audio": ("test.wav", _wav_bytes(), "audio/wav")},
        )

    assert resp.status_code == 200
    call_kwargs = mock_instance.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs.get("language") is None
