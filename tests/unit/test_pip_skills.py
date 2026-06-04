from skills.base import SkillContext
from skills.pip import ShowPipSkill, DismissPipSkill


def _ctx():
    sent, spoken = [], []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda pid, t, p: sent.append((pid, t, p)),
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    return ctx, sent, spoken


def test_show_pip_sends_show_message():
    ctx, sent, spoken = _ctx()
    skill = ShowPipSkill()
    skill.execute(skill.Params(url="http://x/stream", kind="live"), ctx)
    assert sent == [("silver", "show_pip",
                     {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}})]
    assert spoken == []   # silent: no announce


def test_show_pip_announce_speaks():
    ctx, sent, spoken = _ctx()
    skill = ShowPipSkill()
    skill.execute(skill.Params(url="http://x.jpg", announce="Someone's at the door."), ctx)
    assert sent[0][1] == "show_pip"
    assert spoken == [("silver", "Someone's at the door.")]


def test_dismiss_pip_sends_dismiss_message():
    ctx, sent, spoken = _ctx()
    skill = DismissPipSkill()
    skill.execute(skill.Params(), ctx)
    assert sent == [("silver", "dismiss_pip", {})]
