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
