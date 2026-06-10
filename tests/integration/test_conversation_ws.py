import pytest


@pytest.mark.usefixtures("no_incarnation", "tmp_personas_dir")
def test_user_input_drives_run_turn_and_pushes_frames(monkeypatch):
    from playAIdes import PlayAIdes, PlayAIdesArgs
    from model_interfaces import MockLLM

    ai = PlayAIdes(PlayAIdesArgs(persona=["personas/testbot/persona.json"],
                                 use_avatar=True, llm=MockLLM(),
                                 generate_voice=False, use_voice=False,
                                 generate_avatar=False))
    server = ai.incarnation_server          # the StubIncarnationServer
    server.commands.clear()

    ai._handle_incarnation_message({"type": "user_input",
                                    "payload": {"text": "hello there"}})

    types = [c[0] for c in server.commands]
    assert "reply_started" in types
    assert "reply_done" in types
    assert "assistant_message" in types     # the subtitle still fires (viewer unchanged)
