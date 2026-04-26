"""Unit tests for find_default_persona_id — picks the boot persona when
the URL/CLI doesn't specify one."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from playAIdes import find_default_persona_id


def _seed(tmp_path: Path, name: str, is_default: bool):
    pdir = tmp_path / name
    pdir.mkdir()
    (pdir / "persona.json").write_text(json.dumps({
        "name": name.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "is_default": is_default,
    }))


def test_returns_id_of_persona_with_is_default_true(tmp_path):
    _seed(tmp_path, "alice", is_default=False)
    _seed(tmp_path, "silver", is_default=True)
    _seed(tmp_path, "zelda", is_default=False)
    assert find_default_persona_id(tmp_path) == "silver"


def test_falls_back_to_first_alphabetical_when_no_default(tmp_path, caplog):
    _seed(tmp_path, "zelda", is_default=False)
    _seed(tmp_path, "alice", is_default=False)
    _seed(tmp_path, "silver", is_default=False)
    assert find_default_persona_id(tmp_path) == "alice"
    # Spec §7: "If none flagged, fall back to the first persona
    # alphabetically and log a warning."
    assert any("no is_default" in r.message.lower() for r in caplog.records)


def test_returns_none_when_no_personas(tmp_path):
    assert find_default_persona_id(tmp_path) is None


def test_skips_invalid_persona_dirs(tmp_path):
    _seed(tmp_path, "alice", is_default=False)
    # A directory with no persona.json — should be skipped silently.
    (tmp_path / "broken").mkdir()
    # A persona.json that's not valid JSON — should be skipped silently.
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "persona.json").write_text("{not json")
    assert find_default_persona_id(tmp_path) == "alice"
