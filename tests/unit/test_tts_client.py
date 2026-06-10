"""Hermetic unit tests for backend.clients.tts.TTSClient (respx-mocked)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.clients.tts import TTSClient, TTSError, _parse_sample_rate


def test_urls_default_and_from_env(monkeypatch):
    monkeypatch.delenv("VOICEBOX_URL", raising=False)
    monkeypatch.delenv("TTS_URL", raising=False)
    monkeypatch.delenv("VOICEBOX_REGISTRY_URL", raising=False)
    monkeypatch.delenv("VOICEBOX_DESIGN_URL", raising=False)
    c = TTSClient()
    assert c.rig_url == "http://localhost:8008"
    assert c.registry_url == "http://localhost:8008"
    assert c.design_url == "http://localhost:8008"  # falls back to rig_url

    monkeypatch.setenv("VOICEBOX_URL", "http://rig:8008")
    monkeypatch.setenv("VOICEBOX_REGISTRY_URL", "http://reg:8008")
    monkeypatch.setenv("VOICEBOX_DESIGN_URL", "http://qwen:8008")
    c2 = TTSClient()
    assert (c2.rig_url, c2.registry_url, c2.design_url) == (
        "http://rig:8008", "http://reg:8008", "http://qwen:8008")


def test_parse_sample_rate():
    assert _parse_sample_rate("audio/l16; rate=22050; channels=1") == 22050
    assert _parse_sample_rate("audio/wav") == 24000           # default
    assert _parse_sample_rate("audio/l16; rate=bogus") == 24000


@respx.mock
def test_synth_returns_wav_bytes_and_sends_contract_body():
    route = respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(200, content=b"RIFFwav", headers={"content-type": "audio/wav"}))
    out = TTSClient(rig_url="http://rig.test").synth("hello", "v1", tags="[calm]")
    assert out == b"RIFFwav"
    body = json.loads(route.calls.last.request.content)
    assert body == {"input": "hello", "voice": "v1",
                    "response_format": "wav", "voicebox": {"tags": "[calm]"}}


@respx.mock
def test_synth_maps_http_error_to_ttserror():
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(404, json={"detail": "voice 'x' not found"}))
    with pytest.raises(TTSError):
        TTSClient(rig_url="http://rig.test").synth("hi", "x")


@respx.mock
async def test_open_speech_stream_yields_rate_and_pcm():
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(
            200, content=b"\x01\x02\x03\x04",
            headers={"content-type": "audio/l16; rate=16000; channels=1"}))
    chunks = bytearray()
    async with TTSClient(rig_url="http://rig.test").open_speech_stream("hi", "v1") as (sr, stream):
        assert sr == 16000
        async for chunk in stream:
            chunks.extend(chunk)
    assert bytes(chunks) == b"\x01\x02\x03\x04"


@respx.mock
async def test_open_speech_stream_error_raises_ttserror():
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(TTSError):
        async with TTSClient(rig_url="http://rig.test").open_speech_stream("hi", "v1"):
            pass
