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


def test_no_persona_yields_error_single_delta():
    svc = ConversationService(
        get_persona=lambda pid: None,
        history_load=lambda pid: [],
        history_save=lambda pid: None,
        dispatch=lambda *a: None,
        llm=None,
        speak=lambda tid, text: None,
        ha=None,
    )
    events = list(svc.run_turn("nobody", "hi"))
    assert [e.type for e in events] == ["reply_started", "reply_delta", "reply_done"]
    assert events[-1].payload["text"] == "No persona loaded."


class _StreamLLM:
    def __init__(self, chunks):
        self._chunks = list(chunks)
    def chat(self, messages, system_prompt=None):
        return "".join(self._chunks)
    def chat_stream(self, messages, system_prompt=None):
        for c in self._chunks:
            yield c


def test_llm_path_streams_deltas_speaks_and_persists():
    persona = _persona(persona_voice={"speaker_uuid": "v-1"})
    history = {}
    svc = _service(persona, llm=_StreamLLM(["Hel", "lo"]), history=history)
    events = list(svc.run_turn("testbot", "hi"))

    assert [e.type for e in events] == [
        "reply_started", "reply_delta", "reply_delta", "reply_done",
    ]
    assert [e.payload["text"] for e in events[1:3]] == ["Hel", "lo"]
    assert events[-1].payload["text"] == "Hello"
    assert svc._spoken == [("testbot", "Hello")]
    assert history["testbot"][-2:] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello"},
    ]


def test_house_word_delegates_to_ha_single_delta(mock_ha_client):
    persona = _persona(house_words=["house"])
    ha = mock_ha_client
    ha.script(speech_text="Lights on.", conversation_id="c-1")
    svc = _service(persona, llm=_StreamLLM(["unused"]), ha=ha)
    events = list(svc.run_turn("testbot", "house turn on the lights"))

    assert [e.type for e in events] == ["reply_started", "reply_delta", "reply_done"]
    assert events[1].payload["text"] == "Lights on."
    assert ha.calls[0]["text"] == "turn on the lights"
    assert svc._spoken == [("testbot", "Lights on.")]


def test_house_word_with_no_residual_short_circuits(mock_ha_client):
    persona = _persona(house_words=["house"])
    ha = mock_ha_client
    svc = _service(persona, llm=_StreamLLM(["unused"]), ha=ha)
    events = list(svc.run_turn("testbot", "house"))
    assert events[1].payload["text"] == "What about the house?"
    assert ha.calls == []


def test_house_word_rephrase_uses_llm(mock_ha_client):
    persona = _persona(house_words=["house"], rephrase_ha_response=True)
    ha = mock_ha_client
    ha.script(speech_text="Lights on.", success=True)

    class _RephraseLLM:
        def chat(self, messages, system_prompt=None):
            return "The lights are now on, darling."
        def chat_stream(self, messages, system_prompt=None):
            yield "unused"

    svc = _service(persona, llm=_RephraseLLM(), ha=ha)
    events = list(svc.run_turn("testbot", "house turn on the lights"))
    assert events[1].payload["text"] == "The lights are now on, darling."
    assert svc._spoken == [("testbot", "The lights are now on, darling.")]
