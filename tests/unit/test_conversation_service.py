from persona import Persona
from backend.services.conversation import ConversationService, TurnEvent

_PERSONA = {
    "name": "TestBot",
    "back_ground": "A persona used only in tests.",
    "psyche": {"traits": ["calm", "deterministic"]},
    "gender": "Female",
    "language": "English",
}


def _persona(**overrides):
    return Persona(**{**_PERSONA, **overrides})


def _service(persona, *, llm=None, ha=None, speak=None, dispatch=None, history=None):
    hist = history if history is not None else {}
    spoken = []
    dispatched = []
    svc = ConversationService(
        get_persona=lambda pid: persona,
        history_load=lambda pid: hist.setdefault(pid, []),
        history_save=lambda pid: None,
        dispatch=dispatch or (lambda *a: dispatched.append(a)),
        llm=llm,
        ha=ha,
        speak=speak or (lambda tid, text: spoken.append((tid, text))),
        ha_default_agent_id=None,
        history_cap=80,
    )
    svc._spoken = spoken
    svc._dispatched = dispatched
    return svc


def test_phrase_trigger_dispatches_and_yields_silent_single_delta():
    persona = _persona(
        triggers=[{"on": {"phrase": "show camera"},
                   "do": {"skill": "show_pip", "params": {"source": "cam.1"}}}],
        skills=["show_pip"],
    )
    svc = _service(persona)
    events = list(svc.run_turn("testbot", "show camera now"))

    types = [e.type for e in events]
    assert types == ["reply_started", "reply_delta", "reply_done"]
    assert events[1].payload["text"] == ""
    assert events[2].payload["text"] == ""
    assert svc._dispatched == [("testbot", "show_pip", {"source": "cam.1"})]
    assert svc._spoken == []
