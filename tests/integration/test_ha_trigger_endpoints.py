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
