# tests/unit/test_http_skill.py
import httpx
import pytest

from skills.base import SkillContext
from skills.declarative import HttpSkill, _interpolate_body


def _ctx():
    spoken = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda *a: None,
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    return ctx, spoken


def test_interpolate_body_whole_token_keeps_type():
    body = {"brightness": "{level}", "name": "fixed", "nested": {"id": "{eid}"}}
    out = _interpolate_body(body, {"level": 80, "eid": "light.x"})
    assert out == {"brightness": 80, "name": "fixed", "nested": {"id": "light.x"}}


def test_http_skill_get_interpolates_and_encodes_url(monkeypatch):
    captured = {}

    def fake_request(self, method, url, headers=None, json=None):
        captured["method"], captured["url"] = method, url
        return httpx.Response(200, text="OK")

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    spec = {"name": "weather", "kind": "http", "method": "GET",
            "url": "https://api.test/q?city={city}", "params": {"city": "str"}}
    ctx, spoken = _ctx()
    res = HttpSkill(spec).execute(HttpSkill(spec).Params(city="São Paulo"), ctx)
    assert res.ok is True and res.output == "OK"
    assert captured["method"] == "GET"
    # Space + non-ASCII percent-encoded, never raw-concatenated.
    assert captured["url"] == "https://api.test/q?city=S%C3%A3o%20Paulo"
    assert spoken == []


def test_http_skill_announces_response_when_configured(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request",
                        lambda self, m, u, headers=None, json=None: httpx.Response(200, text="72F"))
    spec = {"name": "temp", "kind": "http", "url": "https://api.test/t",
            "params": {}, "announce_output": True}
    ctx, spoken = _ctx()
    HttpSkill(spec).execute(HttpSkill(spec).Params(), ctx)
    assert spoken == [("silver", "72F")]


def test_http_skill_non_2xx_marks_failure(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request",
                        lambda self, m, u, headers=None, json=None: httpx.Response(500, text="boom"))
    spec = {"name": "x", "kind": "http", "url": "https://api.test/x", "params": {}}
    ctx, _ = _ctx()
    res = HttpSkill(spec).execute(HttpSkill(spec).Params(), ctx)
    assert res.ok is False and res.error == "http_500"


def test_http_skill_malformed_template_returns_failure():
    # An unclosed brace in the url template raises ValueError from str.format;
    # execute() must catch it and return ok=False rather than raising.
    spec = {"name": "bad", "kind": "http", "url": "https://api.test/q?x={y", "params": {"y": "str"}}
    ctx, _ = _ctx()
    res = HttpSkill(spec).execute(HttpSkill(spec).Params(y="z"), ctx)
    assert res.ok is False
    assert res.error and res.error.startswith("bad template")
