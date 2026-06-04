"""Deterministic router — pure matchers (spec §3.5). No LLM in the loop.
v1: the voice (phrase) path. The event path lands in Plan 2."""
from __future__ import annotations

from typing import Iterable, Optional

from persona import Trigger
from match_keywords import match_keyword_prefix


def match_phrase_trigger(
    text: str,
    triggers: Iterable[Trigger],
    enabled_skills: list[str],
) -> Optional[tuple[str, dict]]:
    """First enabled phrase-trigger whose phrase prefixes `text` wins.

    Returns (skill_name, params) or None. Reuses match_keyword_prefix's
    case-insensitive, word-boundary, prefix-only semantics. Event triggers
    (no `on.phrase`) are ignored here.
    """
    for trig in triggers:
        phrase = trig.on.phrase
        if not phrase:
            continue
        matched, _residual = match_keyword_prefix(text, [phrase])
        if matched and trig.do.skill in enabled_skills:
            return (trig.do.skill, dict(trig.do.params))
    return None
