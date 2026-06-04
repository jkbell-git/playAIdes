import pytest
from pydantic import BaseModel
from skills.base import Skill, SkillContext, SkillResult


def test_skill_result_defaults_ok():
    r = SkillResult()
    assert r.ok is True
    assert r.output is None and r.error is None


def test_skill_context_send_display_uses_target_id():
    sent = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda pid, t, p: sent.append((pid, t, p)),
        speak_fn=lambda pid, text: None,
    )
    ctx.send_display("show_pip", {"url": "http://x"})
    assert sent == [("silver", "show_pip", {"url": "http://x"})]


def test_skill_context_speak_uses_target_id():
    spoken = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda *a: None,
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    ctx.speak("hello")
    assert spoken == [("silver", "hello")]


def test_skill_base_requires_execute():
    class Noop(Skill):
        name = "noop"
        class Params(BaseModel):
            pass
    s = Noop()
    assert s.name == "noop" and s.kind == "internal"
    with pytest.raises(NotImplementedError):
        s.execute(Noop.Params(), None)
