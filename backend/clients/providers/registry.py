"""Construct a live Provider for a given provider id from the config + secrets stores.

The single seam the API routes go through, so tests can monkeypatch build_provider
to return a FakeProvider without touching HTTP.
"""
from __future__ import annotations

import os
from typing import Optional

from backend.stores import config_store, secrets_store
from backend.clients.providers.base import Provider
from backend.clients.providers.homeassistant import HomeAssistantProvider


def build_provider(
    provider_id: str,
    store_path: str = config_store.DEFAULT_PATH,
    secret_path: str = secrets_store.DEFAULT_PATH,
) -> Optional[Provider]:
    store = config_store.load(store_path)
    pconf = (store.get("providers") or {}).get(provider_id)
    if not pconf or not pconf.get("enabled", True):
        return None
    if pconf.get("kind") == "homeassistant":
        base_url = (pconf.get("config") or {}).get("base_url") or os.environ.get("HA_URL", "")
        token = secrets_store.resolve_token(provider_id, secret_path) or ""
        return HomeAssistantProvider(base_url, token)
    return None
