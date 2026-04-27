"""Keyword-prefix matching for routing user input.

Used by playAIdes.chat() to detect 'house word' delegation: when the user's
input begins with a configured keyword (e.g. "house"), the residual text
after that keyword is forwarded to Home Assistant's conversation agent.

Mirrors the prefix-only semantics intended for transcriptMatcher.js's
matchPhrase but is intentionally more conservative — only the prefix
position counts as a match (so "play the song House of the Rising Sun"
does NOT delegate)."""
from __future__ import annotations

from typing import List, Tuple


def match_keyword_prefix(text: str, keywords: List[str]) -> Tuple[bool, str]:
    """Return (matched, residual) for the first keyword that prefixes text.

    Matching is case-insensitive, leading/trailing whitespace is tolerated,
    and the keyword must be followed by either end-of-string or a non-letter
    non-digit character (so "house" matches "house, turn..." but not
    "household chores").

    Returns (False, "") if no keyword matches or `keywords` is empty.
    """
    if not keywords:
        return (False, "")
    stripped = text.strip()
    lowered = stripped.lower()
    for kw in keywords:
        if not kw:
            continue
        kw_lower = kw.lower()
        if not lowered.startswith(kw_lower):
            continue
        # Word-boundary check: the char right after the keyword must be
        # absent (end of string) or non-alphanumeric.
        end = len(kw_lower)
        if end < len(lowered) and lowered[end].isalnum():
            continue
        # Residual is the remainder of the ORIGINAL (case-preserved) text
        # after the matched keyword, with leading whitespace stripped.
        residual = stripped[end:].lstrip(" \t")
        # Trailing whitespace is also stripped for ergonomics.
        return (True, residual.rstrip())
    return (False, "")
