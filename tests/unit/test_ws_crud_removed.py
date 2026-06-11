"""The WS dispatcher's persona-CRUD branches are DELETED (creator.js was their
only consumer, now on REST). get_personas stays — viewer.js consumes it."""
from __future__ import annotations

import pytest

from model_interfaces import MockLLM
from playAIdes import PlayAIdes, PlayAIdesArgs


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)], generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False, llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


def test_crud_frames_are_inert(play):
    before = list(play.incarnation_server.commands)
    for msg_type, payload in [
        ("get_persona", {"id": "testbot"}),
        ("create_persona", {"name": "Ghost", "description": ""}),
        ("update_persona", {"id": "testbot", "name": "Hacked"}),
        ("delete_persona", {"id": "testbot"}),
    ]:
        play._handle_incarnation_message({"type": msg_type, "payload": payload})
    assert play.incarnation_server.commands == before   # no reply frames
    assert play.get_persona_by_id("ghost") is None       # nothing created
    assert play.get_persona_by_id("testbot")["name"] == "TestBot"  # nothing changed


def test_get_personas_still_answers(play):
    play._handle_incarnation_message({"type": "get_personas", "payload": {}})
    cmds = dict(play.incarnation_server.commands)
    assert [p["id"] for p in cmds["personas_list"]["personas"]] == ["testbot"]
