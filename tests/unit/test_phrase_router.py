from persona import Trigger
from skills.router import match_phrase_trigger


def _t(phrase, skill, params=None):
    return Trigger(on={"phrase": phrase}, do={"skill": skill, "params": params or {}})


def test_matches_enabled_phrase_trigger():
    triggers = [_t("show the front door", "show_pip", {"url": "http://x"})]
    out = match_phrase_trigger("Show the front door", triggers, ["show_pip"])
    assert out == ("show_pip", {"url": "http://x"})


def test_skips_disabled_skill():
    triggers = [_t("show the front door", "show_pip")]
    assert match_phrase_trigger("show the front door", triggers, []) is None


def test_no_match_returns_none():
    triggers = [_t("show the front door", "show_pip")]
    assert match_phrase_trigger("what time is it", triggers, ["show_pip"]) is None


def test_first_match_wins():
    triggers = [
        _t("dismiss", "dismiss_pip"),
        _t("dismiss", "show_pip"),
    ]
    out = match_phrase_trigger("dismiss", triggers, ["dismiss_pip", "show_pip"])
    assert out[0] == "dismiss_pip"


def test_word_boundary_no_partial_match():
    # "show" must not match inside "showcase" (match_keyword_prefix semantics).
    triggers = [_t("show", "show_pip")]
    assert match_phrase_trigger("showcase the art", triggers, ["show_pip"]) is None


def test_event_triggers_are_ignored_by_phrase_router():
    triggers = [Trigger(on={"event": "motion"}, do={"skill": "show_pip"})]
    assert match_phrase_trigger("motion", triggers, ["show_pip"]) is None


def test_empty_triggers_returns_none():
    assert match_phrase_trigger("anything", [], ["show_pip"]) is None
