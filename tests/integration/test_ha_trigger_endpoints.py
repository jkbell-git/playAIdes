"""Integration tests for HA→playAIdes HTTP trigger endpoints.

Uses the project-wide `incarnation_server` and `client` fixtures from
`tests/integration/conftest.py`. Those fixtures monkeypatch
`threading.Thread` to a no-op so no real uvicorn server is spawned —
critical to prevent zombie containers (the fake-thread pattern is also
documented in that conftest.py docstring).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestActivateEndpointAuth:
    def test_missing_authorization_header_returns_401(self, client, with_api_key):
        r = client.post("/api/personas/silver/activate")
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, client, with_api_key):
        r = client.post("/api/personas/silver/activate",
                        headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_correct_token_returns_200_and_dispatches(
        self, incarnation_server, client, with_api_key,
    ):
        r = client.post("/api/personas/silver/activate",
                        headers={"Authorization": f"Bearer {with_api_key}"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # The callback should have been invoked with the synthesized message.
        assert incarnation_server._callback_log == [
            {"type": "set_active_persona", "payload": {"id": "silver"}},
        ]

    def test_no_env_key_set_returns_200_in_dev_mode(self, client, monkeypatch):
        """When PLAYAIDES_API_KEY is unset, auth is skipped (dev convenience)."""
        monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)
        r = client.post("/api/personas/silver/activate")
        assert r.status_code == 200


class TestDismissEndpoint:
    def test_dismiss_requires_auth(self, client, with_api_key):
        r = client.post("/api/dismiss")
        assert r.status_code == 401

    def test_dismiss_clears_bindings_and_broadcasts_unload(
        self, incarnation_server, client, with_api_key,
    ):
        # Seed bindings to verify they get cleared.
        incarnation_server._bindings = {object(): "silver", object(): "rin"}
        # Stub broadcast_to_all so we can observe the emit.
        broadcasts: list[tuple[str, dict]] = []
        incarnation_server.broadcast_to_all = (
            lambda c, p=None: broadcasts.append((c, p or {}))
        )

        r = client.post("/api/dismiss",
                        headers={"Authorization": f"Bearer {with_api_key}"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert incarnation_server._bindings == {}
        assert broadcasts == [("unload_model", {})]


class TestStateEndpoint:
    def test_state_does_not_require_auth(self, client, monkeypatch):
        """GET /api/state is unauthenticated by design (read-only, no PII)."""
        monkeypatch.setenv("PLAYAIDES_API_KEY", "anything")
        r = client.get("/api/state")
        assert r.status_code == 200

    def test_state_returns_active_persona_and_client_count(
        self, incarnation_server, client,
    ):
        # Seed two bound clients and a state-provider that reports "silver".
        incarnation_server._bindings = {object(): "silver", object(): "silver"}
        incarnation_server.state_provider = lambda: {"active_persona_id": "silver"}

        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["active_persona_id"] == "silver"
        assert body["bound_client_count"] == 2

    def test_state_handles_missing_state_provider(self, incarnation_server, client):
        """If no state_provider is set, active_persona_id is None."""
        incarnation_server.state_provider = None
        r = client.get("/api/state")
        assert r.status_code == 200
        assert r.json()["active_persona_id"] is None
