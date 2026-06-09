"""HomeAssistantProvider normalizes /api/states and routes invoke() (HTTP mocked)."""
import responses
from pathlib import Path

from backend.clients.providers.base import Status, CAP_PIP, CAP_SCRIPTS, CAP_LAUNCH_TARGETS
from backend.clients.providers.homeassistant import HomeAssistantProvider
from backend.stores import config_store, secrets_store
from backend.clients.providers import registry

HA_BASE = "http://ha.test:8123"


def _provider():
    return HomeAssistantProvider(HA_BASE, "tok")


@responses.activate
def test_health_ok_when_api_reachable():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=200)
    s = _provider().health()
    assert isinstance(s, Status) and s.ok is True


@responses.activate
def test_health_reports_reason_when_unreachable():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=401)
    s = _provider().health()
    assert s.ok is False and s.reason


@responses.activate
def test_discover_keeps_only_v1_domains_and_normalizes():
    responses.add(
        responses.GET, f"{HA_BASE}/api/states",
        json=[
            {"entity_id": "camera.front", "attributes": {"friendly_name": "Front Cam"}},
            {"entity_id": "media_player.tv", "attributes": {"friendly_name": "TV"}},
            {"entity_id": "script.greet", "attributes": {}},
            {"entity_id": "sun.sun", "attributes": {"friendly_name": "Sun"}},  # dropped
        ],
        status=200,
    )
    items = _provider().discover()
    assert [i.id for i in items] == ["camera.front", "media_player.tv", "script.greet"]
    cam = items[0]
    assert cam.domain == "camera"
    assert cam.name == "Front Cam"
    assert CAP_PIP in cam.capabilities
    mp = items[1]
    assert set(mp.capabilities) == {"say_target", CAP_LAUNCH_TARGETS}
    assert items[2].name == "script.greet"  # friendly_name absent -> entity_id


@responses.activate
def test_invoke_camera_returns_resolved_url():
    responses.add(
        responses.GET, f"{HA_BASE}/api/states/camera.front",
        json={"attributes": {"access_token": "abc"}}, status=200,
    )
    out = _provider().invoke(CAP_PIP, "camera.front")
    assert out["ok"] is True
    assert out["url"].endswith("/api/camera_proxy/camera.front?token=abc")


@responses.activate
def test_invoke_script_fires_service():
    responses.add(
        responses.POST, f"{HA_BASE}/api/services/script/turn_on", json=[], status=200,
    )
    out = _provider().invoke(CAP_SCRIPTS, "script.greet")
    assert out["ok"] is True


def test_invoke_unsupported_capability_is_handled():
    out = _provider().invoke("nope", "x")
    assert out["ok"] is False and out["reason"]


def test_build_provider_constructs_ha_from_store_and_secret(tmp_path: Path):
    store_path = str(tmp_path / "integrations.json")
    secret_path = str(tmp_path / "secrets.json")
    config_store.save({
        "providers": {"homeassistant": {
            "kind": "homeassistant", "enabled": True,
            "config": {"base_url": "http://ha.local:8123"}}},
        "mappings": {},
    }, store_path)
    secrets_store.set_secret("homeassistant", "token", "tok", secret_path)

    p = registry.build_provider("homeassistant", store_path=store_path, secret_path=secret_path)
    assert isinstance(p, HomeAssistantProvider)


def test_build_provider_returns_none_for_unknown(tmp_path: Path):
    store_path = str(tmp_path / "integrations.json")
    config_store.save({"providers": {}, "mappings": {}}, store_path)
    assert registry.build_provider("ghost", store_path=store_path,
                                   secret_path=str(tmp_path / "s.json")) is None
