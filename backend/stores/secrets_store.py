"""Write-only secrets store for provider credentials (config/secrets.json).

Secrets are POSTed once to the API, persisted here, and NEVER returned to the
browser or echoed in any response. `resolve_token` reads this file first and
falls back to the HA_TOKEN env var so existing .env-based setups keep working.
Writes are atomic.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

DEFAULT_PATH = "config/secrets.json"


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def set_secret(provider_id: str, key: str, value: str, path: str = DEFAULT_PATH) -> None:
    data = _load(path)
    data.setdefault(provider_id, {})[key] = value
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def get_secret(provider_id: str, key: str, path: str = DEFAULT_PATH) -> Optional[str]:
    return (_load(path).get(provider_id) or {}).get(key)


def resolve_token(provider_id: str = "homeassistant", path: str = DEFAULT_PATH,
                  env: Optional[dict] = None) -> Optional[str]:
    """Resolve the provider token: secrets file first, then HA_TOKEN env fallback."""
    from_file = get_secret(provider_id, "token", path)
    if from_file:
        return from_file
    return (env if env is not None else os.environ).get("HA_TOKEN")
