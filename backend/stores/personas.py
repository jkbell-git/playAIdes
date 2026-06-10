"""Pure file I/O for persona documents (personas/<id>/persona.json).

No Pydantic, no business rules — validation and domain logic live in
backend/services/persona.py. The path-traversal guard lives HERE because it
protects the filesystem (spec 2026-06-10, component 1). Constructor-arg base
dir so tests run on tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Union


def _check_id(persona_id: str) -> None:
    """Reject ids that could escape the base directory (ported from
    PlayAIdes.delete_persona / _history_path)."""
    if (not persona_id or "/" in persona_id or "\\" in persona_id
            or persona_id in {".", ".."}):
        raise ValueError(f"Suspicious persona_id: {persona_id!r}")


class PersonaStore:
    def __init__(self, base_dir: Union[str, Path] = "personas"):
        self.base_dir = Path(base_dir)

    def _dir(self, persona_id: str) -> Path:
        _check_id(persona_id)
        return self.base_dir / persona_id

    def list_ids(self) -> list:
        """Ids of subdirectories containing a persona.json. Creates the base
        dir if absent (ported from PlayAIdes.list_personas)."""
        os.makedirs(self.base_dir, exist_ok=True)
        return sorted(
            d.name for d in self.base_dir.iterdir()
            if d.is_dir() and (d / "persona.json").exists()
        )

    def exists(self, persona_id: str) -> bool:
        return (self._dir(persona_id) / "persona.json").exists()

    def read(self, persona_id: str) -> dict:
        path = self._dir(persona_id) / "persona.json"
        if not path.exists():
            raise KeyError(persona_id)
        with open(path) as f:
            return json.load(f)

    def write(self, persona_id: str, data: dict) -> None:
        d = self._dir(persona_id)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "persona.json", "w") as f:
            json.dump(data, f, indent=2)

    def delete(self, persona_id: str) -> None:
        d = self._dir(persona_id)
        if not d.is_dir():
            raise KeyError(persona_id)
        shutil.rmtree(d)
