"""Home Assistant provider — wraps the (root) HAClient behind the seam.

discover() reads GET /api/states and surfaces only the v1 domains; invoke()
test-fires a capability (resolve a camera URL, or run a script).
"""
from __future__ import annotations

from typing import Optional

from ha_client import HAClient  # root module (re-homed to backend/clients/ha.py later)
from backend.clients.providers.base import (
    Provider, Status, Item,
    CAP_PIP, CAP_SAY_TARGET, CAP_LAUNCH_TARGETS, CAP_SCRIPTS,
)

# HA domains surfaced in v1, and which playAIdes capabilities each can fill.
_DOMAIN_CAPS: dict[str, list[str]] = {
    "camera": [CAP_PIP],
    "media_player": [CAP_SAY_TARGET, CAP_LAUNCH_TARGETS],
    "script": [CAP_SCRIPTS],
}


class HomeAssistantProvider(Provider):
    kind = "homeassistant"
    config_schema = ["base_url"]

    def __init__(self, base_url: str, token: str, timeout: float = 5.0):
        self._client = HAClient(base_url, token, timeout=timeout)

    def health(self) -> Status:
        if self._client.health_check():
            return Status(ok=True)
        return Status(ok=False, reason="Home Assistant unreachable or token rejected")

    def discover(self) -> list[Item]:
        states = self._client.get_states() or []
        items: list[Item] = []
        for s in states:
            entity_id = s.get("entity_id", "")
            domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
            caps = _DOMAIN_CAPS.get(domain)
            if not caps:
                continue
            name = (s.get("attributes") or {}).get("friendly_name") or entity_id
            items.append(Item(id=entity_id, domain=domain, name=name,
                              capabilities=list(caps)))
        items.sort(key=lambda i: (i.domain, i.id))
        return items

    def invoke(self, capability: str, target: str, args: Optional[dict] = None) -> dict:
        if capability == CAP_PIP:
            # Camera-kind PiP source: resolve the live, token-rotating stream URL.
            # (url-kind PiP sources are operator-entered and never reach a provider.)
            url = self._client.camera_url(target)
            if url:
                return {"ok": True, "url": url}
            return {"ok": False, "reason": "camera entity did not resolve to a stream"}
        if capability == CAP_SCRIPTS:
            ok = self._client.call_service("script", "turn_on", {"entity_id": target})
            return {"ok": ok} if ok else {"ok": False, "reason": "script service call failed"}
        return {"ok": False, "reason": f"unsupported capability {capability!r}"}
