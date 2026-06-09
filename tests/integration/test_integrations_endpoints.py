# tests/integration/test_integrations_endpoints.py
"""Integration tests for the /api/v1/integrations* routes.

Uses the project `incarnation_server` / `client` fixtures (which chdir to a tmp
dir) so config/secrets writes land under tmp_path, never the repo. The provider
seam is stubbed via registry.build_provider so no HTTP is needed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.clients.providers import registry
from backend.clients.providers.base import Item, CAP_PIP
from backend.clients.providers.fake import FakeProvider

pytestmark = pytest.mark.integration

AUTH = {"Authorization": "Bearer test-api-key-secret-1234"}
BASE = "/api/v1/integrations"


def test_set_config_persists_to_store(client, with_api_key, tmp_path):
    r = client.post(f"{BASE}/homeassistant/config",
                    json={"config": {"base_url": "http://ha.local:8123"}}, headers=AUTH)
    assert r.status_code == 200
    saved = json.loads((tmp_path / "config" / "integrations.json").read_text())
    assert saved["providers"]["homeassistant"]["config"]["base_url"] == "http://ha.local:8123"


def test_secret_endpoint_is_write_only(client, with_api_key, tmp_path):
    r = client.post(f"{BASE}/homeassistant/secret",
                    json={"key": "token", "value": "super-secret"}, headers=AUTH)
    assert r.status_code == 200
    assert "super-secret" not in r.text          # never echoed
    saved = json.loads((tmp_path / "config" / "secrets.json").read_text())
    assert saved["homeassistant"]["token"] == "super-secret"   # persisted server-side


def test_secret_requires_auth(client, with_api_key):
    r = client.post(f"{BASE}/homeassistant/secret", json={"key": "token", "value": "x"})
    assert r.status_code == 401


def test_put_and_get_mappings_roundtrip(client, with_api_key):
    mappings = {"launch_targets": [
        {"provider": "homeassistant", "entity": "media_player.tv", "label": "den"}]}
    r = client.put(f"{BASE}/homeassistant/mappings",
                   json={"mappings": mappings}, headers=AUTH)
    assert r.status_code == 200
    r2 = client.get(f"{BASE}/homeassistant/mappings", headers=AUTH)
    assert r2.json()["mappings"] == mappings


def test_scan_uses_provider_and_groups_by_domain(client, with_api_key, monkeypatch):
    fake = FakeProvider(items=[
        Item(id="camera.front", domain="camera", name="Front", capabilities=[CAP_PIP]),
        Item(id="script.greet", domain="script", name="Greet", capabilities=["scripts"]),
    ])
    monkeypatch.setattr(registry, "build_provider", lambda pid, **kw: fake)
    r = client.post(f"{BASE}/homeassistant/scan", headers=AUTH)
    assert r.status_code == 200
    grouped = r.json()["groups"]
    assert set(grouped) == {"camera", "script"}
    assert grouped["camera"][0]["id"] == "camera.front"


def test_invoke_delegates_to_provider(client, with_api_key, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(registry, "build_provider", lambda pid, **kw: fake)
    r = client.post(f"{BASE}/homeassistant/invoke",
                    json={"capability": "pip", "target": "camera.front"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert fake.invocations == [("pip", "camera.front", {})]


def test_health_reports_unknown_provider(client, with_api_key, monkeypatch):
    monkeypatch.setattr(registry, "build_provider", lambda pid, **kw: None)
    r = client.get(f"{BASE}/ghost/health", headers=AUTH)
    assert r.status_code == 404


def test_list_integrations_returns_seeded_provider(client, with_api_key):
    # The startup seed provisions the homeassistant provider; the list route
    # surfaces it (id/kind/enabled/config) and must never leak secrets.
    r = client.get(BASE, headers=AUTH)
    assert r.status_code == 200
    providers = {p["id"]: p for p in r.json()["providers"]}
    assert "homeassistant" in providers
    assert providers["homeassistant"]["kind"] == "homeassistant"
    assert "token" not in json.dumps(providers)  # no secret in the listing
