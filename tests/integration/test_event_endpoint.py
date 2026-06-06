# tests/integration/test_event_endpoint.py
"""Integration test (FastAPI TestClient, no external services): POST /api/event
routes to the orchestrator's event_handler; bearer auth gates it when set."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):  # pragma: no cover
        pass


def _build_server(monkeypatch, tmp_path, handler):
    """Build an IncarnationServer with no real uvicorn thread (repo convention)."""
    import incarnation_server as mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "threading", type("m", (), {"Thread": _NoopThread}))
    return mod.IncarnationServer(host="127.0.0.1", port=18767, event_handler=handler)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)   # dev mode: no auth
    calls: list = []

    def handler(name, payload):
        calls.append((name, payload))
        return {"matched": True, "skill": "show_pip"} if name == "motion" else {"matched": False}

    srv = _build_server(monkeypatch, tmp_path, handler)
    c = TestClient(srv.app)
    c.calls = calls
    return c


def test_event_routes_to_handler(client):
    r = client.post("/api/event", json={"name": "motion", "payload": {"state": "on"}})
    assert r.status_code == 200
    assert r.json() == {"matched": True, "skill": "show_pip"}
    assert client.calls == [("motion", {"state": "on"})]


def test_event_unmatched_returns_matched_false(client):
    r = client.post("/api/event", json={"name": "nope", "payload": {}})
    assert r.status_code == 200
    assert r.json() == {"matched": False}


def test_event_missing_name_is_422(client):
    r = client.post("/api/event", json={"payload": {}})
    assert r.status_code == 422       # pydantic body validation (FastAPI default)


def test_event_requires_bearer_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "secret")
    srv = _build_server(monkeypatch, tmp_path, lambda n, p: {"matched": False})
    c = TestClient(srv.app)
    assert c.post("/api/event", json={"name": "x", "payload": {}}).status_code == 401
    ok = c.post("/api/event", json={"name": "x", "payload": {}},
                headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
