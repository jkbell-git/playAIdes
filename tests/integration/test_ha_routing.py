"""Integration tests for chat() routing to HA on house-word match."""
from __future__ import annotations

import json
import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _seed_persona_with_house_words(tmp_personas_dir, pid="silver",
                                    house_words=None,
                                    rephrase=False, agent_id=None):
    pdir = tmp_personas_dir / pid
    pdir.mkdir(exist_ok=True)
    persona = {
        "name": pid.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {"model_url": "x.vrm"},
        "house_words": house_words or [],
        "rephrase_ha_response": rephrase,
        "ha_agent_id": agent_id,
    }
    (pdir / "persona.json").write_text(json.dumps(persona))


@pytest.fixture
def play_with_ha(persona_file, fake_tts, no_incarnation, mock_ha_client):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    play = PlayAIdes(args)
    # Inject the mock HA client post-construction.
    play.ha_client = mock_ha_client
    return play


class TestHouseWordRouting:
    def test_house_word_match_calls_ha_and_uses_verbatim_response(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], agent_id="conversation.foo",
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="Lights are off.")

        result = play_with_ha.chat("house turn off the lights")

        assert mock_ha_client.calls == [{
            "text": "turn off the lights",
            "agent_id": "conversation.foo",
            "conversation_id": None,
        }]
        assert result == "Lights are off."

    def test_no_house_word_match_uses_persona_llm(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver", house_words=["house"],
        )
        play_with_ha.set_persona("silver")
        result = play_with_ha.chat("how are you?")
        # No HA call.
        assert mock_ha_client.calls == []
        # MockLLM echoes the input.
        assert "how are you?" in result

    def test_empty_house_words_never_calls_ha(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(tmp_personas_dir, "silver", house_words=[])
        play_with_ha.set_persona("silver")
        play_with_ha.chat("house turn off the lights")
        assert mock_ha_client.calls == []


class TestRephrase:
    def test_rephrase_enabled_calls_persona_llm_with_ha_response(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], rephrase=True,
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="Lights are off.")

        result = play_with_ha.chat("house turn off the lights")

        # HA was called once.
        assert len(mock_ha_client.calls) == 1
        # MockLLM echoes its last input — so the result should contain the
        # raw HA speech_text wrapped in the rephrase prompt.
        assert "Lights are off." in result

    def test_rephrase_disabled_skips_persona_llm(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], rephrase=False,
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="OK.")
        result = play_with_ha.chat("house turn off lights")
        # MockLLM echo would prefix with 'Mock Response:' — so absence
        # confirms the persona LLM was not called.
        assert "Mock Response" not in result
        assert result == "OK."
