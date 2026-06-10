import sys
import types
from unittest.mock import MagicMock

# Stub out unavailable native deps so PlayAIdes can be imported without
# the full Docker environment.
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models"):  # native deps only; incarnation_server/ha_client are real (mocking them in sys.modules leaks into integration tests)
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from persona import Trigger
from skills.registry import SkillRegistry
from skills.pip import ShowPipSkill


def _make_ai():
    from playAIdes import PlayAIdes
    from incarnation_server import WebSocketDisplayChannel
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.incarnation_server = MagicMock()
    ai.display = WebSocketDisplayChannel(ai.incarnation_server)
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
    from backend.services.conversation import ConversationService
    ai = _make_ai()
    ai.llm = MagicMock()
    ai.llm.chat.return_value = "LLM REPLY"
    # ConversationService calls chat_stream; route it through chat so
    # existing ai.llm.chat.assert_called() assertions still hold.
    ai.llm.chat_stream.side_effect = lambda msgs, system_prompt=None: [
        ai.llm.chat(msgs, system_prompt=system_prompt)
    ]
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
    ai.conversation = ConversationService(
        get_persona=lambda pid: ai.current_persona,
        history_load=ai._load_history,
        history_save=ai._save_history,
        dispatch=ai._dispatch_skill,
        llm=ai.llm,
        speak=ai.speak_as_persona,
        ha=None,
        ha_default_agent_id=None,
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
