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


def _interpolate_params(params: dict, payload: dict) -> dict:
    """Replace a param value of the exact form '{payload.<field>}' with the raw
    (typed) value from the event payload; missing fields resolve to None. Other
    values pass through unchanged. (Partial/templated interpolation is deferred.)"""
    out: dict = {}
    for k, v in (params or {}).items():
        if isinstance(v, str) and v.startswith("{payload.") and v.endswith("}"):
            out[k] = (payload or {}).get(v[len("{payload."):-1])
        else:
            out[k] = v
    return out


def match_event_trigger(
    name: str,
    payload: dict,
    triggers: Iterable[Trigger],
) -> Optional[tuple[str, dict]]:
    """First event-trigger whose `on.event` equals `name` and whose `on.match`
    (shallow equality vs payload) holds wins. Returns (skill_name, interpolated
    params) or None.

    Enablement is NOT checked here — by design. The caller MUST gate via
    SkillRegistry.is_enabled before dispatch (spec §3.5): the phrase matcher
    gates inline, but _dispatch_skill checks only *registration*, so the event
    path's enable-gate lives in PlayAIdes.handle_event (Task 8)."""
    payload = payload or {}
    for trig in triggers:
        if not trig.on.event or trig.on.event != name:
            continue
        match = trig.on.match or {}
        if all(payload.get(k) == v for k, v in match.items()):
            return (trig.do.skill, _interpolate_params(dict(trig.do.params), payload))
    return None
