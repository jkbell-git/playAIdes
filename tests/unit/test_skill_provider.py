# tests/unit/test_skill_provider.py
from pydantic import BaseModel

from skills.base import Skill, SkillResult
from skills.provider import SkillProvider
from skills.registry import SkillRegistry


class _Fake(Skill):
    name = "p_skill"
    class Params(BaseModel):
        pass
    def execute(self, params, ctx):
        return SkillResult()


class _Provider:
    def skills(self):
        return [_Fake()]


def test_provider_satisfies_protocol():
    assert isinstance(_Provider(), SkillProvider)   # runtime_checkable structural check


def test_register_provider_registers_each_skill():
    reg = SkillRegistry()
    reg.register_provider(_Provider())
    assert reg.get("p_skill").name == "p_skill"


def test_register_all_registers_iterable():
    reg = SkillRegistry()
    reg.register_all([_Fake()])
    assert reg.get("p_skill") is not None
