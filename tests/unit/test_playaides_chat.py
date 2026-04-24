"""Unit tests for the PlayAIdes chat flow — no network, no audio."""
from __future__ import annotations

from pathlib import Path

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM


def _make(persona_file: Path, fake_tts, *, use_voice=False, generate_voice=False):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=generate_voice,
        use_voice=use_voice,
        use_avatar=False,
        generate_avatar=False,
        llm=MockLLM(),
        tts=fake_tts,
    )
    return PlayAIdes(args)


class TestChat:
    def test_returns_mock_response_and_appends_history(
        self, persona_file, fake_tts, no_incarnation
    ):
        play = _make(persona_file, fake_tts)
        out = play.chat("hello there")
        assert "hello there" in out
        # MockLLM echoes, so response contains the user's text.
        assert play.chat_history[0] == {"role": "user", "content": "hello there"}
        assert len(play.chat_history) == 1  # only user is appended; reply isn't

    def test_no_persona_loaded_returns_sentinel(
        self, tmp_path, monkeypatch, fake_tts, no_incarnation
    ):
        # Build a PlayAIdes and then clear the persona to hit the guard path.
        import json
        monkeypatch.chdir(tmp_path)
        f = tmp_path / "p.json"
        f.write_text(json.dumps({
            "name": "T", "back_ground": "bg",
            "psyche": {"traits": []}, "gender": "Female",
        }))
        play = _make(f, fake_tts)
        play.current_persona = None
        assert play.chat("anything") == "No persona loaded."

    def test_voice_disabled_skips_tts(
        self, persona_file, fake_tts, no_incarnation
    ):
        play = _make(persona_file, fake_tts, use_voice=False)
        play.chat("hi")
        assert fake_tts.stream_calls == []
        assert fake_tts.file_calls == []

    def test_voice_enabled_calls_tts_stream(
        self, persona_file, fake_tts, no_incarnation, valid_persona_dict
    ):
        # Give the persona a valid speaker so the TTS path has an id to use.
        import json
        valid_persona_dict["persona_voice"] = {"speaker_uuid": "uuid-1"}
        persona_file.write_text(json.dumps(valid_persona_dict))
        play = _make(persona_file, fake_tts, use_voice=True)
        play.chat("hi")
        assert len(fake_tts.stream_calls) == 1
        assert fake_tts.stream_calls[0].speaker_id == "uuid-1"

    def test_system_prompt_mentions_persona_name(
        self, persona_file, fake_tts, no_incarnation, monkeypatch
    ):
        captured = {}

        class SpyLLM(MockLLM):
            def chat(self, messages, system_prompt=None):
                captured["system"] = system_prompt
                captured["messages"] = list(messages)
                return "ok"

        args = PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False, use_voice=False,
            use_avatar=False, generate_avatar=False,
            llm=SpyLLM(), tts=fake_tts,
        )
        play = PlayAIdes(args)
        play.chat("question")
        assert "TestBot" in captured["system"]
        assert captured["messages"][-1]["content"] == "question"


class TestValidateArgs:
    def test_rejects_non_personatts(self, persona_file):
        class NotTTS:
            pass
        with pytest.raises(Exception):  # pydantic wraps as ValidationError
            PlayAIdesArgs(
                persona=[str(persona_file)],
                generate_voice=False, use_voice=False,
                use_avatar=False, generate_avatar=False,
                llm=MockLLM(), tts=NotTTS(),
            )
