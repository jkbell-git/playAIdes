# tests/unit/test_skill_loader.py
import json

import pytest

from skills.loader import load_skill_packs


def _write_pack(tmp_path, fname, obj):
    p = tmp_path / fname
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_missing_directory_returns_empty(tmp_path):
    assert load_skill_packs(str(tmp_path / "nope")) == []


def test_loads_bash_and_http_skills(tmp_path):
    _write_pack(tmp_path, "pack.json", {"skills": [
        {"name": "a", "kind": "bash", "command": ["echo", "hi"], "params": {}},
        {"name": "b", "kind": "http", "url": "https://x/y", "params": {}},
    ]})
    skills = load_skill_packs(str(tmp_path))
    by_name = {s.name: s for s in skills}
    assert set(by_name) == {"a", "b"}
    assert by_name["a"].kind == "bash" and by_name["b"].kind == "http"


def test_unknown_kind_fails_fast(tmp_path):
    _write_pack(tmp_path, "bad.json", {"skills": [{"name": "x", "kind": "telepathy"}]})
    with pytest.raises(ValueError, match="unknown kind"):
        load_skill_packs(str(tmp_path))


def test_missing_name_fails_fast(tmp_path):
    _write_pack(tmp_path, "bad.json", {"skills": [{"kind": "bash", "command": ["echo"]}]})
    with pytest.raises(ValueError, match="missing 'name'"):
        load_skill_packs(str(tmp_path))


def test_duplicate_name_across_packs_fails_fast(tmp_path):
    _write_pack(tmp_path, "a.json", {"skills": [{"name": "dup", "kind": "bash", "command": ["echo"]}]})
    _write_pack(tmp_path, "b.json", {"skills": [{"name": "dup", "kind": "bash", "command": ["echo"]}]})
    with pytest.raises(ValueError, match="duplicate"):
        load_skill_packs(str(tmp_path))
