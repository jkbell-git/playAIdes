# tests/unit/test_silver_launch_targets.py
"""bin/silver-launch.py resolves its launch targets from the config store
(via backend.stores.launch_targets), falling back to the hardcoded defaults."""
import importlib.util
import os

from backend.stores import launch_targets

_SILVER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "bin", "silver-launch.py")


def _load_silver_launch():
    spec = importlib.util.spec_from_file_location("silver_launch", _SILVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_silver_launch_exposes_fallback_defaults():
    mod = _load_silver_launch()
    assert mod._FALLBACK_BOXES == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_silver_launch_resolves_targets_via_store(tmp_path):
    mod = _load_silver_launch()
    store = tmp_path / "integrations.json"
    store.write_text('{"mappings": {"launch_targets": '
                     '[{"entity": "media_player.x", "label": "den"}]}}')
    boxes = mod.resolve_boxes(store_path=str(store))
    assert boxes == {"den": "media_player.x"}
