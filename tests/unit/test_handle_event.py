# tests/unit/test_handle_event.py
import sys
import types
from unittest.mock import MagicMock

# Stub out unavailable native deps so PlayAIdes can be imported without
# the full Docker environment (mirrors test_chat_skill_dispatch.py).
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models"):  # native deps only; incarnation_server/ha_client are real (mocking them in sys.modules leaks into integration tests)
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from persona import Trigger
from skills.registry import SkillRegistry
from skills.pip import ShowPipSkill


def _make_ai(skills, triggers):
    from playAIdes import PlayAIdes
    from incarnation_server import WebSocketDisplayChannel
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.incarnation_server = MagicMock()
    ai.display = WebSocketDisplayChannel(ai.incarnation_server)
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.ha_client = None
    reg = SkillRegistry()
    reg.register(ShowPipSkill())
    ai.skill_registry = reg
    ai.current_persona = types.SimpleNamespace(
        name="Silver", persona_voice=None, language="English",
        skills=skills, triggers=triggers,
    )
    return ai


def test_event_fires_enabled_skill():
    triggers = [Trigger(on={"event": "motion", "match": {"state": "on"}},
                        do={"skill": "show_pip", "params": {"url": "http://x/s", "kind": "live"}})]
    ai = _make_ai(["show_pip"], triggers)
    result = ai.handle_event("motion", {"state": "on"})
    assert result == {"matched": True, "skill": "show_pip"}
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/s", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )


def test_event_registered_but_not_enabled_does_not_fire():
    # show_pip is registered AND a trigger references it, but it is NOT in the
    # persona's enable-list. The event path must NOT dispatch it. (The footgun.)
    triggers = [Trigger(on={"event": "motion"}, do={"skill": "show_pip", "params": {"url": "u"}})]
    ai = _make_ai([], triggers)                       # empty enable-list
    result = ai.handle_event("motion", {})
    assert result == {"matched": False}
    ai.incarnation_server.broadcast_to_persona.assert_not_called()


def test_event_no_matching_trigger():
    ai = _make_ai(["show_pip"], [])
    assert ai.handle_event("nothing", {}) == {"matched": False}


def test_event_no_persona():
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.current_persona = None
    assert ai.handle_event("motion", {}) == {"matched": False}


def test_event_malformed_persona_does_not_raise():
    # persona.skills is None (corrupt) — is_enabled would raise TypeError;
    # handle_event must swallow it and return matched=False, not propagate.
    triggers = [Trigger(on={"event": "motion"}, do={"skill": "show_pip", "params": {"url": "u"}})]
    ai = _make_ai(None, triggers)
    assert ai.handle_event("motion", {}) == {"matched": False}
