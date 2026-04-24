"""Integration-test fixtures that build an IncarnationServer suitable for TestClient.

Trick: ``IncarnationServer.__init__`` normally spawns a daemon thread that
runs uvicorn on a real port. For tests we don't want that — FastAPI's
``TestClient`` speaks ASGI directly. We monkeypatch ``threading.Thread`` in
the module for the duration of the test so the app is built but the thread
is a no-op.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):  # pragma: no cover - trivial
        pass


@pytest.fixture
def incarnation_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build an IncarnationServer against a tmp working dir with no real thread."""
    import incarnation_server as mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "threading", type("m", (), {"Thread": _NoopThread}))
    callback_log: list[dict] = []
    server = mod.IncarnationServer(
        host="127.0.0.1", port=18765,
        on_message_callback=callback_log.append,
    )
    server._callback_log = callback_log  # attach for tests
    return server


@pytest.fixture
def client(incarnation_server) -> TestClient:
    return TestClient(incarnation_server.app)
