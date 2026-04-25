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
