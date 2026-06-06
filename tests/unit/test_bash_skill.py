# tests/unit/test_bash_skill.py
from skills.base import SkillContext
from skills.declarative import BashSkill, build_params_model


def _ctx():
    spoken = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda *a: None,
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    return ctx, spoken


def test_build_params_model_validates_types():
    M = build_params_model("demo", {"name": "str", "count": "int"})
    m = M(name="x", count="3")          # pydantic coerces "3" -> 3
    assert m.name == "x" and m.count == 3


def test_build_params_model_rejects_unknown_type():
    try:
        build_params_model("demo", {"bad": "datetime"})
        assert False, "expected ValueError on unknown type"
    except ValueError:
        pass


def test_bash_skill_runs_echo_and_returns_output():
    spec = {"name": "say_hi", "kind": "bash",
            "command": ["echo", "hi {who}"], "params": {"who": "str"}}
    skill = BashSkill(spec)
    assert skill.name == "say_hi" and skill.kind == "bash"
    ctx, spoken = _ctx()
    res = skill.execute(skill.Params(who="bell"), ctx)
    assert res.ok is True
    assert res.output == "hi bell"
    assert spoken == []                 # announce_output defaults False


def test_bash_skill_announces_output_when_configured():
    spec = {"name": "say", "kind": "bash", "command": ["echo", "done"],
            "params": {}, "announce_output": True}
    ctx, spoken = _ctx()
    BashSkill(spec).execute(BashSkill(spec).Params(), ctx)
    assert spoken == [("silver", "done")]


def test_bash_skill_no_shell_injection():
    # A param value that WOULD be dangerous in a shell is passed as one argv
    # element, never interpreted. `echo` prints it literally; nothing executes.
    spec = {"name": "danger", "kind": "bash",
            "command": ["echo", "{arg}"], "params": {"arg": "str"}}
    ctx, _ = _ctx()
    res = BashSkill(spec).execute(BashSkill(spec).Params(arg="; rm -rf /"), ctx)
    assert res.ok is True
    assert res.output == "; rm -rf /"   # literal — the `;` did nothing


def test_bash_skill_nonzero_exit_marks_failure():
    spec = {"name": "fail", "kind": "bash", "command": ["false"], "params": {}}
    ctx, _ = _ctx()
    res = BashSkill(spec).execute(BashSkill(spec).Params(), ctx)
    assert res.ok is False
