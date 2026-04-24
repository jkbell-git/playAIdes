"""Unit tests for voice_generation.voice_api.Qwen3TTS_local — HTTP mocked."""
from __future__ import annotations

from pathlib import Path

import pytest
import responses

from voice_generation.voice_api import Qwen3TTS_local
from voice_generation.voice_server.service.voice_server_api import (
    SpeechGenerationRequest,
    VoiceDesignRequest,
)


@pytest.fixture
def tts(monkeypatch: pytest.MonkeyPatch) -> Qwen3TTS_local:
    t = Qwen3TTS_local()
    t.BASE_URL = "http://fake-tts:8009"
    return t


class TestGenerateVoice:
    @responses.activate
    def test_success_returns_speaker_id(self, tts):
        responses.post(
            "http://fake-tts:8009/design",
            json={"speaker_id": "spk-42"},
            status=200,
        )
        out = tts.generate_voice(VoiceDesignRequest(
            text="hi", language="English", instruct="calm", name="n", gender="Female"
        ))
        assert out == "spk-42"

    @responses.activate
    def test_failure_returns_none(self, tts):
        responses.post("http://fake-tts:8009/design", json={"err": "bad"}, status=500)
        out = tts.generate_voice(VoiceDesignRequest(
            text="hi", language="English", instruct="calm", name="n", gender="Female"
        ))
        assert out is None


class TestGenerateSpeechFile:
    @responses.activate
    def test_writes_file_on_success(self, tts, tmp_path: Path):
        responses.post(
            "http://fake-tts:8009/generate_file",
            body=b"WAV_BYTES",
            status=200,
            content_type="audio/wav",
        )
        out = tts.generate_speech_file(
            SpeechGenerationRequest(text="hello", speaker_id="spk-1"),
            output_path=str(tmp_path),
        )
        p = Path(out)
        assert p.exists()
        assert p.read_bytes() == b"WAV_BYTES"
        assert p.suffix == ".wav"

    @responses.activate
    def test_upstream_error_does_not_create_file(self, tts, tmp_path: Path):
        responses.post("http://fake-tts:8009/generate_file", status=503)
        out = tts.generate_speech_file(
            SpeechGenerationRequest(text="hello", speaker_id="spk-1"),
            output_path=str(tmp_path),
        )
        # Current implementation returns the path it would have written to,
        # but never actually writes. Verify no file landed on disk.
        assert not Path(out).exists()
