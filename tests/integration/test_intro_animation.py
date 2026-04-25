"""Integration tests: intro_animation drives the post-load greeting clip."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _persona_dict(intro=None, idle="idle"):
    return {
        "name": "Test",
        "back_ground": "test",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {
            "model_url": "m.vrm",
            "idle_animation": idle,
            **({"intro_animation": intro} if intro else {}),
        },
    }


def _seed(tmp_personas_dir, persona):
    pdir = tmp_personas_dir / "test"
    pdir.mkdir(exist_ok=True)
    (pdir / "persona.json").write_text(json.dumps(persona))
    return pdir / "persona.json"


@pytest.fixture
def args_factory(tmp_personas_dir, fake_tts, no_incarnation):
    def make(persona_file):
        return PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False, use_voice=False,
            use_avatar=True, generate_avatar=False,
            llm=MockLLM(), tts=fake_tts,
        )
    return make


class TestIntroAnimation:
    def test_intro_animation_used_when_set(self, tmp_personas_dir, args_factory):
        """When intro_animation is set, it's the first thing played after model load."""
        f = _seed(tmp_personas_dir, _persona_dict(intro="wave_hello"))
        play = PlayAIdes(args_factory(f))
        # Simulate the frontend reporting all animations finished loading.
        # (load_default_animations populates expected_animations; we drain it.)
        play.expected_animations.clear()
        # Trigger the post-load greeting path
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "animation_loaded", "name": "wave_hello"},
        })
        # The stub IncarnationServer captures every send_command call
        cmds = play.incarnation_server.commands
        names_played = [
            payload.get("name") for cmd, payload in cmds if cmd == "play_animation"
        ]
        assert "wave_hello" in names_played, f"got: {names_played}"

    def test_falls_back_to_idle_when_intro_unset(self, tmp_personas_dir, args_factory):
        """No intro_animation → first play_animation is the idle clip."""
        f = _seed(tmp_personas_dir, _persona_dict(intro=None, idle="stand"))
        play = PlayAIdes(args_factory(f))
        play.expected_animations.clear()
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "animation_loaded", "name": "stand"},
        })
        cmds = play.incarnation_server.commands
        names = [p.get("name") for c, p in cmds if c == "play_animation"]
        assert "stand" in names

    def test_falls_back_to_default_when_default_is_loaded(self, tmp_personas_dir, args_factory):
        """When intro + idle are both None AND DEFAULT_IDLE_ANIMATION is in
        the loaded set, fall back to it."""
        from playAIdes import DEFAULT_IDLE_ANIMATION
        avatar = {"model_url": "m.vrm", "idle_animation": None}
        persona = {
            "name": "Test", "back_ground": "test",
            "psyche": {"traits": []}, "gender": "Female",
            "language": "English", "avatar": avatar,
        }
        f = _seed(tmp_personas_dir, persona)
        play = PlayAIdes(args_factory(f))
        play.expected_animations.clear()
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "animation_loaded", "name": DEFAULT_IDLE_ANIMATION},
        })
        cmds = play.incarnation_server.commands
        play_anims = [p for c, p in cmds if c == "play_animation"]
        assert len(play_anims) == 1
        assert play_anims[0]["name"] == DEFAULT_IDLE_ANIMATION

    def test_falls_back_to_first_loaded_when_default_missing(self, tmp_personas_dir, args_factory):
        """Pack uses generic names like VRMA_01.vrma — default model_pose
        isn't in the loaded set. Resolver should pick the first alphabetical
        loaded clip rather than send name=DEFAULT (which would T-pose)."""
        avatar = {"model_url": "m.vrm", "idle_animation": None}
        persona = {
            "name": "Test", "back_ground": "test",
            "psyche": {"traits": []}, "gender": "Female",
            "language": "English", "avatar": avatar,
        }
        f = _seed(tmp_personas_dir, persona)
        play = PlayAIdes(args_factory(f))
        # Seed expected_animations so the play branch only fires on the LAST
        # animation_loaded (mirrors how load_default_animations populates it).
        play.expected_animations = {"VRMA_07", "VRMA_03"}
        for name in ("VRMA_07", "VRMA_03"):
            play._handle_incarnation_message({
                "type": "status",
                "payload": {"state": "animation_loaded", "name": name},
            })
        cmds = play.incarnation_server.commands
        play_anims = [p for c, p in cmds if c == "play_animation"]
        assert len(play_anims) == 1
        # First alphabetical → "VRMA_03"
        assert play_anims[0]["name"] == "VRMA_03"

    def test_unknown_intro_falls_back_to_loaded_clip(self, tmp_personas_dir, args_factory):
        """Persona configures intro_animation='wave_hello' but the loaded
        pack doesn't include it. Resolver should fall through to default
        or first-loaded, not send name='wave_hello' (which would T-pose)."""
        f = _seed(tmp_personas_dir, _persona_dict(intro="wave_hello"))
        play = PlayAIdes(args_factory(f))
        play.expected_animations.clear()
        # Persona wanted "wave_hello" but only "VRMA_01" is loaded.
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "animation_loaded", "name": "VRMA_01"},
        })
        cmds = play.incarnation_server.commands
        play_anims = [p for c, p in cmds if c == "play_animation"]
        assert len(play_anims) == 1
        assert play_anims[0]["name"] == "VRMA_01"
        # Loop because we did NOT play the configured intro — we fell back.
        assert play_anims[0]["loop"] is True

    def test_loaded_animations_tracks_each_clip(self, tmp_personas_dir, args_factory):
        """`loaded_animations` accumulates every animation_loaded event,
        even if the name wasn't in expected_animations (e.g. tests that
        skip the load_default_animations enumeration)."""
        f = _seed(tmp_personas_dir, _persona_dict(intro="x"))
        play = PlayAIdes(args_factory(f))
        play.expected_animations.clear()
        for name in ("a", "b", "c"):
            play._handle_incarnation_message({
                "type": "status",
                "payload": {"state": "animation_loaded", "name": name},
            })
        assert play.loaded_animations == {"a", "b", "c"}
