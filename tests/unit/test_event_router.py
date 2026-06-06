# tests/unit/test_event_router.py
from persona import Trigger
from skills.router import match_event_trigger, _interpolate_params


def _et(event, skill, match=None, params=None):
    on = {"event": event}
    if match is not None:
        on["match"] = match
    return Trigger(on=on, do={"skill": skill, "params": params or {}})


def test_matches_event_by_name():
    triggers = [_et("front_door_motion", "show_pip", params={"source": "camera.fd"})]
    out = match_event_trigger("front_door_motion", {}, triggers)
    assert out == ("show_pip", {"source": "camera.fd"})


def test_match_conditions_must_all_hold():
    triggers = [_et("motion", "show_pip", match={"state": "on"}, params={"x": 1})]
    assert match_event_trigger("motion", {"state": "off"}, triggers) is None
    assert match_event_trigger("motion", {"state": "on"}, triggers) == ("show_pip", {"x": 1})


def test_payload_interpolation_preserves_type():
    triggers = [_et("ev", "show_pip", params={"source": "{payload.entity_id}", "n": "{payload.count}"})]
    out = match_event_trigger("ev", {"entity_id": "camera.fd", "count": 3}, triggers)
    assert out == ("show_pip", {"source": "camera.fd", "n": 3})


def test_phrase_triggers_ignored_by_event_matcher():
    triggers = [Trigger(on={"phrase": "show the door"}, do={"skill": "show_pip", "params": {"url": "u"}})]
    assert match_event_trigger("show the door", {}, triggers) is None


def test_first_match_wins():
    triggers = [_et("ev", "first"), _et("ev", "second")]
    assert match_event_trigger("ev", {}, triggers)[0] == "first"


def test_interpolate_params_unmatched_field_becomes_none():
    assert _interpolate_params({"a": "{payload.missing}"}, {}) == {"a": None}
