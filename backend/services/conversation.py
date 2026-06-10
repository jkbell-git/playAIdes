"""The conversation turn, extracted from PlayAIdes.chat (slice 2).

Transport-free: no FastAPI, no requests, no voicebox_client. Collaborators are
injected, so this module is unit-testable without the not-yet-migrated voicebox
package. run_turn yields the turn-event stream; the WS adapter forwards events as
frames, the REST adapter drains them to a full reply."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)


@dataclass
class TurnEvent:
    type: str                                  # reply_started | reply_delta | reply_done
    payload: dict = field(default_factory=dict)


class ConversationService:
    def __init__(self, *, get_persona: Callable, history_load: Callable,
                 history_save: Callable, dispatch: Callable, llm,
                 speak: Callable, ha=None, ha_default_agent_id: Optional[str] = None,
                 history_cap: int = 80):
        self._get_persona = get_persona
        self._history_load = history_load
        self._history_save = history_save
        self._dispatch = dispatch
        self._llm = llm
        self._speak = speak
        self._ha = ha
        self._ha_default_agent_id = ha_default_agent_id
        self._history_cap = history_cap
        self._ha_conversation_ids: dict[str, str] = {}

    def run_turn(self, persona_id: str, text: str) -> Iterator[TurnEvent]:
        persona = self._get_persona(persona_id)
        target_id = persona_id
        yield TurnEvent("reply_started", {"persona_id": target_id})

        if persona is None:
            yield TurnEvent("reply_delta", {"persona_id": target_id, "text": "No persona loaded."})
            yield TurnEvent("reply_done", {"persona_id": target_id, "text": "No persona loaded."})
            return

        # Deterministic phrase trigger (precedence: phrase → house_words → LLM).
        from skills.router import match_phrase_trigger
        matched = match_phrase_trigger(text, persona.triggers, persona.skills)
        if matched is not None:
            skill_name, params = matched
            self._dispatch(target_id, skill_name, params)
            yield TurnEvent("reply_delta", {"persona_id": target_id, "text": ""})
            yield TurnEvent("reply_done", {"persona_id": target_id, "text": ""})
            return

        # LLM / house-word paths land in Tasks 4 & 5.
        yield TurnEvent("reply_delta", {"persona_id": target_id, "text": ""})
        yield TurnEvent("reply_done", {"persona_id": target_id, "text": ""})
