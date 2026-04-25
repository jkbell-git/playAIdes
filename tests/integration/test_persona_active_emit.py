"""Integration test: server emits `persona_active` to the browser when the
avatar reports model_loaded, carrying name + wake_words + dismiss_words."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _persona_dict(wake=None, dismiss=None):
    return {
        "name": "Silver",
        "back_ground": "test",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {"model_url": "m.vrm"},
        **({"wake_words": wake} if wake is not None else {}),
        **({"dismiss_words": dismiss} if dismiss is not None else {}),
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


class TestPersonaActiveEmit:
    def test_emits_persona_active_on_model_loaded(self, tmp_personas_dir, args_factory):
        """A model_loaded status triggers a persona_active broadcast carrying
        the matching config."""
        f = _seed(tmp_personas_dir, _persona_dict(
            wake=["hey silver", "シルバー"],
            dismiss=["goodnight silver"],
        ))
        play = PlayAIdes(args_factory(f))
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "model_loaded", "name": "Silver.vrm"},
        })
        cmds = play.incarnation_server.commands
        active = [(c, p) for c, p in cmds if c == "persona_active"]
        assert len(active) == 1
        _, payload = active[0]
        assert payload["name"] == "Silver"
        assert payload["wake_words"] == ["hey silver", "シルバー"]
        assert payload["dismiss_words"] == ["goodnight silver"]

    def test_persona_active_handles_unset_fields(self, tmp_personas_dir, args_factory):
        """Persona without wake/dismiss config still emits persona_active —
        with empty lists. Browser will simply never match anything."""
        f = _seed(tmp_personas_dir, _persona_dict(wake=None, dismiss=None))
        play = PlayAIdes(args_factory(f))
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "model_loaded", "name": "Silver.vrm"},
        })
        cmds = play.incarnation_server.commands
        active = [(c, p) for c, p in cmds if c == "persona_active"]
        assert len(active) == 1
        _, payload = active[0]
        assert payload["wake_words"] == []
        assert payload["dismiss_words"] == []
