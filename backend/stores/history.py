"""Pure file I/O for per-persona chat history (personas/<id>/chat_history.json).

Atomic writes (sibling tempfile + os.replace, unlink-on-failure) ported
verbatim from PlayAIdes._save_history so a mid-write crash never corrupts the
file. Corrupt/unreadable history degrades to empty with a warning (ported from
PlayAIdes._load_history).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Union

from backend.stores.personas import _check_id

logger = logging.getLogger(__name__)


class HistoryStore:
    def __init__(self, base_dir: Union[str, Path] = "personas"):
        self.base_dir = Path(base_dir)

    def _path(self, persona_id: str) -> Path:
        _check_id(persona_id)
        return self.base_dir / persona_id / "chat_history.json"

    def read(self, persona_id: str) -> list:
        path = self._path(persona_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s — starting empty", path, e)
            return []

    def write(self, persona_id: str, history: list) -> None:
        path = self._path(persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling tempfile, then atomically rename over the target.
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(path.parent), delete=False,
            prefix=".chat_history.", suffix=".json.tmp",
        ) as tf:
            json.dump(history, tf, ensure_ascii=False, indent=2)
            tmp_path = tf.name
        try:
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def delete(self, persona_id: str) -> None:
        path = self._path(persona_id)
        if path.exists():
            path.unlink()
