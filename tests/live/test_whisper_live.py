"""Live smoke test: real Whisper container in docker-compose.live.yml.

Skips automatically when:
  - WHISPER_URL is unset (i.e. running default `make test` rather than `make test-live`)
  - tests/live/test_clips/hello_en.wav doesn't exist (user hasn't seeded a clip)
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.live

WHISPER_URL = os.environ.get("WHISPER_URL")
CLIPS_DIR = Path(__file__).parent / "test_clips"


@pytest.fixture
def stt_proxy_url():
    """The STT proxy URL on the test container's incarnation_server."""
    return "http://localhost:8765/api/stt/proxy"


@pytest.mark.skipif(not WHISPER_URL, reason="WHISPER_URL not set — skip live STT test")
def test_whisper_transcribes_english(stt_proxy_url):
    """Real Whisper round-trip on a tiny English clip."""
    clip = CLIPS_DIR / "hello_en.wav"
    if not clip.exists():
        pytest.skip(f"missing test clip: {clip} — record one and re-run")

    with clip.open("rb") as f:
        with httpx.Client(timeout=30.0) as c:
            response = c.post(
                stt_proxy_url,
                files={"audio": ("hello_en.wav", f, "audio/wav")},
            )

    assert response.status_code == 200
    body = response.json()
    text = body.get("text", "").lower()
    # We don't pin the exact transcript (Whisper's "base" model isn't perfect)
    # but a short clip of "hello" should produce *something* and detect English.
    assert text, f"empty transcript: {body!r}"
    assert body.get("language") == "en"
