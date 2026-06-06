"""Internal (hard-typed) PiP skills (spec §3.10). A trigger supplies either a
direct `url` or an HA camera `source` (entity_id) that is resolved to a fresh
camera_proxy URL via the SkillContext (Plan 2)."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

from skills.base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class ShowPipSkill(Skill):
    name = "show_pip"
    kind = "internal"

    class Params(BaseModel):
        url: Optional[str] = None
        source: Optional[str] = None          # HA camera entity_id (resolved at dispatch)
        kind: Literal["live", "snapshot"] = "snapshot"
        dismiss: dict = {"type": "until_dismissed"}
        announce: Optional[str] = None

        @model_validator(mode="after")
        def require_url_or_source(self) -> "ShowPipSkill.Params":
            if not self.url and not self.source:
                raise ValueError("show_pip requires either 'url' or 'source' (camera entity)")
            return self

    def execute(self, params: "ShowPipSkill.Params", ctx: SkillContext) -> SkillResult:
        url = params.url
        if not url and params.source:
            url = ctx.resolve_camera_url(params.source, live=(params.kind == "live"))
        if not url:
            logger.warning("show_pip: could not resolve a url (source=%r)", params.source)
            return SkillResult(ok=False, error="unresolved camera source")
        ctx.send_display("show_pip", {
            "url": url,
            "kind": params.kind,
            "dismiss": params.dismiss,
        })
        if params.announce:
            ctx.speak(params.announce)
        return SkillResult()


class DismissPipSkill(Skill):
    name = "dismiss_pip"
    kind = "internal"

    class Params(BaseModel):
        pass

    def execute(self, params: "DismissPipSkill.Params", ctx: SkillContext) -> SkillResult:
        ctx.send_display("dismiss_pip", {})
        return SkillResult()
