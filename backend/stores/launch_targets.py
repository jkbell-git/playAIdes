"""Fire-TV launch targets — the canonical defaults plus a store-aware loader.

Single source of truth shared by the migration seed (config_store.seed_if_absent)
and bin/silver-launch.py, so rewiring the launcher to read the config store is a
non-breaking change: when the store has no launch_targets mapping, the hardcoded
defaults are used.
"""
from __future__ import annotations

import json
from typing import Optional

# The Fire TV media_player entities that were hardcoded as BOXES in
# bin/silver-launch.py (label -> entity_id).
DEFAULT_LAUNCH_TARGETS: dict[str, str] = {
    "bedroom": "media_player.fire_tv_192_168_0_233",
    "box8":    "media_player.fire_tv_192_168_0_8",
    "living":  "media_player.fire_tv_192_168_0_234",
}


def load_launch_targets(store_path: str = "config/integrations.json",
                        fallback: Optional[dict] = None) -> dict:
    """Return {label: entity_id} from the store's launch_targets mapping, falling
    back to `fallback` (the hardcoded defaults) when the store or mapping is absent."""
    fallback = dict(fallback or {})
    try:
        with open(store_path) as f:
            store = json.load(f)
    except (OSError, ValueError):
        # Missing, unreadable (e.g. bad perms), or malformed store -> defaults.
        return fallback
    targets = (store.get("mappings") or {}).get("launch_targets") or []
    out: dict[str, str] = {}
    for t in targets:
        label, entity = t.get("label"), t.get("entity")
        if label and entity:
            out[label] = entity
    return out or fallback
