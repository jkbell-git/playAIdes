"""Unit tests for PlayAIdes.set_persona — runtime persona swap."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs, PersonaLoadError
from model_interfaces import MockLLM


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


def _seed_persona(tmp_personas_dir, pid: str, name: str = None):
    pdir = tmp_personas_dir / pid
    pdir.mkdir(exist_ok=True)
    (pdir / "persona.json").write_text(json.dumps({
        "name": name or pid.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
    }))
    return pid


class TestSetPersona:
    def test_swaps_to_new_persona(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        result = play.set_persona("rin")
        assert result is not None
        assert result.name == "Rin"
        assert play.current_persona is result

    def test_idempotent_when_same_id(self, play):
        # `persona_file` fixture seeds "testbot" — the active persona.
        original = play.current_persona
        result = play.set_persona("testbot")
        assert result is original
        assert play.current_persona is original

    def test_refuses_unknown_id(self, play):
        with pytest.raises(PersonaLoadError):
            play.set_persona("nobody-with-this-name")

    def test_refuses_path_traversal(self, play):
        for bad_id in ["../etc", "..", ".", "foo/bar", "foo\\bar", ""]:
            with pytest.raises((PersonaLoadError, ValueError)):
                play.set_persona(bad_id)

    def test_loads_history_on_swap(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        history_file = tmp_personas_dir / "rin" / "chat_history.json"
        history_file.write_text(json.dumps([
            {"role": "user", "content": "old hello"},
        ]))
        play.set_persona("rin")
        assert "rin" in play.chat_histories
        assert play.chat_histories["rin"] == [
            {"role": "user", "content": "old hello"},
        ]

    def test_does_not_reset_existing_history(self, play, tmp_personas_dir):
        # Existing in-memory history for the active persona must not be cleared.
        play.chat_histories["testbot"] = [
            {"role": "user", "content": "earlier"},
        ]
        _seed_persona(tmp_personas_dir, "rin")
        play.set_persona("rin")  # swap away
        assert play.chat_histories["testbot"] == [
            {"role": "user", "content": "earlier"},
        ]


class TestChatPerPersonaRouting:
    def test_chat_appends_to_active_persona_history(self, play):
        play.chat("hello there")
        active_id = play.current_persona.name.strip().lower().replace(" ", "_")
        assert active_id in play.chat_histories
        history = play.chat_histories[active_id]
        # MockLLM gives a deterministic reply; expect both turns appended.
        roles = [m["role"] for m in history]
        assert "user" in roles
        assert "assistant" in roles

    def test_chat_with_explicit_persona_id_routes_there(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        play.set_persona("rin")
        # MockLLM will respond. The "rin" history should grow.
        play.chat("hi rin", persona_id="rin")
        assert any("rin" == k for k in play.chat_histories.keys())
        rin_history = play.chat_histories["rin"]
        assert len(rin_history) >= 2  # user + assistant

    def test_chat_persists_after_each_turn(self, play, tmp_personas_dir):
        play.chat("first thing")
        active_id = play.current_persona.name.strip().lower().replace(" ", "_")
        history_file = tmp_personas_dir / active_id / "chat_history.json"
        assert history_file.exists()
        on_disk = json.loads(history_file.read_text())
        assert on_disk == play.chat_histories[active_id]
