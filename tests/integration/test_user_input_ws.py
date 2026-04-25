"""Integration test: incoming `user_input` WS messages route to PlayAIdes.chat()."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False,
        use_voice=False,
        use_avatar=True,
        generate_avatar=False,
        llm=MockLLM(),
        tts=fake_tts,
    )
    return PlayAIdes(args)


def test_user_input_routes_to_chat(play):
    """A `user_input` WS message triggers chat() and the assistant_message
    broadcast path that Phase 1 already wired."""
    play._handle_incarnation_message({
        "type": "user_input",
        "payload": {"text": "hello there"},
    })

    cmds = play.incarnation_server.commands
    assistant_messages = [
        (cmd, payload) for cmd, payload in cmds if cmd == "assistant_message"
    ]
    assert len(assistant_messages) == 1
    _, payload = assistant_messages[0]
    assert payload["text"]  # MockLLM returns a non-empty string


def test_user_input_ignores_empty_text(play):
    """Empty / whitespace-only utterances drop silently (don't waste an LLM round-trip)."""
    play._handle_incarnation_message({
        "type": "user_input",
        "payload": {"text": "   "},
    })
    cmds = play.incarnation_server.commands
    assistant_messages = [c for c, _ in cmds if c == "assistant_message"]
    assert assistant_messages == []


def test_user_input_missing_text_does_not_crash(play):
    """Malformed payload (no `text` key) is ignored, not raised."""
    play._handle_incarnation_message({
        "type": "user_input",
        "payload": {},
    })  # Should not raise
