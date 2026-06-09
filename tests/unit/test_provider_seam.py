"""The fake provider locks the seam contract and templates v2/v3 providers."""
from backend.clients.providers.base import Provider, Status, Item, CAP_PIP
from backend.clients.providers.fake import FakeProvider


def test_fake_provider_satisfies_the_seam():
    p = FakeProvider(
        items=[Item(id="camera.front", domain="camera", name="Front",
                    capabilities=[CAP_PIP])],
        healthy=True,
    )
    assert isinstance(p, Provider)
    assert p.kind == "fake"

    health = p.health()
    assert isinstance(health, Status)
    assert health.ok is True

    items = p.discover()
    assert [i.id for i in items] == ["camera.front"]
    assert items[0].capabilities == [CAP_PIP]

    result = p.invoke(CAP_PIP, "camera.front", {"preview": True})
    assert result["ok"] is True
    assert p.invocations == [(CAP_PIP, "camera.front", {"preview": True})]


def test_fake_provider_reports_unhealthy_with_reason():
    s = FakeProvider(healthy=False).health()
    assert s.ok is False
    assert s.reason  # non-empty human-readable reason
