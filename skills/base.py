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

    def send_display(self, cmd_type: str, payload: Optional[dict] = None) -> None:
        self.send(self.target_id, cmd_type, payload or {})

    def speak(self, text: str) -> None:
        self.speak_fn(self.target_id, text)


class Skill:
    """Base for all skills. Subclasses set `name`, `Params`, and `execute`."""
    name: str
    Params: type[BaseModel]
    kind: str = "internal"

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        raise NotImplementedError
