"""Integration tests for POST /api/voice.

The voice endpoint is the no-Home-Assistant mic path: a non-browser client
(ESP32 / the phone debug page) uploads an audio clip; the server runs Whisper
STT (mocked here via respx) and routes the transcript through the SAME
``user_input`` message path the browser uses, so the bound viewer speaks the
reply. These tests verify: STT round-trip, routing into on_message_callback,
the empty-transcript / persona_id branches, and upstream/validation errors.
"""
from __future__ import annotations

import io

import pytest
import respx
from httpx import Response

pytestmark = pytest.mark.integration


@respx.mock
def test_voice_happy_path_transcribes_and_routes(client, incarnation_server):
    """Audio → Whisper → returns transcript AND routes a user_input message."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(200, json={"text": "hello there silver", "language": "en"}),
    )

    response = client.post(
        "/api/voice",
        files={"audio": ("clip.wav", io.BytesIO(b"RIFF....fake-wav"), "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "text": "hello there silver", "language": "en", "routed": True,
    }

    log = incarnation_server._callback_log
    assert len(log) == 1
    assert log[0]["type"] == "user_input"
    assert log[0]["payload"] == {"text": "hello there silver"}


@respx.mock
def test_voice_empty_transcript_is_not_routed(client, incarnation_server):
    """Whisper heard nothing → routed:false and no conversation turn fired."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(200, json={"text": "   ", "language": ""}),
    )

    response = client.post(
        "/api/voice",
        files={"audio": ("clip.wav", io.BytesIO(b"silence"), "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == ""
    assert body["routed"] is False
    assert incarnation_server._callback_log == []


@respx.mock
def test_voice_persona_id_query_param_is_forwarded(client, incarnation_server):
    """An optional ?persona_id= targets a specific persona in the routed payload."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(200, json={"text": "switch to you", "language": "en"}),
    )

    response = client.post(
        "/api/voice?persona_id=silver",
        files={"audio": ("clip.wav", io.BytesIO(b"x"), "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json()["routed"] is True
    log = incarnation_server._callback_log
    assert len(log) == 1
    assert log[0]["payload"] == {"text": "switch to you", "persona_id": "silver"}


@respx.mock
def test_voice_upstream_error_returns_502(client, incarnation_server):
    """Whisper down / 5xx → 502 with a clear detail, and nothing routed."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(503, text="model loading"),
    )

    response = client.post(
        "/api/voice",
        files={"audio": ("clip.wav", io.BytesIO(b"junk"), "audio/wav")},
    )

    assert response.status_code == 502
    assert "STT" in response.json()["detail"]
    assert incarnation_server._callback_log == []


def test_voice_missing_audio_field_returns_422(client):
    """Missing `audio` form field → FastAPI validation error (422)."""
    response = client.post("/api/voice", files={})
    assert response.status_code == 422
