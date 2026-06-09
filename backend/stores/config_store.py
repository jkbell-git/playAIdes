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
