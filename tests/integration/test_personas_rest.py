"""End-to-end /api/v1/personas tests on the real IncarnationServer app with a
real PersonaService over tmp dirs — proves the router is mounted and the whole
request cycle (router → service → stores) works."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.services.persona import PersonaService
from backend.stores.history import HistoryStore
from backend.stores.personas import PersonaStore

pytestmark = pytest.mark.integration


@pytest.fixture
def client(tmp_path):
    from incarnation_server import IncarnationServer
    server = IncarnationServer()
    base = tmp_path / "personas"
    server.app.state.persona_service = PersonaService(
        persona_store=PersonaStore(base_dir=base),
        history_store=HistoryStore(base_dir=base),
        active_persona_id=lambda: "keeper",
    )
    return TestClient(server.app)


def test_full_crud_and_triggers_flow(client):
    # create → 201, full defaulted document (D3)
    r = client.post("/api/v1/personas",
                    json={"name": "New Friend", "description": "hello"})
    assert r.status_code == 201
    doc = r.json()
    assert doc["id"] == "new_friend" and doc["triggers"] == []

    # collision → 409 (D7)
    assert client.post("/api/v1/personas", json={"name": "New Friend"}).status_code == 409

    # list + get
    assert [p["id"] for p in client.get("/api/v1/personas").json()] == ["new_friend"]
    assert client.get("/api/v1/personas/new_friend").json()["name"] == "New Friend"

    # full-document replace
    doc["back_ground"] = "edited"
    r = client.put("/api/v1/personas/new_friend", json=doc)
    assert r.status_code == 200 and r.json()["back_ground"] == "edited"

    # invalid update → 422, file untouched (D3)
    assert client.put("/api/v1/personas/new_friend",
                      json={"name": "broken only"}).status_code == 422
    assert client.get("/api/v1/personas/new_friend").json()["back_ground"] == "edited"

    # triggers: whole-list replace (D2) + bad row → 422
    trig = [{"on": {"phrase": "show camera"},
             "do": {"skill": "show_pip", "params": {}}}]
    assert client.put("/api/v1/personas/new_friend/triggers", json=trig).status_code == 200
    got = client.get("/api/v1/personas/new_friend/triggers").json()
    assert got[0]["on"]["phrase"] == "show camera"
    assert client.put("/api/v1/personas/new_friend/triggers",
                      json=[{"on": {}, "do": {"skill": "x"}}]).status_code == 422

    # delete-active 409 (D7), then delete → 204 → 404
    client.post("/api/v1/personas", json={"name": "Keeper"})
    assert client.delete("/api/v1/personas/keeper").status_code == 409
    assert client.delete("/api/v1/personas/new_friend").status_code == 204
    assert client.get("/api/v1/personas/new_friend").status_code == 404
    assert client.delete("/api/v1/personas/new_friend").status_code == 404
