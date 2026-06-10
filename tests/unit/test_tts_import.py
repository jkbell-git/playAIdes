"""Proves playAIdes imports with no voicebox_client stub — the migration keystone."""


def test_playaides_imports_without_voicebox_stub():
    import playAIdes  # must NOT raise ModuleNotFoundError
    assert hasattr(playAIdes, "PlayAIdes")


def test_args_accepts_duck_typed_tts():
    from playAIdes import PlayAIdesArgs

    class FakeTTS:
        def synth(self, text, voice, *, tags=""):
            return b""
        def design_voice(self, name, instruct, text, gender, language):
            return "v"

    fake = FakeTTS()
    args = PlayAIdesArgs(persona=["x"], generate_voice=False, use_voice=False,
                         use_avatar=False, generate_avatar=False, tts=fake)
    assert args.tts is fake


def test_args_rejects_non_tts_object():
    import pytest
    from pydantic import ValidationError
    from playAIdes import PlayAIdesArgs

    with pytest.raises((ValidationError, ValueError)):
        PlayAIdesArgs(persona=["x"], generate_voice=False, use_voice=False,
                      use_avatar=False, generate_avatar=False, tts=object())
