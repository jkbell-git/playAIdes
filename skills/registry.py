"""Name → Skill map. Internal skills register here at startup (spec §3.3).
Declarative (bash/http) and provider skills are added in Plan 2."""
from __future__ import annotations

from typing import Optional

from skills.base import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def is_enabled(self, name: str, enabled_skills: list[str]) -> bool:
        """True only if the skill is both registered AND enabled for the persona."""
        return name in self._skills and name in enabled_skills
