"""End-to-end live chat test: real LLM (any OpenAI-compat) + FakeTTS."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from model_interfaces import OpenAICompatLLM
from playAIdes import PlayAIdes, PlayAIdesArgs

pytestmark = [pytest.mark.live, pytest.mark.slow]


def test_end_to_end_chat(
    llm_url: str, persona_file: Path, fake_tts, no_incarnation
):
    model = os.environ.get("LLM_MODEL", "gemma3:4b")
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False,
        use_voice=False,
        use_avatar=False,
        generate_avatar=False,
        llm=OpenAICompatLLM(base_url=llm_url, model=model),
        tts=fake_tts,
    )
    play = PlayAIdes(args)
    reply = play.chat("Respond with a single short greeting.")
    assert isinstance(reply, str)
    assert reply.strip() != ""
    assert play.chat_history[-1]["role"] == "user"
