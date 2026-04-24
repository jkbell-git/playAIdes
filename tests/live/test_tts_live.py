"""Live E2E smoke test against the real Qwen3 TTS container."""
from __future__ import annotations

from pathlib import Path

import pytest

from voice_generation.voice_api import Qwen3TTS_local
from voice_generation.voice_server.service.voice_server_api import (
    SpeechGenerationRequest,
    VoiceDesignRequest,
)

pytestmark = [pytest.mark.live, pytest.mark.slow]


def test_design_and_generate(tts_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Point the class at the live container URL via env var (already set by
    # docker-compose.live.yml, but enforce here for robustness).
    monkeypatch.setenv("TTS_URL", tts_url)
    tts = Qwen3TTS_local()
    tts.BASE_URL = tts_url  # instance override, module-level default may be cached

    speaker_id = tts.generate_voice(VoiceDesignRequest(
        text="Hello world.",
        language="English",
        instruct="A calm, neutral voice.",
        name="test-voice",
        gender="Female",
    ))
    assert speaker_id, "TTS server did not return a speaker_id"

    out_file = tts.generate_speech_file(
        SpeechGenerationRequest(text="Hello from a test.", speaker_id=speaker_id),
        output_path=str(tmp_path),
    )
    assert out_file, "generate_speech_file returned no path"
    p = Path(out_file)
    assert p.exists() and p.stat().st_size > 0
