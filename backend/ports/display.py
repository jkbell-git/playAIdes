"""The single server→client push port. The domain depends on this Protocol;
the transport implements it. Injecting it breaks the incarnation_server ⇄
PlayAIdes circular dependency (the same pattern as LLMInterface → OpenAICompatLLM)."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class DisplayChannel(Protocol):
    def push(self, persona_id: str, event_type: str, payload: dict) -> None:
        """Push one frame to the displays bound to `persona_id`."""
        ...
