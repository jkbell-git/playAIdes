"""Integration tests for the WebSocket /ws endpoint."""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration


class TestWebSocket:
    def test_callback_fires_on_inbound_message(self, incarnation_server, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "hello", "payload": {"x": 1}}))
            # Give the server a tick to process. TestClient is synchronous enough
            # that the callback should have fired before the next send.
            ws.send_text(json.dumps({"type": "ping"}))
        msgs = incarnation_server._callback_log
        types = [m.get("type") for m in msgs]
        assert "hello" in types and "ping" in types

    def test_invalid_json_is_ignored(self, incarnation_server, client):
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not-json{")
            ws.send_text(json.dumps({"type": "after_bad"}))
        # Only the valid one reached the callback.
        types = [m.get("type") for m in incarnation_server._callback_log]
        assert "after_bad" in types
        assert all(t != "not-json{" for t in types)

    def test_send_command_flushes_queue_on_connect(self, incarnation_server, client):
        # Before any client connects, queue a message.
        incarnation_server.send_command("preconnect", {"hello": "world"})
        assert len(incarnation_server.message_queue) == 1
        with client.websocket_connect("/ws") as ws:
            received = ws.receive_text()
        msg = json.loads(received)
        assert msg["type"] == "preconnect"
        assert msg["payload"] == {"hello": "world"}
        # Queue drained.
        assert incarnation_server.message_queue == []

    def test_send_command_with_no_client_queues(self, incarnation_server):
        incarnation_server.send_command("queued_cmd", {"k": "v"})
        assert len(incarnation_server.message_queue) == 1
        queued = json.loads(incarnation_server.message_queue[0])
        assert queued["type"] == "queued_cmd"
        assert queued["payload"] == {"k": "v"}
