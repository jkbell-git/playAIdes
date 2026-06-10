"""Router unit tests for backend/api/personas.py — every status mapping in the
spec table, against a scriptable fake service injected via app.state."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.testclient import TestClient

from backend.api.personas import router
from backend.services.persona import PersonaActive, PersonaExists, PersonaNotFound
from persona import Persona


def _validation_error() -> ValidationError:
    try:
        Persona()                      # missing required fields
    except ValidationError as e:
        return e
    raise AssertionError("unreachable")


class FakePersonaService:
    """Each method returns its scripted value, or raises its scripted error."""

    def __init__(self):
        self.behavior = {}
        self.calls = []

    def _do(self, method, default, *args):
        self.calls.append((method, args))
        b = self.behavior.get(method)
        if isinstance(b, Exception):
            raise b
        return default if b is None else b

    def list(self): return self._do("list", [{"id": "a"}])
    def get(self, pid): return self._do("get", {"id": pid}, pid)
    def create(self, name, description):
        return self._do("create", {"id": "x", "name": name}, name, description)
    def update(self, pid, data):
        return self._do("update", {"id": pid, **data}, pid, data)
    def delete(self, pid): return self._do("delete", None, pid)
    def get_triggers(self, pid): return self._do("get_triggers", [], pid)
    def replace_triggers(self, pid, triggers):
        return self._do("replace_triggers", triggers, pid, triggers)


@pytest.fixture
def fake_svc():
    return FakePersonaService()


@pytest.fixture
def client(fake_svc):
    app = FastAPI()
    app.include_router(router)
    app.state.persona_service = fake_svc
    return TestClient(app)


def test_list_ok(client):
    r = client.get("/api/v1/personas")
    assert r.status_code == 200 and r.json() == [{"id": "a"}]


def test_create_201_and_409(client, fake_svc):
    r = client.post("/api/v1/personas", json={"name": "X", "description": "d"})
    assert r.status_code == 201
    assert fake_svc.calls[-1] == ("create", ("X", "d"))
    fake_svc.behavior["create"] = PersonaExists("x")
    assert client.post("/api/v1/personas", json={"name": "X"}).status_code == 409


def test_get_ok_404_and_traversal_404(client, fake_svc):
    assert client.get("/api/v1/personas/a").status_code == 200
    fake_svc.behavior["get"] = PersonaNotFound("ghost")
    assert client.get("/api/v1/personas/ghost").status_code == 404
    fake_svc.behavior["get"] = ValueError("Suspicious persona_id")
    r = client.get("/api/v1/personas/dots")
    assert r.status_code == 404
    assert "Suspicious" not in r.json()["detail"]       # guard details not leaked


def test_put_ok_404_and_422(client, fake_svc):
    assert client.put("/api/v1/personas/a", json={"name": "X"}).status_code == 200
    fake_svc.behavior["update"] = PersonaNotFound("ghost")
    assert client.put("/api/v1/personas/ghost", json={"name": "X"}).status_code == 404
    # The except-order pin: ValidationError must map to 422, not the ValueError 404.
    fake_svc.behavior["update"] = _validation_error()
    assert client.put("/api/v1/personas/a", json={"name": "X"}).status_code == 422


def test_delete_204_404_409(client, fake_svc):
    r = client.delete("/api/v1/personas/a")
    assert r.status_code == 204 and r.content == b""
    fake_svc.behavior["delete"] = PersonaNotFound("ghost")
    assert client.delete("/api/v1/personas/ghost").status_code == 404
    fake_svc.behavior["delete"] = PersonaActive("a")
    assert client.delete("/api/v1/personas/a").status_code == 409


def test_triggers_get_and_put(client, fake_svc):
    assert client.get("/api/v1/personas/a/triggers").status_code == 200
    fake_svc.behavior["get_triggers"] = PersonaNotFound("ghost")
    assert client.get("/api/v1/personas/ghost/triggers").status_code == 404

    trig = [{"on": {"phrase": "p"}, "do": {"skill": "s", "params": {}}}]
    r = client.put("/api/v1/personas/a/triggers", json=trig)
    assert r.status_code == 200 and r.json() == trig
    assert fake_svc.calls[-1] == ("replace_triggers", ("a", trig))  # bare array body
    fake_svc.behavior["replace_triggers"] = _validation_error()
    assert client.put("/api/v1/personas/a/triggers", json=trig).status_code == 422


def test_503_when_service_absent():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/v1/personas").status_code == 503


def test_401_when_key_set_and_no_header(fake_svc, with_api_key):
    app = FastAPI()
    app.include_router(router)
    app.state.persona_service = fake_svc
    client = TestClient(app)
    assert client.get("/api/v1/personas").status_code == 401
    ok = client.get("/api/v1/personas",
                    headers={"Authorization": f"Bearer {with_api_key}"})
    assert ok.status_code == 200
