"""Unit tests for match_keywords.match_keyword_prefix."""
from match_keywords import match_keyword_prefix


def test_no_keywords_returns_no_match():
    assert match_keyword_prefix("turn off the lights", []) == (False, "")


def test_keyword_at_start_matches_and_strips():
    matched, residual = match_keyword_prefix("house turn off the lights", ["house"])
    assert matched is True
    assert residual == "turn off the lights"


def test_match_is_case_insensitive():
    matched, residual = match_keyword_prefix("HOUSE turn off the lights", ["house"])
    assert matched is True
    assert residual == "turn off the lights"


def test_keyword_only_returns_match_with_empty_residual():
    matched, residual = match_keyword_prefix("house", ["house"])
    assert matched is True
    assert residual == ""


def test_keyword_in_middle_does_not_match():
    """Prefix match only — house anywhere but the start is not a delegation."""
    matched, residual = match_keyword_prefix(
        "play the song House of the Rising Sun", ["house"]
    )
    assert matched is False
    assert residual == ""


def test_leading_whitespace_tolerated():
    matched, residual = match_keyword_prefix("   house  turn off  ", ["house"])
    assert matched is True
    assert residual == "turn off"


def test_first_match_wins_with_multiple_keywords():
    matched, residual = match_keyword_prefix(
        "home dim the lights", ["house", "home"]
    )
    assert matched is True
    assert residual == "dim the lights"


def test_keyword_must_be_followed_by_space_or_end():
    """A word starting with the keyword (e.g. 'household') is not a match."""
    matched, residual = match_keyword_prefix("household chores", ["house"])
    assert matched is False


def test_punctuation_after_keyword_is_residual():
    matched, residual = match_keyword_prefix("house, turn off", ["house"])
    assert matched is True
    assert residual == ", turn off"
