"""Hermetic tests for the conversation REST adapter (slice 2).

Builds a standalone FastAPI app with the router + a fake conversation service
on app.state. Does NOT import playAIdes; safe to run via bin/test.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.conversation import router
from backend.services.conversation import TurnEvent


class _FakeConv:
    def run_turn(self, persona_id, text):
        yield TurnEvent("reply_started", {"persona_id": persona_id})
        yield TurnEvent("reply_delta", {"persona_id": persona_id, "text": "Hi "})
        yield TurnEvent("reply_delta", {"persona_id": persona_id, "text": text})
        yield TurnEvent("reply_done", {"persona_id": persona_id, "text": f"Hi {text}"})


def _client():
    app = FastAPI()
    app.state.conversation_service = _FakeConv()
    app.include_router(router)
    return TestClient(app)


def test_post_message_drains_to_full_reply(with_api_key):
    client = _client()
    resp = client.post("/api/v1/personas/silver/messages",
                       json={"text": "there"},
                       headers={"Authorization": f"Bearer {with_api_key}"})
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Hi there"}


def test_post_message_requires_auth(with_api_key):
    # with_api_key configures PLAYAIDES_API_KEY so auth is enforced;
    # sending no Authorization header -> 401
    resp = _client().post("/api/v1/personas/silver/messages", json={"text": "x"})
    assert resp.status_code == 401
