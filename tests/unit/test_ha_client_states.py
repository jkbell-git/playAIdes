"""Unit tests for HAClient.get_states / call_service (HTTP mocked with `responses`)."""
import responses

from ha_client import HAClient

HA_BASE = "http://ha.test:8123"


@responses.activate
def test_get_states_returns_list():
    responses.add(
        responses.GET, f"{HA_BASE}/api/states",
        json=[{"entity_id": "camera.front", "attributes": {"friendly_name": "Front"}}],
        status=200,
    )
    out = HAClient(HA_BASE, "tok").get_states()
    assert out == [{"entity_id": "camera.front", "attributes": {"friendly_name": "Front"}}]


@responses.activate
def test_get_states_returns_none_on_error():
    responses.add(responses.GET, f"{HA_BASE}/api/states", status=500)
    assert HAClient(HA_BASE, "tok").get_states() is None


@responses.activate
def test_call_service_true_on_200_and_sends_bearer():
    captured = {}

    def cb(request):
        captured["auth"] = request.headers.get("Authorization")
        return (200, {}, "[]")

    responses.add_callback(
        responses.POST, f"{HA_BASE}/api/services/script/turn_on", callback=cb,
    )
    ok = HAClient(HA_BASE, "my-token").call_service(
        "script", "turn_on", {"entity_id": "script.greet"})
    assert ok is True
    assert captured["auth"] == "Bearer my-token"


@responses.activate
def test_call_service_false_on_network_error():
    responses.add(
        responses.POST, f"{HA_BASE}/api/services/script/turn_on",
        body=ConnectionError("down"),
    )
    assert HAClient(HA_BASE, "tok").call_service("script", "turn_on", {}) is False
