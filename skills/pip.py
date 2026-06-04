"""Internal (hard-typed) PiP skills (spec §3.10). v1 takes a direct url;
HA-entity → camera_proxy resolution is Plan 2."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from skills.base import Skill, SkillContext, SkillResult


class ShowPipSkill(Skill):
    name = "show_pip"
    kind = "internal"

    class Params(BaseModel):
        url: str
        kind: Literal["live", "snapshot"] = "snapshot"
        dismiss: dict = {"type": "until_dismissed"}
        announce: Optional[str] = None

    def execute(self, params: "ShowPipSkill.Params", ctx: SkillContext) -> SkillResult:
        ctx.send_display("show_pip", {
            "url": params.url,
            "kind": params.kind,
            "dismiss": params.dismiss,
        })
        if params.announce:
            ctx.speak(params.announce)
        return SkillResult(ok=True)


class DismissPipSkill(Skill):
    name = "dismiss_pip"
    kind = "internal"

    class Params(BaseModel):
        pass

    def execute(self, params: "DismissPipSkill.Params", ctx: SkillContext) -> SkillResult:
        ctx.send_display("dismiss_pip", {})
        return SkillResult(ok=True)
