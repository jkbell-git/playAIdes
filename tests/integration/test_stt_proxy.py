"""Integration tests for POST /api/stt/proxy.

Verifies the proxy forwards audio uploads to the Whisper container
(mocked via respx) and returns the transcribed text + detected language.
"""
from __future__ import annotations

import io

import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.integration


@respx.mock
def test_stt_proxy_happy_path(client):
    """Forwards audio to Whisper, returns text + language."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(
            200,
            json={"text": "hello there", "language": "en"},
        )
    )

    fake_audio = io.BytesIO(b"RIFF....fake-wav-bytes")
    response = client.post(
        "/api/stt/proxy",
        files={"audio": ("clip.wav", fake_audio, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"text": "hello there", "language": "en"}


@respx.mock
def test_stt_proxy_upstream_error_returns_502(client):
    """Whisper down / 5xx → proxy responds 502 with a clear detail string."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(503, text="model loading"),
    )

    fake_audio = io.BytesIO(b"junk")
    response = client.post(
        "/api/stt/proxy",
        files={"audio": ("clip.wav", fake_audio, "audio/wav")},
    )

    assert response.status_code == 502
    assert "STT" in response.json()["detail"]


def test_stt_proxy_missing_audio_field_returns_422(client):
    """Missing `audio` form field → FastAPI returns 422 (validation error)."""
    response = client.post("/api/stt/proxy", files={})
    assert response.status_code == 422
