"""Common interface for persona skills (spec §3.1).

A Skill is a named capability behind one interface; the deterministic router
(now) and the future agentic router both dispatch the same Skill objects.
Skills are synchronous: PlayAIdes.chat() is synchronous and the WS broadcast
helper schedules sends on the WS loop internally, so no event loop is needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel


class SkillResult(BaseModel):
    ok: bool = True
    output: Optional[str] = None    # e.g. bash stdout / http body excerpt (Plan 2)
    error: Optional[str] = None


@dataclass
class SkillContext:
    """A skill's only door to the system, bound to one persona invocation."""
    persona: Any                                  # persona.Persona (Any to avoid import cycle)
    target_id: str                                # canonical persona id this turn routes to
    send: Callable[[str, str, dict], None]        # (persona_id, cmd_type, payload) -> WS push
    speak_fn: Callable[[str, str], None]          # (persona_id, text) -> subtitle + TTS
    resolve_camera: Optional[Callable[[str, bool], Optional[str]]] = None  # (entity_id, live) -> url | None

    def send_display(self, cmd_type: str, payload: Optional[dict] = None) -> None:
        self.send(self.target_id, cmd_type, payload or {})

    def speak(self, text: str) -> None:
        self.speak_fn(self.target_id, text)

    def resolve_camera_url(self, entity_id: str, live: bool = False) -> Optional[str]:
        """Resolve an HA camera entity to a proxy URL, or None if HA is not
        configured / unavailable. The skill's only door to camera resolution."""
        if self.resolve_camera is None:
            return None
        return self.resolve_camera(entity_id, live)


class Skill:
    """Base for all skills. Subclasses set `name`, `Params`, and `execute`."""
    name: str
    Params: type[BaseModel]
    kind: str = "internal"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "name") or not isinstance(getattr(cls, "name", None), str):
            raise TypeError(f"{cls.__name__} must define a string class attribute 'name'")
        if not hasattr(cls, "Params"):
            raise TypeError(f"{cls.__name__} must define a 'Params' inner class")

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        raise NotImplementedError
