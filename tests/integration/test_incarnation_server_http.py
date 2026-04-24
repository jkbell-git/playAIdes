"""Integration tests for IncarnationServer HTTP endpoints via TestClient."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

pytestmark = pytest.mark.integration


class _FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in: programmable get() response / error."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, timeout=None, **kwargs):
        if self._error is not None:
            raise self._error
        return self._response


class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestDefaultAnimations:
    def test_empty_when_no_files(self, client):
        # Fixture chdirs into a fresh tmp dir; no .vrma files present.
        r = client.get("/api/default_animations")
        assert r.status_code == 200
        assert r.json() == {"animations": []}

    def test_lists_vrma_files(self, tmp_path: Path, client):
        # The server __init__ already created the dir; drop a file into it.
        anim_dir = Path("incarnation/public/vrma/animations")
        anim_dir.mkdir(parents=True, exist_ok=True)
        (anim_dir / "wave.vrma").write_bytes(b"fake")
        (anim_dir / "readme.txt").write_text("not an animation")
        r = client.get("/api/default_animations")
        data = r.json()
        names = [a["name"] for a in data["animations"]]
        assert names == ["wave"]
        assert data["animations"][0]["url"].endswith("/default_animations/wave.vrma")


class TestModelUpload:
    def test_uploads_file_and_fires_callback(self, incarnation_server, client):
        file_bytes = b"VRM\x00fake-model-bytes"
        r = client.post(
            "/api/personas/testbot/model",
            files={"file": ("model.vrm", io.BytesIO(file_bytes), "application/octet-stream")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["filename"] == "model.vrm"
        assert "/personas/testbot/avatar/model.vrm" in body["url"]

        # File actually landed on disk
        saved = Path("personas/testbot/avatar/model.vrm")
        assert saved.exists()
        assert saved.read_bytes() == file_bytes

        # Callback fired with the right shape
        assert len(incarnation_server._callback_log) == 1
        cb = incarnation_server._callback_log[0]
        assert cb["type"] == "model_uploaded"
        assert cb["payload"]["persona_id"] == "testbot"


class TestAnimationUpload:
    def test_uploads_animation_and_fires_callback(self, incarnation_server, client):
        r = client.post(
            "/api/personas/testbot/animations",
            files={"file": ("dance.vrma", io.BytesIO(b"anim"), "application/octet-stream")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "dance"
        assert body["filename"] == "dance.vrma"
        assert Path("personas/testbot/avatar/animations/dance.vrma").exists()
        assert incarnation_server._callback_log[0]["type"] == "animation_uploaded"
        assert incarnation_server._callback_log[0]["payload"]["name"] == "dance"


class TestRefAudioProxy:
    def test_proxies_ref_audio(self, client, monkeypatch):
        fake_resp = MagicMock(spec=httpx.Response)
        fake_resp.status_code = 200
        fake_resp.content = b"WAVE_BYTES"
        monkeypatch.setattr(
            "incarnation_server.httpx.AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response=fake_resp),
        )
        r = client.get("/api/speakers/abc/ref_audio")
        assert r.status_code == 200
        assert r.content == b"WAVE_BYTES"
        assert r.headers["content-type"] == "audio/wav"

    def test_proxies_upstream_error(self, client, monkeypatch):
        fake_resp = MagicMock(spec=httpx.Response)
        fake_resp.status_code = 404
        fake_resp.text = "no such speaker"
        monkeypatch.setattr(
            "incarnation_server.httpx.AsyncClient",
            lambda *a, **k: _FakeAsyncClient(response=fake_resp),
        )
        r = client.get("/api/speakers/nope/ref_audio")
        assert r.status_code == 404

    def test_upstream_connection_error_502(self, client, monkeypatch):
        monkeypatch.setattr(
            "incarnation_server.httpx.AsyncClient",
            lambda *a, **k: _FakeAsyncClient(error=httpx.ConnectError("nope")),
        )
        r = client.get("/api/speakers/boom/ref_audio")
        assert r.status_code == 502
