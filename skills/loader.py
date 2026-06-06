# skills/loader.py
"""Load declarative (bash/http) skills from JSON packs in a global directory
(spec §3.3 step 2). Each pack file is {"skills": [ {name, kind, ...}, ... ]}.
Fail-fast (raise) on unknown kind, missing name, malformed JSON, or a duplicate
name across packs — registry/load errors must surface at startup (spec §6)."""
from __future__ import annotations

import json
import logging
import os
from typing import List

from skills.base import Skill
from skills.declarative import BashSkill, HttpSkill

logger = logging.getLogger(__name__)

_KINDS = {"bash": BashSkill, "http": HttpSkill}


def load_skill_packs(directory: str) -> List[Skill]:
    skills: List[Skill] = []
    seen: set[str] = set()
    if not os.path.isdir(directory):
        logger.info("skill pack dir %r not present; no declarative skills loaded.", directory)
        return skills
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(directory, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)                         # JSONDecodeError → fail-fast
        for spec in data.get("skills", []):
            name = spec.get("name")
            kind = spec.get("kind")
            if not name:
                raise ValueError(f"{path}: a skill spec is missing 'name'")
            if kind not in _KINDS:
                raise ValueError(
                    f"{path}: skill {name!r} has unknown kind {kind!r} "
                    f"(allowed: {sorted(_KINDS)})"
                )
            if name in seen:
                raise ValueError(f"duplicate declarative skill name {name!r} (in {path})")
            seen.add(name)
            skills.append(_KINDS[kind](spec))           # spec-validation errors fail-fast too
    logger.info("Loaded %d declarative skill(s) from %s", len(skills), directory)
    return skills
