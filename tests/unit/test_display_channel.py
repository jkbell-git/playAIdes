from incarnation_server import WebSocketDisplayChannel


class _StubServer:
    def __init__(self):
        self.calls = []
    def broadcast_to_persona(self, persona_id, cmd_type, payload=None):
        self.calls.append((persona_id, cmd_type, payload))


def test_websocket_display_channel_forwards_push_to_broadcast():
    server = _StubServer()
    ch = WebSocketDisplayChannel(server)
    ch.push("silver", "reply_delta", {"text": "hi"})
    assert server.calls == [("silver", "reply_delta", {"text": "hi"})]
