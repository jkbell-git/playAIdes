"""Unit tests for the PlayAIdes chat flow — no network, no audio."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Stub out unavailable native deps so PlayAIdes can be imported without
# the full Docker environment.
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM


def _make(persona_file: Path, fake_tts, *, use_voice=False, generate_voice=False, use_avatar=False):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=generate_voice,
        use_voice=use_voice,
        use_avatar=use_avatar,
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
        # Both user and assistant turns are appended to the per-persona history.
        assert len(play.chat_history) == 2
        assert play.chat_history[1]["role"] == "assistant"

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
        # With use_voice=False, speak_as_persona returns early — no start_lip_sync
        # frame should be pushed.  Build with use_avatar=True so the stub
        # incarnation_server is wired and commands can be inspected.
        play = _make(persona_file, fake_tts, use_voice=False, use_avatar=True)
        play.chat("hi")
        cmds = [cmd for cmd, _payload in play.incarnation_server.commands]
        assert "start_lip_sync" not in cmds

    def test_voice_enabled_calls_tts_stream(
        self, persona_file, fake_tts, no_incarnation, valid_persona_dict
    ):
        # New design: the browser/avatar is the only audio sink.  With
        # use_avatar=True and a valid voice, speak_as_persona pushes a
        # start_lip_sync frame whose URL carries &voice=uuid-1 (no direct synth).
        import json
        valid_persona_dict["persona_voice"] = {"voice": "uuid-1"}
        persona_file.write_text(json.dumps(valid_persona_dict))
        play = _make(persona_file, fake_tts, use_voice=True, use_avatar=True)
        play.chat("hi")
        lip_sync_cmds = [
            payload for cmd, payload in play.incarnation_server.commands
            if cmd == "start_lip_sync"
        ]
        assert lip_sync_cmds, "expected at least one start_lip_sync command"
        assert "&voice=uuid-1" in lip_sync_cmds[0]["url"]

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


class TestAssistantMessageBroadcast:
    """When use_avatar is on, chat() emits an assistant_message WS command
    carrying the reply text, before any audio is dispatched. This drives
    the new viewer's subtitle band even when the terminal is the input."""

    def test_emits_assistant_message_with_reply_text(
        self, persona_file, fake_tts, no_incarnation
    ):
        # use_avatar=True so an IncarnationServer (stub) is wired
        args = PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False,
            use_voice=False,
            use_avatar=True,
            generate_avatar=False,
            llm=MockLLM(),
            tts=fake_tts,
        )
        play = PlayAIdes(args)
        reply = play.chat("hello there")
        cmds = play.incarnation_server.commands
        assistant_messages = [
            (cmd, payload) for cmd, payload in cmds if cmd == "assistant_message"
        ]
        assert len(assistant_messages) == 1
        _, payload = assistant_messages[0]
        assert payload["text"] == reply

    def test_no_message_when_avatar_disabled(
        self, persona_file, fake_tts, no_incarnation
    ):
        # use_avatar=False → no incarnation_server → nothing to emit to
        args = PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False,
            use_voice=False,
            use_avatar=False,
            generate_avatar=False,
            llm=MockLLM(),
            tts=fake_tts,
        )
        play = PlayAIdes(args)
        # incarnation_server is None when use_avatar=False
        assert play.incarnation_server is None
        # Should not raise
        play.chat("hi")
