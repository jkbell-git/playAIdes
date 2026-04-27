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
