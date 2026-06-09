import json
from pathlib import Path

from backend.stores import config_store


def test_load_missing_returns_empty_skeleton(tmp_path: Path):
    data = config_store.load(str(tmp_path / "integrations.json"))
    assert data == {"providers": {}, "mappings": {}}


def test_save_then_load_roundtrips(tmp_path: Path):
    path = str(tmp_path / "config" / "integrations.json")  # nested dir is created
    payload = {"providers": {"homeassistant": {"kind": "homeassistant"}},
               "mappings": {"launch_targets": []}}
    config_store.save(payload, path)
    assert json.loads(Path(path).read_text()) == payload
    assert config_store.load(path) == payload


def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path):
    path = str(tmp_path / "integrations.json")
    config_store.save({"providers": {}, "mappings": {}}, path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
