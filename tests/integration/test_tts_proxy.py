"""Integration tests for the repointed TTS proxy routes (respx-mocked)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from starlette.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def proxy_client(monkeypatch):
    monkeypatch.setenv("VOICEBOX_URL", "http://rig.test")
    monkeypatch.setenv("VOICEBOX_REGISTRY_URL", "http://reg.test")
    monkeypatch.delenv("TTS_URL", raising=False)
    from incarnation_server import IncarnationServer
    return TestClient(IncarnationServer().app)


@respx.mock
def test_tts_proxy_wraps_pcm_in_wav_with_header_rate(proxy_client):
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(
            200, content=b"\xaa\xbb\xcc\xdd",
            headers={"content-type": "audio/l16; rate=16000; channels=1"}))
    r = proxy_client.get("/api/tts/proxy", params={"text": "hi", "voice": "v1"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    body = r.content
    assert body.startswith(b"RIFF")
    assert int.from_bytes(body[24:28], "little") == 16000   # sample rate in WAV header
    assert body.endswith(b"\xaa\xbb\xcc\xdd")
    sent = json.loads(respx.calls.last.request.content)
    assert sent["response_format"] == "pcm" and sent["voice"] == "v1" and sent["input"] == "hi"


@respx.mock
def test_ref_audio_proxy_hits_registry(proxy_client):
    respx.get("http://reg.test/v1/voices/v1/ref_audio").mock(
        return_value=httpx.Response(200, content=b"RIFFref",
                                    headers={"content-type": "audio/wav"}))
    r = proxy_client.get("/api/speakers/v1/ref_audio")
    assert r.status_code == 200
    assert r.content == b"RIFFref"
