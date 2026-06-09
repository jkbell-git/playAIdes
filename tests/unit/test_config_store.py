import json
from pathlib import Path

from backend.stores import config_store
from backend.stores import launch_targets


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


def test_seed_writes_once_from_defaults(tmp_path):
    path = str(tmp_path / "config" / "integrations.json")
    seeded = config_store.seed_if_absent(path, env={"HA_URL": "http://ha.local:8123/"})
    assert seeded is True
    data = config_store.load(path)
    assert data["providers"]["homeassistant"]["kind"] == "homeassistant"
    assert data["providers"]["homeassistant"]["config"]["base_url"] == "http://ha.local:8123"
    labels = {t["label"]: t["entity"] for t in data["mappings"]["launch_targets"]}
    assert labels == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_seed_is_idempotent(tmp_path):
    path = str(tmp_path / "integrations.json")
    assert config_store.seed_if_absent(path, env={"HA_URL": "x"}) is True
    assert config_store.seed_if_absent(path, env={"HA_URL": "y"}) is False  # already there
    assert config_store.load(path)["providers"]["homeassistant"]["config"]["base_url"] == "x"
