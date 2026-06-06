import pytest
from pydantic import ValidationError
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


def _ctx_with_camera(resolved):
    sent, spoken = [], []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda pid, t, p: sent.append((pid, t, p)),
        speak_fn=lambda pid, text: spoken.append((pid, text)),
        resolve_camera=lambda entity_id, live: resolved,
    )
    return ctx, sent, spoken


def test_show_pip_resolves_camera_source_to_url():
    ctx, sent, _ = _ctx_with_camera("http://ha/api/camera_proxy_stream/camera.fd?token=T")
    ShowPipSkill().execute(ShowPipSkill().Params(source="camera.fd", kind="live"), ctx)
    assert sent[0][1] == "show_pip"
    assert sent[0][2]["url"] == "http://ha/api/camera_proxy_stream/camera.fd?token=T"
    assert sent[0][2]["kind"] == "live"


def test_show_pip_unresolved_source_is_failure_no_send():
    ctx, sent, _ = _ctx_with_camera(None)        # resolution returned None
    res = ShowPipSkill().execute(ShowPipSkill().Params(source="camera.fd"), ctx)
    assert res.ok is False
    assert sent == []                            # nothing shown


def test_show_pip_requires_url_or_source():
    with pytest.raises(ValidationError):
        ShowPipSkill().Params()                  # neither url nor source
