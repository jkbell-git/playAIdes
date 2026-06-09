import json
from pathlib import Path

from backend.stores import launch_targets


def test_defaults_present():
    assert set(launch_targets.DEFAULT_LAUNCH_TARGETS) == {"bedroom", "box8", "living"}


def test_load_falls_back_when_store_missing(tmp_path: Path):
    out = launch_targets.load_launch_targets(
        store_path=str(tmp_path / "nope.json"),
        fallback=launch_targets.DEFAULT_LAUNCH_TARGETS,
    )
    assert out == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_load_reads_launch_targets_from_store(tmp_path: Path):
    path = tmp_path / "integrations.json"
    path.write_text(json.dumps({
        "mappings": {"launch_targets": [
            {"provider": "homeassistant", "entity": "media_player.tv_a", "label": "den"},
            {"provider": "homeassistant", "entity": "media_player.tv_b", "label": "office"},
        ]}
    }))
    out = launch_targets.load_launch_targets(
        store_path=str(path), fallback=launch_targets.DEFAULT_LAUNCH_TARGETS)
    assert out == {"den": "media_player.tv_a", "office": "media_player.tv_b"}


def test_load_falls_back_when_mapping_empty(tmp_path: Path):
    path = tmp_path / "integrations.json"
    path.write_text(json.dumps({"mappings": {"launch_targets": []}}))
    out = launch_targets.load_launch_targets(
        store_path=str(path), fallback=launch_targets.DEFAULT_LAUNCH_TARGETS)
    assert out == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_load_falls_back_on_unreadable_store(tmp_path: Path):
    # A store path that exists but can't be JSON-read (here a directory -> OSError)
    # must degrade to defaults, not crash. Guards the field case where a root-owned
    # config/integrations.json (mode 600) crashed bin/silver-launch.py.
    bad = tmp_path / "integrations.json"
    bad.mkdir()
    out = launch_targets.load_launch_targets(
        store_path=str(bad), fallback=launch_targets.DEFAULT_LAUNCH_TARGETS)
    assert out == launch_targets.DEFAULT_LAUNCH_TARGETS
