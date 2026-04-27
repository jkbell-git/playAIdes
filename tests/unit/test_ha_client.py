"""Unit tests for ha_client.HAClient (HTTP mocked with `responses`)."""
import responses

from ha_client import HAClient, ConversationResponse


HA_BASE = "http://ha.test:8123"


@responses.activate
def test_converse_success_extracts_speech_text():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        json={
            "response": {
                "response_type": "action_done",
                "speech": {"plain": {"speech": "Turning off the lights"}},
            },
            "conversation_id": "conv-123",
        },
        status=200,
    )
    client = HAClient(HA_BASE, "tok")
    r = client.converse("turn off the lights", agent_id="conversation.assist")
    assert isinstance(r, ConversationResponse)
    assert r.success is True
    assert r.speech_text == "Turning off the lights"
    assert r.conversation_id == "conv-123"
    assert r.error_code is None


@responses.activate
def test_converse_no_intent_match_returns_failure():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        json={
            "response": {
                "response_type": "error",
                "data": {"code": "no_intent_match"},
                "speech": {"plain": {"speech": "Sorry, I couldn't understand that"}},
            },
            "conversation_id": None,
        },
        status=200,
    )
    client = HAClient(HA_BASE, "tok")
    r = client.converse("xyzzy")
    assert r.success is False
    assert r.error_code == "no_intent_match"
    assert r.speech_text == "I didn't catch that — try rephrasing?"


@responses.activate
def test_converse_401_returns_failure_with_generic_message():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        json={"message": "Unauthorized"},
        status=401,
    )
    client = HAClient(HA_BASE, "bad-token")
    r = client.converse("anything")
    assert r.success is False
    assert r.error_code == "ha_http_401"
    assert "can't reach" in r.speech_text.lower() or "trouble" in r.speech_text.lower()


@responses.activate
def test_converse_timeout_returns_failure():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        body=ConnectionError("simulated network drop"),
    )
    client = HAClient(HA_BASE, "tok", timeout=1.0)
    r = client.converse("anything")
    assert r.success is False
    assert r.error_code == "ha_unreachable"
    assert "can't reach the house" in r.speech_text.lower()


@responses.activate
def test_health_check_true_on_200():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=200)
    assert HAClient(HA_BASE, "tok").health_check() is True


@responses.activate
def test_health_check_false_on_5xx():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=500)
    assert HAClient(HA_BASE, "tok").health_check() is False


@responses.activate
def test_health_check_false_on_network_error():
    responses.add(
        responses.GET, f"{HA_BASE}/api/",
        body=ConnectionError("simulated"),
    )
    assert HAClient(HA_BASE, "tok").health_check() is False


@responses.activate
def test_converse_sends_bearer_token_and_agent_id():
    captured: dict = {}

    def callback(request):
        captured["auth"] = request.headers.get("Authorization")
        import json as _json
        captured["body"] = _json.loads(request.body)
        return (200, {}, '{"response": {"speech": {"plain": {"speech": "ok"}}}, "conversation_id": null}')

    responses.add_callback(
        responses.POST, f"{HA_BASE}/api/conversation/process", callback=callback,
    )
    HAClient(HA_BASE, "my-token").converse(
        "hello", agent_id="conversation.foo", conversation_id="prev-id",
    )
    assert captured["auth"] == "Bearer my-token"
    assert captured["body"]["text"] == "hello"
    assert captured["body"]["agent_id"] == "conversation.foo"
    assert captured["body"]["conversation_id"] == "prev-id"
