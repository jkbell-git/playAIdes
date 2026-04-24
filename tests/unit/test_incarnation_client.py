"""Unit tests for incarnation_client.IncarnationClient.

The client fires-and-forgets messages via ``websockets.connect`` in a
background thread. We mock the ``websockets.connect`` async context manager
and verify the wire format.
"""
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from incarnation_client import IncarnationClient


class _FakeWS:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, payload: str):
        self.sent.append(payload)


class _FakeConnect:
    """Stand-in for ``websockets.connect(uri)`` async context manager."""

    def __init__(self, ws: _FakeWS):
        self.ws = ws

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_send_command_serializes_and_sends():
    ws = _FakeWS()

    def fake_connect(uri):
        # capture uri for later assertion
        fake_connect.captured_uri = uri
        return _FakeConnect(ws)

    with patch("incarnation_client.websockets.connect", side_effect=fake_connect):
        client = IncarnationClient(uri="ws://example:1234")
        client.send_command("play_animation", {"name": "wave", "loop": False})
        assert _wait_for(lambda: len(ws.sent) == 1)

    assert fake_connect.captured_uri == "ws://example:1234"
    msg = json.loads(ws.sent[0])
    assert msg == {"type": "play_animation", "payload": {"name": "wave", "loop": False}}


def test_send_command_no_payload():
    ws = _FakeWS()
    with patch("incarnation_client.websockets.connect", return_value=_FakeConnect(ws)):
        IncarnationClient().send_command("ping")
        assert _wait_for(lambda: len(ws.sent) == 1)
    msg = json.loads(ws.sent[0])
    assert msg["type"] == "ping"
    # payload may or may not be present depending on implementation — either is fine,
    # but if present it must be a dict.
    if "payload" in msg:
        assert isinstance(msg["payload"], dict)
