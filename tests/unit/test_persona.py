"""Unit tests for persona.py Pydantic models."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from persona import Avatar, Memories, Persona, Psyche, Voice


class TestPsyche:
    def test_minimal(self):
        p = Psyche(traits=["kind"])
        assert p.traits == ["kind"]

    def test_empty_traits_ok(self):
        # Empty list is valid — a persona with no declared traits is fine.
        assert Psyche(traits=[]).traits == []

    def test_traits_required(self):
        with pytest.raises(ValidationError):
            Psyche()  # type: ignore[call-arg]


class TestAvatar:
    def test_minimal(self):
        a = Avatar(model_url="/path/to/model.vrm")
        assert a.model_url.endswith(".vrm")
        assert a.idle_animation == "idle"  # default

    def test_full(self):
        a = Avatar(
            model_url="m.vrm",
            animations_url="/anims",
            idle_animation="stand",
            animation_list=["wave", "bow"],
            background_url="/bg.png",
        )
        assert a.animation_list == ["wave", "bow"]

    def test_model_url_required(self):
        with pytest.raises(ValidationError):
            Avatar()  # type: ignore[call-arg]


class TestVoice:
    def test_is_voice_valid_false_when_no_uuid(self):
        assert Voice().is_voice_valid() is False

    def test_is_voice_valid_false_on_none_explicit(self):
        assert Voice(speaker_uuid=None).is_voice_valid() is False

    def test_is_voice_valid_true_when_uuid(self):
        assert Voice(speaker_uuid="abc-123").is_voice_valid() is True

    def test_instruct_optional(self):
        v = Voice(speaker_uuid="x", voice_instruct=["calm", "slow"])
        assert v.voice_instruct == ["calm", "slow"]


class TestMemories:
    def test_requires_memories(self):
        with pytest.raises(ValidationError):
            Memories()  # type: ignore[call-arg]

    def test_round_trip(self):
        m = Memories(memories="once upon a time")
        assert m.memories == "once upon a time"


class TestPersona:
    def _base(self, **extra):
        data = {
            "name": "Alice",
            "back_ground": "A test persona.",
            "psyche": {"traits": ["curious"]},
            "gender": "Female",
        }
        data.update(extra)
        return data

    def test_minimal(self):
        p = Persona(**self._base())
        assert p.name == "Alice"
        assert p.language == "English"  # default
        assert p.avatar is None

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            Persona(name="NoBack")  # type: ignore[call-arg]

    def test_json_round_trip(self, tmp_path: Path, valid_persona_dict: dict):
        f = tmp_path / "p.json"
        f.write_text(json.dumps(valid_persona_dict))
        p = Persona(**json.loads(f.read_text()))
        assert p.name == valid_persona_dict["name"]
        # And the dump re-validates
        re = Persona(**p.model_dump())
        assert re.name == p.name

    def test_handy_json_fixture_parses(self):
        """The repo's personas/handy.json is the canonical example — must parse."""
        path = Path(__file__).resolve().parents[2] / "personas" / "handy.json"
        data = json.loads(path.read_text())
        p = Persona(**data)
        assert p.name == "Handy"
