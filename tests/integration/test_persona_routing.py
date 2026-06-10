"""Integration test: assistant_message broadcasts only to clients bound
to the matching persona_id.

Uses raw WebSocket clients via FastAPI's TestClient since this exercises
the actual broadcast path."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Stub unavailable native deps so tests that import PlayAIdes (e.g.
# test_chat_assistant_message_routes_via_persona_binding) can run without the
# full Docker environment.  Only voicebox/voicebox_client are stubbed —
# incarnation_server and ha_client are real modules used by these tests.
for _mod in ("voicebox_client", "voicebox", "voicebox.api_models"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


pytestmark = pytest.mark.integration


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):  # pragma: no cover
        pass


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Bare server with a no-op callback so we can drive WS frames directly.

    Uses _NoopThread so no real uvicorn thread spawns; TestClient drives
    the ASGI app directly."""
    import incarnation_server as mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "threading", type("m", (), {"Thread": _NoopThread}))
    msgs_received: list = []
    s = mod.IncarnationServer(
        host="127.0.0.1", port=18766,
        on_message_callback=lambda msg: msgs_received.append(msg),
    )
    s.received = msgs_received
    return s


def _wait_for_callback_count(server, msg_type: str, expected: int, timeout: float = 2.0):
    """Spin until the callback log has `expected` messages of `msg_type`.

    Used as a sync barrier: once the server callback fires for a frame,
    the WS endpoint has finished processing it (including binding side
    effects on `_bindings`)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sum(1 for m in server.received if m.get("type") == msg_type) >= expected:
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {expected}× {msg_type} callbacks")


def test_assistant_message_broadcasts_only_to_bound_clients(server):
    """Two WS clients bind to different personas; assistant_message for
    one persona reaches only that client."""
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as ws_a, \
         client.websocket_connect("/ws") as ws_b:
        # Bind ws_a to "silver", ws_b to "rin".
        ws_a.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "silver"}}))
        ws_b.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "rin"}}))
        # Sync barrier: wait for both bind frames to land in callback log,
        # which means the server has processed the binds.
        _wait_for_callback_count(server, "set_active_persona", 2)

        # Server-side broadcast targeted at "silver" only.
        server.broadcast_to_persona("silver", "assistant_message", {
            "text": "for silver only", "persona_id": "silver",
        })
        # ws_a should see the assistant_message.
        msg_a = json.loads(ws_a.receive_text())
        assert msg_a["type"] == "assistant_message"
        assert msg_a["payload"]["text"] == "for silver only"

        # ws_b shouldn't have a frame waiting from the silver broadcast.
        # Prove this with a sentinel: targeted ping to "rin" — if the
        # earlier broadcast was incorrectly routed to ws_b, the FIFO of
        # ws_b's recv channel would contain the silver msg first.
        server.broadcast_to_persona("rin", "ping", {"hello": "rin"})
        msg_b = json.loads(ws_b.receive_text())
        assert msg_b["type"] == "ping"
        assert msg_b["payload"] == {"hello": "rin"}


def test_disconnect_clears_binding(server):
    """When a client disconnects, its persona binding is removed and a
    later broadcast doesn't try to send to a closed socket."""
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "silver"}}))
        _wait_for_callback_count(server, "set_active_persona", 1)
    # Connection is closed by the time we exit the with-block; the
    # `finally` clause in the WS endpoint should have cleared the binding.
    assert server._bindings == {}
    # Broadcasting should be a no-op (no targets) and must not raise.
    server.broadcast_to_persona("silver", "assistant_message", {"text": "after disconnect"})


def test_dismiss_persona_clears_binding(server):
    """dismiss_persona unbinds the client; subsequent broadcasts don't
    reach it (until it re-binds)."""
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "silver"}}))
        _wait_for_callback_count(server, "set_active_persona", 1)

        ws.send_text(json.dumps({"type": "dismiss_persona", "payload": {"id": "silver"}}))
        _wait_for_callback_count(server, "dismiss_persona", 1)

        # Broadcast for "silver" — should NOT reach this client (no
        # bindings remaining for "silver").
        server.broadcast_to_persona("silver", "assistant_message", {"text": "after dismiss"})

        # Sentinel: a broadcast_to_all reaches every connected client
        # regardless of binding. If dismiss worked, the silver broadcast
        # was a no-op, so the next frame on the wire is global_ping.
        server.broadcast_to_all("global_ping", {"x": 1})
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "global_ping"
        assert msg["payload"] == {"x": 1}


def test_set_active_persona_routes_all_messages_via_persona_binding(persona_file, fake_tts, tmp_personas_dir):
    """Multi-TV regression: when set_active_persona swaps to a new persona,
    EVERY persona-scoped message (persona_changed, unload_model, load_model,
    set_background, history_loaded) must route via broadcast_to_persona to
    the requested id — never via broadcast_to_all. Spec §3 multi-TV memory.

    Uses MagicMock to verify the routing intent (which method was called
    with which persona_id) rather than driving the full multi-WS plumbing.
    """
    from playAIdes import PlayAIdes, PlayAIdesArgs
    from model_interfaces import MockLLM
    from unittest.mock import MagicMock

    # Seed a Rin persona on disk so set_persona("rin") succeeds.
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
            "background_url": "rin_bg.jpg",
        },
    }))

    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    play = PlayAIdes(args)
    from incarnation_server import WebSocketDisplayChannel
    spy = MagicMock()
    spy.broadcast_to_persona = MagicMock()
    spy.broadcast_to_all = MagicMock()
    spy.send_command = MagicMock()
    play.incarnation_server = spy
    play.display = WebSocketDisplayChannel(spy)

    play._handle_incarnation_message({
        "type": "set_active_persona",
        "payload": {"id": "rin"},
    })

    # Every persona-scoped message routes via broadcast_to_persona("rin", ...).
    routed_types = [
        call.args[1] for call in spy.broadcast_to_persona.call_args_list
        if call.args[0] == "rin"
    ]
    for required in ("persona_changed", "unload_model", "load_model",
                     "set_background", "history_loaded"):
        assert required in routed_types, (
            f"{required} did not route via broadcast_to_persona('rin', ...) — "
            f"routed types: {routed_types}"
        )

    # Critical: NONE of the persona-scoped messages should be sent via
    # broadcast_to_all (which would leak to TVs showing other personas).
    leaky_types = {call.args[0] for call in spy.broadcast_to_all.call_args_list}
    leaky_via_send_command = {call.args[0] for call in spy.send_command.call_args_list}
    forbidden = {"persona_changed", "unload_model", "load_model",
                 "set_background", "history_loaded", "play_animation"}
    assert not (leaky_types & forbidden), (
        f"Persona-scoped messages leaked to broadcast_to_all: {leaky_types & forbidden}"
    )
    assert not (leaky_via_send_command & forbidden), (
        f"Persona-scoped messages leaked to send_command: "
        f"{leaky_via_send_command & forbidden}"
    )


def test_chat_assistant_message_routes_via_persona_binding(persona_file, fake_tts):
    """chat() should call broadcast_to_persona, not broadcast_to_all,
    so only clients bound to the persona see the reply."""
    from playAIdes import PlayAIdes, PlayAIdesArgs
    from model_interfaces import MockLLM
    from unittest.mock import MagicMock

    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    play = PlayAIdes(args)
    # Replace the stub server with a MagicMock so we can spy on the calls.
    from incarnation_server import WebSocketDisplayChannel
    spy = MagicMock()
    spy.broadcast_to_persona = MagicMock()
    play.incarnation_server = spy
    play.display = WebSocketDisplayChannel(spy)

    play.chat("hello")
    # Find the assistant_message broadcast.
    persona_id = play.current_persona.name.strip().lower().replace(" ", "_")
    expected_text = "Mock Response: I heard you say 'hello'."
    spy.broadcast_to_persona.assert_any_call(
        persona_id, "assistant_message",
        {"text": expected_text, "persona_id": persona_id},
    )
