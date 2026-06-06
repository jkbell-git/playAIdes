# skills/provider.py
"""External-pack contribution point (spec §3.2). A SkillProvider supplies a list
of Skills via skills(). v1 defines the Protocol and lets the registry accept
provider-sourced skills (SkillRegistry.register_provider); automatic discovery /
loading of providers is deferred (spec §10)."""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from skills.base import Skill


@runtime_checkable
class SkillProvider(Protocol):
    def skills(self) -> List[Skill]: ...
