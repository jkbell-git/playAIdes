import types as _types
from unittest.mock import MagicMock


def _make_ai():
    from playAIdes import PlayAIdes
    from incarnation_server import WebSocketDisplayChannel
    ai = PlayAIdes.__new__(PlayAIdes)            # skip __init__
    ai.incarnation_server = MagicMock()
    ai.display = WebSocketDisplayChannel(ai.incarnation_server)
    ai.args = _types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.tts = MagicMock()
    ai.current_persona = _types.SimpleNamespace(
        persona_voice=_types.SimpleNamespace(voice="uuid-1"),
        name="silver",
        language="English",
    )
    return ai


def test_speak_broadcasts_assistant_message():
    ai = _make_ai()
    ai.speak_as_persona("silver", "hello there")
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "assistant_message", {"text": "hello there", "persona_id": "silver"},
    )


def test_speak_sends_lip_sync_url_with_voice_when_avatar_on():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = True
    ai.speak_as_persona("silver", "hi")
    payloads = [c.args[2] for c in ai.incarnation_server.broadcast_to_persona.call_args_list
                if c.args[1] == "start_lip_sync"]
    assert payloads, "expected a start_lip_sync command"
    assert "&voice=uuid-1" in payloads[0]["url"]
    assert "speaker_id=" not in payloads[0]["url"]


def test_speak_is_silent_without_avatar():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = False                 # no display sink → no audio (CLI path removed)
    ai.speak_as_persona("silver", "hi")
    cmds = [c.args[1] for c in ai.incarnation_server.broadcast_to_persona.call_args_list]
    assert "start_lip_sync" not in cmds
    ai.tts.synth.assert_not_called()
