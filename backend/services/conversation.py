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

    def _system_prompt(self, persona) -> str:
        sp = (f"You are impersonating a this character named"
              f"{persona.name}. "
              f"Your background is: {persona.back_ground}. ")
        if persona.psyche and persona.psyche.traits:
            sp += (f"Your Psyche contains the following traits"
                   f"{', '.join(persona.psyche.traits)}. ")
        if persona.memories and persona.memories.memories:
            sp += (f"your memories are: {persona.memories.memories}.")
        sp += "be a helpful assistant to the user. with yor responses in character"
        if persona.persona_voice and persona.persona_voice.is_voice_valid():
            sp += (f"your response will be sent to a TTS service to be spoken."
                   f"please make sure your response does not contain things not spoken. no emojis")
        return sp

    def _ha_turn(self, persona, target_id: str, residual: str) -> str:
        assert self._ha is not None, "_ha_turn called without an HA client"
        if not residual:
            return "What about the house?"
        agent_id = persona.ha_agent_id or self._ha_default_agent_id
        conv_id = self._ha_conversation_ids.get(target_id)
        ha_resp = self._ha.converse(residual, agent_id=agent_id, conversation_id=conv_id)
        if ha_resp.conversation_id:
            self._ha_conversation_ids[target_id] = ha_resp.conversation_id
        response = ha_resp.speech_text
        if ha_resp.success and persona.rephrase_ha_response:
            rephrase_prompt = (
                f"You are {persona.name}. Rephrase this in your voice, keeping "
                f"the meaning intact: {ha_resp.speech_text}"
            )
            try:
                response = self._llm.chat(
                    [{"role": "user", "content": rephrase_prompt}], system_prompt=None,
                )
            except Exception as e:
                logger.warning("Rephrase LLM call failed, falling back to verbatim: %s", e)
                response = ha_resp.speech_text
        return response

    def run_turn(self, persona_id: str, text: str) -> Iterator[TurnEvent]:
        persona = self._get_persona(persona_id)
        # target_id is this turn's routing id (history/display/dispatch). The
        # caller resolves the active persona before calling run_turn, so it
        # always equals persona_id here; kept as a named concept to mirror chat().
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

        history = self._history_load(target_id)
        system_prompt = self._system_prompt(persona)
        history.append({"role": "user", "content": text})

        # House-word / HA delegation.
        from match_keywords import match_keyword_prefix
        hw_matched, residual = match_keyword_prefix(text, persona.house_words or [])
        if hw_matched and self._ha:
            response = self._ha_turn(persona, target_id, residual)
            yield TurnEvent("reply_delta", {"persona_id": target_id, "text": response})
        else:
            chunks: list[str] = []
            for chunk in self._llm.chat_stream(history, system_prompt=system_prompt):
                chunks.append(chunk)
                yield TurnEvent("reply_delta", {"persona_id": target_id, "text": chunk})
            response = "".join(chunks)

        self._speak(target_id, response)
        history.append({"role": "assistant", "content": response})
        if len(history) > self._history_cap:
            history[:] = history[-self._history_cap:]
        self._history_save(target_id)
        yield TurnEvent("reply_done", {"persona_id": target_id, "text": response})
