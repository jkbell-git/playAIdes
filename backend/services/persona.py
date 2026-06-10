"""PersonaService — the persona domain owner (spec 2026-06-10, D1–D7).

Composes the two pure-I/O stores. Every write round-trips through the
Persona/Trigger Pydantic models (D3), so an invalid document can never reach
disk; pydantic ValidationError propagates as itself (the router maps it to
422). The history cache + cap live here — single owner; PlayAIdes reads the
cache through its chat_histories property for the history_loaded WS frame.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from persona import Persona

logger = logging.getLogger(__name__)


class PersonaNotFound(Exception):
    """No persona with that id."""


class PersonaExists(Exception):
    """create() collided with an existing persona (D7: 409, not overwrite)."""


class PersonaActive(Exception):
    """delete() refused: the persona is currently active (D7: 409)."""


def slug(name: str) -> str:
    """The persona-id slug rule (single home, moved from create_persona)."""
    return name.strip().lower().replace(" ", "_")


class PersonaService:
    def __init__(self, persona_store, history_store,
                 active_persona_id: Callable[[], Optional[str]],
                 history_cap: int = 80):
        self._personas = persona_store
        self._history_store = history_store
        self._active_persona_id = active_persona_id
        self._history_cap = history_cap
        self._histories: Dict[str, List[dict]] = {}

    # ── CRUD ──────────────────────────────────────────────────────────────
    def list(self) -> List[dict]:
        """Every readable persona doc with "id" injected. Corrupt files are
        logged and skipped — one bad file must not take down the list."""
        out = []
        for pid in self._personas.list_ids():
            try:
                doc = self._personas.read(pid)
            except Exception as e:
                logger.error("Error reading persona %s: %s", pid, e)
                continue
            doc["id"] = pid
            out.append(doc)
        return out

    def get(self, persona_id: str) -> dict:
        try:
            doc = self._personas.read(persona_id)
        except KeyError:
            raise PersonaNotFound(persona_id)
        doc["id"] = persona_id
        return doc

    def get_model(self, persona_id: str) -> Persona:
        """Typed by-id load for internal consumers (ConversationService, D6)."""
        try:
            data = self._personas.read(persona_id)
        except KeyError:
            raise PersonaNotFound(persona_id)
        return Persona(**data)

    def create(self, name: str, description: str) -> dict:
        persona_id = slug(name)
        if self._personas.exists(persona_id):
            raise PersonaExists(persona_id)
        model = Persona(
            name=name,
            back_ground=description,
            psyche={"traits": []},
            gender="Female",
            language="English",
        )
        doc = model.model_dump()
        self._personas.write(persona_id, doc)
        doc["id"] = persona_id
        return doc

    def update(self, persona_id: str, data: dict) -> dict:
        if not self._personas.exists(persona_id):
            raise PersonaNotFound(persona_id)
        data = dict(data)
        data.pop("id", None)
        doc = Persona(**data).model_dump()   # ValidationError propagates (422)
        self._personas.write(persona_id, doc)
        doc["id"] = persona_id
        return doc

    def delete(self, persona_id: str) -> None:
        if not self._personas.exists(persona_id):
            raise PersonaNotFound(persona_id)
        if self._active_persona_id() == persona_id:
            raise PersonaActive(persona_id)
        self._personas.delete(persona_id)      # rmtree removes chat history too
        self._histories.pop(persona_id, None)  # no resurrection on re-create

    # ── History (cache + cap, moved from PlayAIdes — single owner) ──
    @property
    def histories(self) -> Dict[str, List[dict]]:
        """The in-memory cache. PlayAIdes' chat_histories property returns
        this same dict; the history_loaded activation frame reads it."""
        return self._histories

    def load_history(self, persona_id: str) -> List[dict]:
        if persona_id in self._histories:
            return self._histories[persona_id]
        history = self._history_store.read(persona_id)
        if len(history) > self._history_cap:
            history = history[-self._history_cap:]
        self._histories[persona_id] = history
        return history

    def save_history(self, persona_id: str) -> None:
        """Persist the cached list (atomic via the store)."""
        self._history_store.write(persona_id, self._histories.get(persona_id, []))

    def delete_history(self, persona_id: str) -> None:
        self._histories.pop(persona_id, None)
        self._history_store.delete(persona_id)

    # ── Triggers (D2: whole-list replace, no row ids) ────────────────────
    def get_triggers(self, persona_id: str) -> List[dict]:
        return self.get(persona_id).get("triggers") or []

    def replace_triggers(self, persona_id: str, triggers: List[dict]) -> List[dict]:
        """Validate the WHOLE persona with the new list spliced in (each row
        through Trigger, and the doc stays coherent — spec D2/D3), write,
        return the new list."""
        try:
            doc = self._personas.read(persona_id)
        except KeyError:
            raise PersonaNotFound(persona_id)
        doc.pop("id", None)
        doc["triggers"] = triggers
        validated = Persona(**doc).model_dump()  # ValidationError propagates
        self._personas.write(persona_id, validated)
        return validated["triggers"]
