"""design_voice / test_voice WS handlers call the new TTSClient surface."""
import types

from playAIdes import PlayAIdes


class _RecordingServer:
    def __init__(self):
        self.commands = []
        self.port = 8765
    def send_command(self, cmd_type, payload):
        self.commands.append((cmd_type, payload))


class _FakeTTS:
    def __init__(self):
        self.design_calls = []
        self.synth_calls = []
    def design_voice(self, name, instruct, text, gender, language):
        self.design_calls.append(dict(name=name, instruct=instruct, text=text,
                                      gender=gender, language=language))
        return "new-voice-uuid"
    def synth(self, text, voice, *, tags=""):
        self.synth_calls.append((text, voice))
        return b"RIFFwavbytes"


def _ai():
    ai = PlayAIdes.__new__(PlayAIdes)          # skip __init__
    ai.tts = _FakeTTS()
    ai.incarnation_server = _RecordingServer()
    return ai


def test_design_voice_handler_designs_and_emits():
    ai = _ai()
    ai._handle_incarnation_message(
        {"type": "design_voice",
         "payload": {"name": "Naoko", "instruct": "calm", "sample_text": "hi",
                     "gender": "female", "language": "English"}})
    assert ai.tts.design_calls[0]["name"] == "Naoko"
    assert ai.tts.design_calls[0]["text"] == "hi"           # sample_text -> text
    emitted = dict(ai.incarnation_server.commands)
    assert emitted["voice_designed"]["speaker_id"] == "new-voice-uuid"  # WS key unchanged
    assert "/api/speakers/new-voice-uuid/ref_audio" in emitted["voice_designed"]["ref_audio_url"]


def test_test_voice_handler_synths_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ai = _ai()
    ai._handle_incarnation_message(
        {"type": "test_voice",
         "payload": {"text": "hello", "speaker_id": "v-1", "language": "English"}})
    assert ai.tts.synth_calls == [("hello", "v-1")]
    emitted = dict(ai.incarnation_server.commands)
    assert "voice_tested" in emitted
    written = list((tmp_path / "incarnation/public/outputs/tts/temp").glob("*.wav"))
    assert len(written) == 1 and written[0].read_bytes() == b"RIFFwavbytes"


# ── B: _setup_voice None-guard ────────────────────────────────────────────────

def test_setup_voice_none_persona_voice_gets_new_voice():
    """_setup_voice must not crash when p.persona_voice is None; it should
    create a Voice(), call design_voice, and store the returned UUID."""
    from persona import Persona, Psyche
    ai = _ai()
    ai.args = types.SimpleNamespace(generate_voice=True)
    ai._update_persona_file = lambda p: None      # stub out file write
    p = Persona(
        name="Naoko",
        back_ground="A serene oracle.",
        psyche=Psyche(traits=["calm", "wise"]),
        gender="Female",
        language="English",
        persona_voice=None,
    )
    ai._setup_voice(p)
    assert p.persona_voice is not None
    assert p.persona_voice.voice == "new-voice-uuid"


# ── C: error-frame tests ──────────────────────────────────────────────────────

def test_design_voice_handler_emits_voice_design_failed_on_error():
    """When tts.design_voice raises, the handler must emit voice_design_failed
    with the error string (parity with test_voice's voice_test_failed frame)."""
    ai = _ai()

    class _FailTTS(_FakeTTS):
        def design_voice(self, **kwargs):
            raise RuntimeError("TTS backend unreachable")

    ai.tts = _FailTTS()
    ai._handle_incarnation_message(
        {"type": "design_voice",
         "payload": {"name": "X", "instruct": "", "sample_text": "hi",
                     "gender": "Female", "language": "English"}})
    emitted = dict(ai.incarnation_server.commands)
    assert "voice_design_failed" in emitted
    assert "TTS backend unreachable" in emitted["voice_design_failed"]["error"]


def test_test_voice_handler_emits_voice_test_failed_on_synth_error(tmp_path, monkeypatch):
    """When tts.synth raises, the handler must emit voice_test_failed."""
    monkeypatch.chdir(tmp_path)
    ai = _ai()

    class _FailTTS(_FakeTTS):
        def synth(self, text, voice, *, tags=""):
            raise RuntimeError("synth unavailable")

    ai.tts = _FailTTS()
    ai._handle_incarnation_message(
        {"type": "test_voice",
         "payload": {"text": "hi", "speaker_id": "v-1", "language": "English"}})
    emitted = dict(ai.incarnation_server.commands)
    assert "voice_test_failed" in emitted
    assert "synth unavailable" in emitted["voice_test_failed"]["error"]
