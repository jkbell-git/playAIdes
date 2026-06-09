"""In-memory provider implementing the seam — used in tests and as the v2/v3 template."""
from __future__ import annotations

from typing import Optional

from backend.clients.providers.base import Provider, Status, Item


class FakeProvider(Provider):
    kind = "fake"
    config_schema = ["base_url"]

    def __init__(self, items: Optional[list[Item]] = None, healthy: bool = True):
        self._items = list(items or [])
        self._healthy = healthy
        self.invocations: list[tuple] = []

    def health(self) -> Status:
        if self._healthy:
            return Status(ok=True)
        return Status(ok=False, reason="fake provider is offline")

    def discover(self) -> list[Item]:
        return list(self._items)

    def invoke(self, capability: str, target: str, args: Optional[dict] = None) -> dict:
        args = args or {}
        self.invocations.append((capability, target, args))
        return {"ok": True, "capability": capability, "target": target}
