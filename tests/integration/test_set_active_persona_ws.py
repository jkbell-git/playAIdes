"""Integration test: set_active_persona triggers persona swap + emits
persona_changed, history_loaded, unload_model, load_model."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _seed_persona(tmp_personas_dir, pid: str, name: str = None,
                  intro_animation: str = None, model_url: str = "m.vrm"):
    pdir = tmp_personas_dir / pid
    pdir.mkdir(exist_ok=True)
    persona = {
        "name": name or pid.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {"model_url": model_url},
    }
    if intro_animation:
        persona["avatar"]["intro_animation"] = intro_animation
    (pdir / "persona.json").write_text(json.dumps(persona))


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


class TestSetActivePersonaWS:
    def test_emits_persona_changed_ok_on_swap(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin", model_url="rin.vrm")
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        changed = [(c, p) for c, p in cmds if c == "persona_changed"]
        assert len(changed) == 1
        _, payload = changed[0]
        assert payload["ok"] is True
        assert payload["persona"]["name"] == "Rin"

    def test_emits_persona_changed_error_on_unknown_id(self, play):
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "no-such-persona"},
        })
        cmds = play.incarnation_server.commands
        changed = [(c, p) for c, p in cmds if c == "persona_changed"]
        assert len(changed) == 1
        _, payload = changed[0]
        assert payload["ok"] is False
        assert "error" in payload

    def test_emits_unload_then_load_model_on_swap(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin", model_url="rin.vrm")
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        types_in_order = [c for c, _ in cmds]
        assert "unload_model" in types_in_order
        assert "load_model" in types_in_order
        # Order: unload before load.
        assert types_in_order.index("unload_model") < types_in_order.index("load_model")
        # Load carries the new persona's model_url.
        load = [(c, p) for c, p in cmds if c == "load_model"][0][1]
        assert load["url"] == "rin.vrm"

    def test_load_model_payload_carries_spawn_and_camera(self, play, tmp_personas_dir):
        """load_model payload includes the persona's spawn_point and
        camera_target so the frontend can position the VRM + camera."""
        # Seed Rin with explicit spawn + camera_target.
        rin_dir = tmp_personas_dir / "rin"
        rin_dir.mkdir(exist_ok=True)
        (rin_dir / "persona.json").write_text(json.dumps({
            "name": "Rin",
            "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female",
            "language": "English",
            "avatar": {
                "model_url": "rin.vrm",
                "spawn_point": [1.0, 0.0, -2.0],
                "camera_target": [1.0, 1.1, -2.0],
            },
        }))
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        load = [(c, p) for c, p in cmds if c == "load_model"]
        assert len(load) == 1
        _, payload = load[0]
        assert payload["url"] == "rin.vrm"
        assert payload["spawn_point"] == [1.0, 0.0, -2.0]
        assert payload["camera_target"] == [1.0, 1.1, -2.0]

    def test_no_unload_when_same_persona(self, play):
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "testbot"},   # same as initial
        })
        cmds = play.incarnation_server.commands
        # Idempotent same-persona swap: no unload_model emitted.
        assert "unload_model" not in [c for c, _ in cmds]

    def test_emits_history_loaded(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        history_file = tmp_personas_dir / "rin" / "chat_history.json"
        history_file.write_text(json.dumps([
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "earlier reply"},
        ]))
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        hist = [(c, p) for c, p in cmds if c == "history_loaded"]
        assert len(hist) == 1
        _, payload = hist[0]
        assert payload["persona_id"] == "rin"
        assert payload["history"] == [
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "earlier reply"},
        ]

    def test_user_input_uses_persona_id_from_payload(self, play, tmp_personas_dir):
        """user_input now carries persona_id; chat() routes to that history."""
        _seed_persona(tmp_personas_dir, "rin")
        play.set_persona("rin")
        play._handle_incarnation_message({
            "type": "user_input",
            "payload": {"text": "hi rin", "persona_id": "rin"},
        })
        # The MockLLM reply should land in rin's history.
        assert "rin" in play.chat_histories
        rin_hist = play.chat_histories["rin"]
        assert any(m.get("content") == "hi rin" for m in rin_hist)

    def test_chat_with_no_voice_config_does_not_crash(self, tmp_personas_dir, fake_tts, no_incarnation):
        """A persona without persona_voice should not crash chat() when
        use_voice=True; the lip-sync emit is gracefully skipped."""
        # Seed a persona with no persona_voice block.
        pdir = tmp_personas_dir / "voiceless"
        pdir.mkdir(exist_ok=True)
        (pdir / "persona.json").write_text(json.dumps({
            "name": "Voiceless",
            "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female",
            "language": "English",
            "avatar": {"model_url": "x.vrm"},
            # NB: no persona_voice key
        }))
        args = PlayAIdesArgs(
            persona=[str(pdir / "persona.json")],
            generate_voice=False,
            use_voice=True,            # voice path enabled
            use_avatar=True,
            generate_avatar=False,
            llm=MockLLM(), tts=fake_tts,
        )
        play = PlayAIdes(args)
        # Must not raise.
        play.chat("hi")
        cmds = play.incarnation_server.commands
        # assistant_message still flows; start_lip_sync is gracefully skipped.
        assert any(c == "assistant_message" for c, _ in cmds)
        assert not any(c == "start_lip_sync" for c, _ in cmds)

    def test_replays_intro_on_same_persona_resummon(self, play, tmp_personas_dir):
        """Same-persona set_active_persona should fire play_animation for
        the intro_animation so re-summon plays the greeting."""
        # `set_persona` is idempotent for same-id calls (returns the cached
        # in-memory persona without re-reading from disk), so we mutate the
        # active persona's avatar.intro_animation directly. In production
        # this field is set when the persona is first loaded.
        from persona import Avatar
        active_id = play.current_persona.name.strip().lower().replace(" ", "_")
        if play.current_persona.avatar is None:
            play.current_persona.avatar = Avatar(
                model_url="m.vrm", intro_animation="wave",
            )
        else:
            play.current_persona.avatar.intro_animation = "wave"

        # Clear command log to focus on what the resummon emits.
        play.incarnation_server.commands.clear()

        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": active_id},
        })

        cmds = play.incarnation_server.commands
        plays = [(c, p) for c, p in cmds if c == "play_animation"]
        assert len(plays) == 1
        assert plays[0][1]["name"] == "wave"
        assert plays[0][1]["loop"] is False
