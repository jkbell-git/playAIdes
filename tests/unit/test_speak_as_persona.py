import sys
import types as _types
from unittest.mock import MagicMock

# Stub out unavailable native deps so PlayAIdes can be imported without
# the full Docker environment (same pattern used by test_chat_skill_dispatch.py).
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models", "incarnation_server", "ha_client"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _make_ai():
    # Build a PlayAIdes-like object with just the attributes speak_as_persona needs.
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)            # skip __init__
    ai.incarnation_server = MagicMock()
    ai.args = _types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.tts = MagicMock()
    # current_persona with a valid voice
    ai.current_persona = _types.SimpleNamespace(
        persona_voice=_types.SimpleNamespace(speaker_uuid="uuid-1"),
        language="English",
    )
    return ai


def test_speak_broadcasts_assistant_message():
    ai = _make_ai()
    ai.speak_as_persona("silver", "hello there")
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "assistant_message", {"text": "hello there", "persona_id": "silver"},
    )


def test_speak_sends_lip_sync_when_voice_and_avatar_on():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = True
    ai.speak_as_persona("silver", "hi")
    calls = [c.args[1] for c in ai.incarnation_server.broadcast_to_persona.call_args_list]
    assert "start_lip_sync" in calls


def test_speak_calls_tts_when_no_avatar():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = False   # server-side TTS path
    ai.speak_as_persona("silver", "hi")
    ai.tts.generate_speech_stream.assert_called_once()
