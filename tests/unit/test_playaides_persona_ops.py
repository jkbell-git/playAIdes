"""Unit tests for PlayAIdes persona CRUD operations.

These tests exercise the file-system helpers (``list_personas``,
``get_persona_by_id``, ``create_persona``, ``update_persona``,
``_load_persona_from_file``) in isolation — no LLM, no TTS, no WebSocket.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from playAIdes import PersonaLoadError, PlayAIdes, PlayAIdesArgs


def _args(persona_files, **overrides):
    """Build a PlayAIdesArgs with everything off unless overridden."""
    from model_interfaces import MockLLM
    defaults = dict(
        persona=persona_files,
        generate_voice=False,
        use_voice=False,
        use_avatar=False,
        generate_avatar=False,
        llm=MockLLM(),
        tts=None,
    )
    defaults.update(overrides)
    return PlayAIdesArgs(**defaults)


@pytest.fixture
def play(tmp_personas_dir: Path, persona_file: Path, fake_tts, no_incarnation) -> PlayAIdes:
    """PlayAIdes instance rooted at a tmp personas dir, no avatar, no voice."""
    return PlayAIdes(_args([str(persona_file)], tts=fake_tts))


class TestLoadPersonaFromFile:
    def test_loads_valid_persona(self, play: PlayAIdes):
        assert play.current_persona is not None
        assert play.current_persona.name == "TestBot"

    def test_missing_file_raises(self, tmp_path, fake_tts, no_incarnation):
        bogus = tmp_path / "does_not_exist.json"
        with pytest.raises(PersonaLoadError, match="not found"):
            PlayAIdes(_args([str(bogus)], tts=fake_tts))

    def test_bad_json_raises(self, tmp_path, fake_tts, no_incarnation):
        f = tmp_path / "bad.json"
        f.write_text("{not json")
        with pytest.raises(PersonaLoadError, match="Invalid JSON"):
            PlayAIdes(_args([str(f)], tts=fake_tts))

    def test_schema_violation_raises(self, tmp_path, fake_tts, no_incarnation):
        f = tmp_path / "incomplete.json"
        f.write_text(json.dumps({"name": "Missing"}))  # missing required fields
        with pytest.raises(PersonaLoadError, match="validation"):
            PlayAIdes(_args([str(f)], tts=fake_tts))


class TestListPersonas:
    def test_lists_seeded_persona(self, play: PlayAIdes):
        personas = play.list_personas()
        assert len(personas) == 1
        assert personas[0]["id"] == "testbot"
        assert personas[0]["name"] == "TestBot"

    def test_ignores_dirs_without_persona_json(self, play: PlayAIdes, tmp_personas_dir: Path):
        (tmp_personas_dir / "empty_dir").mkdir()
        (tmp_personas_dir / "stray.txt").write_text("hi")
        assert len(play.list_personas()) == 1

    def test_ignores_malformed_json(self, play: PlayAIdes, tmp_personas_dir: Path):
        broken = tmp_personas_dir / "broken"
        broken.mkdir()
        (broken / "persona.json").write_text("{bad")
        # Should still return the one good persona without raising.
        result = play.list_personas()
        assert len(result) == 1
        assert result[0]["id"] == "testbot"

    def test_creates_personas_dir_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_tts, no_incarnation
    ):
        # Start with NO personas dir at all.
        monkeypatch.chdir(tmp_path)
        persona_file = tmp_path / "seed.json"
        persona_file.write_text(json.dumps({
            "name": "T", "back_ground": "bg",
            "psyche": {"traits": []}, "gender": "Female",
        }))
        p = PlayAIdes(_args([str(persona_file)], tts=fake_tts))
        assert p.list_personas() == []
        assert (tmp_path / "personas").is_dir()


class TestGetPersonaById:
    def test_returns_dict_for_existing(self, play: PlayAIdes):
        got = play.get_persona_by_id("testbot")
        assert got is not None
        assert got["id"] == "testbot"
        assert got["name"] == "TestBot"

    def test_returns_none_for_missing(self, play: PlayAIdes):
        assert play.get_persona_by_id("does-not-exist") is None


class TestCreatePersona:
    def test_creates_dir_and_file(self, play: PlayAIdes, tmp_personas_dir: Path):
        out = play.create_persona("New Friend", "A brand new persona.")
        assert out["id"] == "new_friend"
        assert out["name"] == "New Friend"
        assert out["back_ground"] == "A brand new persona."
        p_file = tmp_personas_dir / "new_friend" / "persona.json"
        assert p_file.exists()
        on_disk = json.loads(p_file.read_text())
        assert on_disk["name"] == "New Friend"

    def test_id_slugification(self, play: PlayAIdes):
        out = play.create_persona("   Two  Words  ", "x")
        # leading/trailing whitespace stripped, internal spaces → underscores
        assert out["id"].startswith("two")
        assert " " not in out["id"]


class TestUpdatePersona:
    def test_updates_existing(self, play: PlayAIdes, tmp_personas_dir: Path):
        data = play.get_persona_by_id("testbot")
        assert data is not None
        data["back_ground"] = "edited"
        out = play.update_persona("testbot", data)
        assert out["back_ground"] == "edited"
        on_disk = json.loads((tmp_personas_dir / "testbot" / "persona.json").read_text())
        assert on_disk["back_ground"] == "edited"

    def test_strips_id_from_payload(self, play: PlayAIdes, tmp_personas_dir: Path):
        play.update_persona("testbot", {"id": "testbot", "name": "X", "back_ground": "y",
                                         "psyche": {"traits": []}, "gender": "Female"})
        on_disk = json.loads((tmp_personas_dir / "testbot" / "persona.json").read_text())
        assert "id" not in on_disk

    def test_creates_dir_if_missing(self, play: PlayAIdes, tmp_personas_dir: Path):
        play.update_persona("fresh", {"name": "Fresh", "back_ground": "b",
                                        "psyche": {"traits": []}, "gender": "Female"})
        assert (tmp_personas_dir / "fresh" / "persona.json").exists()


class TestDeletePersona:
    def test_deletes_existing(self, play: PlayAIdes, tmp_personas_dir: Path):
        # Create a separate persona so we don't touch the active one
        play.create_persona("Doomed", "to be deleted")
        target_dir = tmp_personas_dir / "doomed"
        assert target_dir.exists()
        assert play.delete_persona("doomed") is True
        assert not target_dir.exists()

    def test_returns_false_for_missing(self, play: PlayAIdes):
        assert play.delete_persona("never_existed") is False

    def test_refuses_active_persona(self, play: PlayAIdes, tmp_personas_dir: Path):
        # The fixture loads "testbot" as the active persona — must be protected.
        assert play.delete_persona("testbot") is False
        assert (tmp_personas_dir / "testbot" / "persona.json").exists()

    @pytest.mark.parametrize("bad_id", ["", "..", ".", "../etc", "foo/bar", "foo\\bar"])
    def test_rejects_path_traversal(self, play: PlayAIdes, bad_id):
        assert play.delete_persona(bad_id) is False
