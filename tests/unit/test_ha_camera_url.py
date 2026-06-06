# tests/unit/test_ha_camera_url.py
from unittest.mock import patch

from ha_client import HAClient


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
    def json(self):
        return self._payload


def _client():
    return HAClient("http://ha.local:8123/", "tok")


def test_snapshot_url_built_from_access_token():
    payload = {"attributes": {"access_token": "ABC", "entity_picture": "/api/camera_proxy/camera.fd?token=ABC"}}
    with patch("ha_client.requests.get", return_value=_Resp(200, payload)):
        url = _client().camera_url("camera.fd", stream=False)
    assert url == "http://ha.local:8123/api/camera_proxy/camera.fd?token=ABC"


def test_stream_url_uses_stream_segment():
    payload = {"attributes": {"access_token": "ABC"}}
    with patch("ha_client.requests.get", return_value=_Resp(200, payload)):
        url = _client().camera_url("camera.fd", stream=True)
    assert url == "http://ha.local:8123/api/camera_proxy_stream/camera.fd?token=ABC"


def test_falls_back_to_entity_picture_for_snapshot():
    payload = {"attributes": {"entity_picture": "/api/camera_proxy/camera.fd?token=XYZ"}}
    with patch("ha_client.requests.get", return_value=_Resp(200, payload)):
        url = _client().camera_url("camera.fd", stream=False)
    assert url == "http://ha.local:8123/api/camera_proxy/camera.fd?token=XYZ"


def test_returns_none_on_non_200():
    with patch("ha_client.requests.get", return_value=_Resp(404, {})):
        assert _client().camera_url("camera.fd") is None


def test_returns_none_on_no_token_no_picture():
    with patch("ha_client.requests.get", return_value=_Resp(200, {"attributes": {}})):
        assert _client().camera_url("camera.fd") is None
