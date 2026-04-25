"""Live smoke test: real Whisper container in docker-compose.live.yml.

Skips automatically when:
  - WHISPER_URL is unset (i.e. running default `make test` rather than `make test-live`)
  - tests/live/test_clips/hello_en.wav doesn't exist (user hasn't seeded a clip)

Hits the Whisper container directly at `${WHISPER_URL}/asr` rather than going
through the FastAPI `/api/stt/proxy`, because the test container does not run
an `incarnation_server` process. The proxy itself is already covered by
`tests/integration/test_stt_proxy.py` with respx mocking — this test only
needs to prove the real Whisper container produces a non-empty transcript
and detects the right language.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.live

WHISPER_URL = os.environ.get("WHISPER_URL")
CLIPS_DIR = Path(__file__).parent / "test_clips"


@pytest.mark.skipif(not WHISPER_URL, reason="WHISPER_URL not set — skip live STT test")
def test_whisper_transcribes_english():
    """Real Whisper round-trip on a tiny English clip."""
    clip = CLIPS_DIR / "hello_en.wav"
    if not clip.exists():
        pytest.skip(f"missing test clip: {clip} — record one and re-run")

    with clip.open("rb") as f:
        with httpx.Client(timeout=60.0) as c:
            response = c.post(
                f"{WHISPER_URL}/asr",
                files={"audio_file": ("hello_en.wav", f, "audio/wav")},
                params={"output": "json"},
            )

    assert response.status_code == 200, f"Whisper returned {response.status_code}: {response.text!r}"
    body = response.json()
    text = body.get("text", "").lower()
    # We don't pin the exact transcript (Whisper's "base" model isn't perfect)
    # but a short clip of "hello" should produce *something* and detect English.
    assert text, f"empty transcript: {body!r}"
    assert body.get("language") == "en"
