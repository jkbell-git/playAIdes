"""Live TTS smoke test against a real voicebox /v1 rig + registry.

Auto-skips unless VOICEBOX_URL is set and reachable. Exercises whole-file synth
against a live engine (e.g. the CPU kokoro rig). Voice *design* (qwen3, GPU) is
covered by the deferred manual live test, not here.
"""
import os

import httpx
import pytest

from backend.clients.tts import TTSClient

pytestmark = pytest.mark.live


@pytest.fixture
def live_rig_url():
    url = os.environ.get("VOICEBOX_URL")
    if not url:
        pytest.skip("VOICEBOX_URL not set; skipping live TTS test")
    try:
        httpx.get(f"{url.rstrip('/')}/health", timeout=3).raise_for_status()
    except Exception as e:
        pytest.skip(f"voicebox rig not reachable at {url!r}: {e}")
    return url


def test_live_synth_returns_wav(live_rig_url):
    voice = os.environ.get("VOICEBOX_TEST_VOICE")
    if not voice:
        pytest.skip("VOICEBOX_TEST_VOICE not set (a voice UUID registered in the live registry)")
    out = TTSClient().synth("Hello from a live test.", voice)
    assert out[:4] == b"RIFF" and len(out) > 44   # a real WAV with body


def test_live_ref_audio_returns_wav(live_rig_url):
    import asyncio

    voice = os.environ.get("VOICEBOX_TEST_VOICE")
    if not voice:
        pytest.skip("VOICEBOX_TEST_VOICE not set (a voice UUID registered in the live registry)")
    registry = os.environ.get("VOICEBOX_REGISTRY_URL")
    if not registry:
        pytest.skip("VOICEBOX_REGISTRY_URL not set; skipping live ref_audio test")
    out = asyncio.run(TTSClient().ref_audio(voice))
    assert out[:4] == b"RIFF" and len(out) > 44
