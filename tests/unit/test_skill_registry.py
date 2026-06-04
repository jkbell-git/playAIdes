import pytest
from pydantic import BaseModel
from skills.base import Skill, SkillResult
from skills.registry import SkillRegistry


class _Fake(Skill):
    name = "fake"
    class Params(BaseModel):
        pass
    def execute(self, params, ctx):
        return SkillResult()


def test_register_and_get():
    reg = SkillRegistry()
    reg.register(_Fake())
    assert reg.get("fake").name == "fake"
    assert reg.get("missing") is None


def test_duplicate_name_raises():
    reg = SkillRegistry()
    reg.register(_Fake())
    with pytest.raises(ValueError):
        reg.register(_Fake())


def test_is_enabled_checks_persona_list():
    reg = SkillRegistry()
    reg.register(_Fake())
    assert reg.is_enabled("fake", ["fake", "other"]) is True
    assert reg.is_enabled("fake", []) is False
    assert reg.is_enabled("missing", ["missing"]) is False   # not registered
