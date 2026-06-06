import sys
import types
from unittest.mock import MagicMock

# Stub out unavailable native deps so PlayAIdes can be imported without
# the full Docker environment.
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models", "incarnation_server", "ha_client"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from persona import Trigger
from skills.registry import SkillRegistry
from skills.pip import ShowPipSkill


def _make_ai():
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.incarnation_server = MagicMock()
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.current_persona = types.SimpleNamespace(name="Silver", persona_voice=None, language="English")
    reg = SkillRegistry()
    reg.register(ShowPipSkill())
    ai.skill_registry = reg
    ai.ha_client = None   # _dispatch_skill builds a ctx wired to _resolve_camera_url
    return ai


def test_dispatch_skill_runs_skill_and_sends_ws():
    ai = _make_ai()
    ai._dispatch_skill("silver", "show_pip", {"url": "http://x/stream", "kind": "live"})
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )


def test_dispatch_unknown_skill_is_noop():
    ai = _make_ai()
    ai._dispatch_skill("silver", "nope", {})       # must not raise
    ai.incarnation_server.broadcast_to_persona.assert_not_called()


def test_dispatch_bad_params_is_noop():
    ai = _make_ai()
    ai._dispatch_skill("silver", "show_pip", {})    # neither url nor source; must not raise
    ai.incarnation_server.broadcast_to_persona.assert_not_called()


def _make_chat_ai():
    ai = _make_ai()
    ai.llm = MagicMock()
    ai.llm.chat.return_value = "LLM REPLY"
    ai.ha_client = None
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False, ha_default_agent_id=None)
    ai._load_history = lambda tid: []
    ai._save_history = lambda tid: None
    ai.current_persona = types.SimpleNamespace(
        name="Silver", persona_voice=None, language="English",
        psyche=None, memories=None, back_ground="bg", house_words=[],
        skills=["show_pip"],
        triggers=[Trigger(on={"phrase": "show the front door"},
                          do={"skill": "show_pip", "params": {"url": "http://x/stream", "kind": "live"}})],
    )
    return ai


def test_phrase_trigger_short_circuits_llm():
    ai = _make_chat_ai()
    out = ai.chat("show the front door")
    ai.llm.chat.assert_not_called()                       # conversation skipped
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )
    assert out == ""


def test_non_trigger_input_falls_through_to_llm():
    ai = _make_chat_ai()
    out = ai.chat("how are you")
    ai.llm.chat.assert_called()                           # normal conversation
    assert out == "LLM REPLY"
