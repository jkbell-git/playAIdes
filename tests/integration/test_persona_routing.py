"""Integration test: assistant_message broadcasts only to clients bound
to the matching persona_id.

Uses raw WebSocket clients via FastAPI's TestClient since this exercises
the actual broadcast path."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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
