"""Typed load/save for the integrations config store (config/integrations.json).

The single source of truth for provider connection config and capability->entity
mappings. Writes are atomic (temp file + os.replace) so a mid-write crash never
corrupts the file. The HA token is NOT stored here — see secrets_store.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

DEFAULT_PATH = "config/integrations.json"


def _empty() -> dict:
    return {"providers": {}, "mappings": {}}


def load(path: str = DEFAULT_PATH) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return _empty()


def save(data: dict, path: str = DEFAULT_PATH) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)  # atomic on POSIX
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def seed_if_absent(path: str = DEFAULT_PATH, env: Optional[dict] = None) -> bool:
    """One-time migration: if the store is absent, write an initial version from
    today's hardcoded values (HA base_url from env, the Fire-TV launch targets).
    Returns True if it seeded, False if the store already existed.

    pip / say_target are intentionally left unmapped — the operator maps them in
    the console (pip takes a camera or url source; see the plan's deferral note).
    Idempotent: never overwrites an existing store."""
    from backend.stores import launch_targets  # local import keeps load/save lean

    if os.path.exists(path):
        return False
    env = env if env is not None else os.environ
    base_url = (env.get("HA_URL") or "").rstrip("/")
    data = {
        "providers": {
            "homeassistant": {
                "kind": "homeassistant",
                "enabled": True,
                "config": {"base_url": base_url},
            }
        },
        "mappings": {
            "launch_targets": [
                {"provider": "homeassistant", "entity": entity, "label": label}
                for label, entity in launch_targets.DEFAULT_LAUNCH_TARGETS.items()
            ],
        },
    }
    save(data, path)
    return True
