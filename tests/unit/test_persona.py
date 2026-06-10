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
        assert Voice(voice=None).is_voice_valid() is False

    def test_is_voice_valid_true_when_uuid(self):
        assert Voice(voice="abc-123").is_voice_valid() is True

    def test_instruct_optional(self):
        v = Voice(voice="x", voice_instruct=["calm", "slow"])
        assert v.voice == "x" and v.voice_instruct == ["calm", "slow"]


class TestMemories:
    def test_requires_memories(self):
        with pytest.raises(ValidationError):
            Memories()  # type: ignore[call-arg]

    def test_round_trip(self):
        m = Memories(memories="once upon a time")
        assert m.memories == "once upon a time"


def test_silver_persona_loads_with_voice_field():
    import json
    from pathlib import Path
    if not Path("personas/silver/persona.json").exists():
        pytest.skip("personas/silver/persona.json not present (private asset)")
    data = json.loads(Path("personas/silver/persona.json").read_text())
    p = Persona(**data)
    assert p.persona_voice.voice == "f89c35ba-6db3-40c3-a7ee-d6b03cf71449"


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


class TestAvatarIntroAnimation:
    def test_intro_animation_optional(self):
        """Avatar without intro_animation parses fine (backwards compat)."""
        a = Avatar(model_url="m.vrm")
        assert a.intro_animation is None

    def test_intro_animation_set(self):
        """Avatar with intro_animation set carries the string through."""
        a = Avatar(model_url="m.vrm", intro_animation="cute_greeting_twirl")
        assert a.intro_animation == "cute_greeting_twirl"

    def test_intro_animation_distinct_from_idle(self):
        """intro_animation and idle_animation can be set independently."""
        a = Avatar(
            model_url="m.vrm",
            intro_animation="wave",
            idle_animation="stand",
        )
        assert a.intro_animation == "wave"
        assert a.idle_animation == "stand"


class TestPersonaWakeAndDismiss:
    def test_wake_words_optional(self):
        """Persona without wake_words parses fine (backwards compat)."""
        p = Persona(
            name="X", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.wake_words is None

    def test_dismiss_words_optional(self):
        """Persona without dismiss_words parses fine (backwards compat)."""
        p = Persona(
            name="X", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.dismiss_words is None

    def test_is_default_defaults_to_false(self):
        """Missing is_default defaults to False, not None."""
        p = Persona(
            name="X", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.is_default is False

    def test_wake_and_dismiss_set(self):
        """List values pass through unchanged."""
        p = Persona(
            name="Silver", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
            wake_words=["hey silver", "silver", "シルバー"],
            dismiss_words=["goodnight silver", "おやすみ"],
            is_default=True,
        )
        assert p.wake_words == ["hey silver", "silver", "シルバー"]
        assert p.dismiss_words == ["goodnight silver", "おやすみ"]
        assert p.is_default is True

    def test_is_default_rejects_none(self):
        """is_default must be a real bool now (Phase 4 boot resolution
        consumes it). None should fail validation."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Persona(
                name="X", back_ground="bg", psyche=Psyche(traits=[]),
                gender="Female", language="English",
                is_default=None,
            )

    def test_ha_fields_default_to_disabled(self):
        """house_words/rephrase_ha_response/ha_agent_id all default to HA-disabled."""
        p = Persona(
            name="Test", back_ground="bg",
            psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.house_words == []
        assert p.rephrase_ha_response is False
        assert p.ha_agent_id is None

    def test_ha_fields_load_from_persona_json(self, tmp_path):
        """A persona.json with HA fields loads into the model correctly."""
        import json
        path = tmp_path / "persona.json"
        path.write_text(json.dumps({
            "name": "Silver", "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female", "language": "English",
            "house_words": ["house"],
            "rephrase_ha_response": True,
            "ha_agent_id": "conversation.openai_assist",
        }))
        p = Persona(**json.loads(path.read_text()))
        assert p.house_words == ["house"]
        assert p.rephrase_ha_response is True
        assert p.ha_agent_id == "conversation.openai_assist"


class TestAvatarSpawnAndCamera:
    def test_spawn_point_optional(self):
        """Avatar without spawn_point parses fine (backwards compat)."""
        a = Avatar(model_url="m.vrm")
        assert a.spawn_point is None

    def test_camera_target_optional(self):
        """Avatar without camera_target parses fine."""
        a = Avatar(model_url="m.vrm")
        assert a.camera_target is None

    def test_spawn_point_three_floats(self):
        a = Avatar(model_url="m.vrm", spawn_point=[0.0, 0.0, 0.0])
        assert a.spawn_point == [0.0, 0.0, 0.0]

    def test_camera_target_three_floats(self):
        a = Avatar(model_url="m.vrm", camera_target=[0.0, 1.1, 0.0])
        assert a.camera_target == [0.0, 1.1, 0.0]

    def test_spawn_point_accepts_ints(self):
        """Persona JSON often has integer literals; ensure they coerce to float-friendly."""
        a = Avatar(model_url="m.vrm", spawn_point=[0, 1, 2])
        # Pydantic v2 will coerce int → float when the field type allows it.
        assert list(a.spawn_point) == [0, 1, 2]
