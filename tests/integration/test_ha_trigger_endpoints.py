"""Integration tests for HA→playAIdes HTTP trigger endpoints."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from incarnation_server import IncarnationServer

pytestmark = pytest.mark.integration


@pytest.fixture
def server_with_callback():
    """Boot an IncarnationServer with a recording callback (no PlayAIdes needed)."""
    received: list[dict] = []

    def cb(msg):
        received.append(msg)

    srv = IncarnationServer(host="testhost", port=0, on_message_callback=cb)
    srv.received = received  # for test access
    return srv


class TestActivateEndpointAuth:
    def test_missing_authorization_header_returns_401(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate")
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate",
                        headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_correct_token_returns_200_and_dispatches(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate",
                        headers={"Authorization": f"Bearer {with_api_key}"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # The callback should have been invoked with the synthesized message.
        assert server_with_callback.received == [
            {"type": "set_active_persona", "payload": {"id": "silver"}},
        ]

    def test_no_env_key_set_returns_200_in_dev_mode(self, server_with_callback, monkeypatch):
        """When PLAYAIDES_API_KEY is unset, auth is skipped (dev convenience)."""
        monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate")
        assert r.status_code == 200


class TestDismissEndpoint:
    def test_dismiss_requires_auth(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/dismiss")
        assert r.status_code == 401

    def test_dismiss_clears_bindings_and_broadcasts_unload(self, server_with_callback, with_api_key):
        # Seed bindings to verify they get cleared.
        server_with_callback._bindings = {object(): "silver", object(): "rin"}
        # Stub broadcast_to_all so we can observe the emit.
        broadcasts: list[tuple[str, dict]] = []
        server_with_callback.broadcast_to_all = lambda c, p=None: broadcasts.append((c, p or {}))

        client = TestClient(server_with_callback.app)
        r = client.post("/api/dismiss",
                        headers={"Authorization": f"Bearer {with_api_key}"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert server_with_callback._bindings == {}
        assert broadcasts == [("unload_model", {})]


class TestStateEndpoint:
    def test_state_does_not_require_auth(self, server_with_callback, monkeypatch):
        """GET /api/state is unauthenticated by design (read-only, no PII)."""
        monkeypatch.setenv("PLAYAIDES_API_KEY", "anything")
        client = TestClient(server_with_callback.app)
        r = client.get("/api/state")
        assert r.status_code == 200

    def test_state_returns_active_persona_and_client_count(self, server_with_callback):
        # Seed two bound clients and a state-provider that reports "silver".
        server_with_callback._bindings = {object(): "silver", object(): "silver"}
        server_with_callback.state_provider = lambda: {"active_persona_id": "silver"}

        client = TestClient(server_with_callback.app)
        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["active_persona_id"] == "silver"
        assert body["bound_client_count"] == 2

    def test_state_handles_missing_state_provider(self, server_with_callback):
        """If no state_provider is set, active_persona_id is None."""
        server_with_callback.state_provider = None
        client = TestClient(server_with_callback.app)
        r = client.get("/api/state")
        assert r.status_code == 200
        assert r.json()["active_persona_id"] is None
