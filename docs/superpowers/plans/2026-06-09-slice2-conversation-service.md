# Slice 2 — ConversationService + DisplayChannel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the conversation turn from the `PlayAIdes` god-object into a transport-free `ConversationService`, and break the `incarnation_server ⇄ PlayAIdes` circular dependency with one `DisplayChannel` push port.

**Architecture:** A new `backend/services/conversation.py` holds `ConversationService.run_turn(persona_id, text)`, a faithful port of `PlayAIdes.chat`'s proxy (phrase-trigger → house-words/HA → LLM) that *yields* a turn-event stream (`reply_started → reply_delta* → reply_done`). The domain pushes to the browser through an injected `DisplayChannel` Protocol (`backend/ports/display.py`) instead of a concrete server reference. Both transports run over the one generator: the WS path forwards events as frames; a new REST endpoint drains the generator to a full reply. Behavior is ported, not redesigned — the viewer is unchanged.

**Tech Stack:** Python 3.14, FastAPI, pydantic, pytest. Tests run in Docker via `bin/test pytest <args>` (hermetic — plain test container) or, for tests that import `playAIdes` (which top-level-imports the not-yet-migrated `voicebox_client`), inside the running harness backend container which has voicebox baked in.

**Spec:** `docs/superpowers/specs/2026-06-09-slice2-conversation-service-design.md`
**Parent architecture:** `docs/superpowers/specs/2026-06-09-backend-frontend-architecture-redesign.md`

---

## File Structure

| File | New/Edit | Responsibility |
|---|---|---|
| `backend/ports/__init__.py` | new | package marker |
| `backend/ports/display.py` | new | `DisplayChannel` Protocol (server→client push) |
| `backend/services/__init__.py` | new | package marker |
| `backend/services/conversation.py` | new | `TurnEvent` + `ConversationService.run_turn` (the ported proxy) |
| `backend/api/conversation.py` | new | REST router: `POST /api/v1/personas/{id}/messages` (drains `run_turn`) |
| `model_interfaces.py` | edit | add `chat_stream` to `LLMInterface` / `OpenAICompatLLM` / `MockLLM` |
| `incarnation_server.py` | edit | add `WebSocketDisplayChannel`; mount the conversation router |
| `playAIdes.py` | edit | construct `DisplayChannel` + `ConversationService`; route `speak_as_persona`/`_skill_send` through the port; `chat()` + the `user_input` WS branch delegate to `run_turn` |
| `tests/conftest.py` | edit | add `RecordingDisplayChannel` + `recording_display` fixture |

**Test-running note (the RED-suite reality):** `playAIdes.py` top-level-imports `voicebox_client`, which the plain test container lacks (fixed later in the TTS-migration slice). So:
- **Hermetic tests** (Tasks 1, 2, 3, 4, 5, 8 — they import `backend.*` / `model_interfaces`, never `playAIdes`): run with `bin/test pytest <path> -v`.
- **`playAIdes`-importing tests** (Tasks 6, 7): run inside the harness backend container, which has voicebox:
  `docker compose -f docker-compose.harness.yml exec -T backend pytest <path> -v`

---

### Task 1: `DisplayChannel` port + `WebSocketDisplayChannel`

**Files:**
- Create: `backend/ports/__init__.py` (empty), `backend/ports/display.py`
- Modify: `incarnation_server.py` (add `WebSocketDisplayChannel` near the top-level, after imports)
- Modify: `tests/conftest.py` (add `RecordingDisplayChannel` + fixture)
- Test: `tests/unit/test_display_channel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_display_channel.py
from incarnation_server import WebSocketDisplayChannel


class _StubServer:
    def __init__(self):
        self.calls = []
    def broadcast_to_persona(self, persona_id, cmd_type, payload=None):
        self.calls.append((persona_id, cmd_type, payload))


def test_websocket_display_channel_forwards_push_to_broadcast():
    server = _StubServer()
    ch = WebSocketDisplayChannel(server)
    ch.push("silver", "reply_delta", {"text": "hi"})
    assert server.calls == [("silver", "reply_delta", {"text": "hi"})]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_display_channel.py -v`
Expected: FAIL — `ImportError: cannot import name 'WebSocketDisplayChannel'`

- [ ] **Step 3: Write the port + the wrapper**

```python
# backend/ports/__init__.py
```
(empty file)

```python
# backend/ports/display.py
"""The single server→client push port. The domain depends on this Protocol;
the transport implements it. Injecting it breaks the incarnation_server ⇄
PlayAIdes circular dependency (the same pattern as LLMInterface → OpenAICompatLLM)."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class DisplayChannel(Protocol):
    def push(self, persona_id: str, event_type: str, payload: dict) -> None:
        """Push one frame to the displays bound to `persona_id`."""
        ...
```

Add to `incarnation_server.py` (top-level, after the existing imports — placed here, not in `backend/`, because the implementation belongs to the transport layer):

```python
class WebSocketDisplayChannel:
    """DisplayChannel implementation backed by the WS broadcast.

    Thread-safe: broadcast_to_persona uses asyncio.run_coroutine_threadsafe,
    so a worker thread running a turn can push frames without touching the
    event loop."""

    def __init__(self, server):
        self._server = server

    def push(self, persona_id: str, event_type: str, payload: dict) -> None:
        self._server.broadcast_to_persona(persona_id, event_type, payload)
```

Add to `tests/conftest.py` (after `StubIncarnationServer`):

```python
class RecordingDisplayChannel:
    """DisplayChannel test double — records every (persona_id, type, payload) push."""

    def __init__(self):
        self.pushes: list[tuple[str, str, dict]] = []

    def push(self, persona_id: str, event_type: str, payload: dict) -> None:
        self.pushes.append((persona_id, event_type, payload))


@pytest.fixture
def recording_display() -> "RecordingDisplayChannel":
    return RecordingDisplayChannel()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_display_channel.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/ports/__init__.py backend/ports/display.py incarnation_server.py tests/conftest.py tests/unit/test_display_channel.py
git commit -m "feat(slice2): add DisplayChannel port + WebSocketDisplayChannel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `LLMInterface.chat_stream`

**Files:**
- Modify: `model_interfaces.py` (add `chat_stream` to `LLMInterface`, `OpenAICompatLLM`, `MockLLM`)
- Test: `tests/unit/test_llm_stream.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_llm_stream.py
import json
import responses
from model_interfaces import MockLLM, OpenAICompatLLM


def test_mock_llm_chat_stream_yields_single_chunk():
    out = list(MockLLM().chat_stream([{"role": "user", "content": "hello"}]))
    assert out == ["Mock Response: I heard you say 'hello'."]


@responses.activate
def test_openai_chat_stream_parses_sse_deltas():
    body = (
        'data: {"choices":[{"delta":{"content":"He"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"llo"}}]}\n\n'
        'data: [DONE]\n\n'
    )
    responses.add(
        responses.POST, "http://fake-llm:11434/v1/chat/completions",
        body=body, status=200, content_type="text/event-stream",
    )
    llm = OpenAICompatLLM(base_url="http://fake-llm:11434/v1", model="m")
    out = list(llm.chat_stream([{"role": "user", "content": "hi"}]))
    assert out == ["He", "llo"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_llm_stream.py -v`
Expected: FAIL — `AttributeError: 'MockLLM' object has no attribute 'chat_stream'`

- [ ] **Step 3: Implement `chat_stream`**

In `model_interfaces.py`, add the abstract method to `LLMInterface` (after `chat`):

```python
    def chat_stream(self, messages: List[Dict[str, str]],
                    system_prompt: Optional[str] = None) -> "Iterator[str]":
        """Yield reply chunks. Default: one chunk wrapping chat() (non-streaming
        backends). Streaming backends override to yield token deltas."""
        yield self.chat(messages, system_prompt=system_prompt)
```

Add `Iterator` to the typing import at the top:

```python
from typing import List, Dict, Optional, Iterator
```

Override in `OpenAICompatLLM` (after `chat`):

```python
    def chat_stream(self, messages: List[Dict[str, str]],
                    system_prompt: Optional[str] = None) -> Iterator[str]:
        url = f"{self.base_url}/chat/completions"
        msgs: List[Dict[str, str]] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        payload = {"model": self.model, "messages": msgs, "stream": True}
        try:
            with requests.post(url, json=payload, timeout=self.timeout, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
        except requests.RequestException as e:
            logger.error("Error streaming from LLM at %s: %s", url, e)
            raise LLMError(f"LLM stream failed: {e}") from e
```

Add `import json` at the top of `model_interfaces.py` (alongside the existing imports).

`MockLLM` inherits the base `chat_stream` (one chunk wrapping `chat`) — no override needed; the base default already satisfies `test_mock_llm_chat_stream_yields_single_chunk`.

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_llm_stream.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add model_interfaces.py tests/unit/test_llm_stream.py
git commit -m "feat(slice2): add chat_stream to the LLM seam

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ConversationService` — TurnEvent + phrase-trigger path

**Files:**
- Create: `backend/services/__init__.py` (empty), `backend/services/conversation.py`
- Test: `tests/unit/test_conversation_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_conversation_service.py
from persona import Persona
from backend.services.conversation import ConversationService, TurnEvent
from conftest import VALID_PERSONA


def _persona(**overrides):
    return Persona(**{**VALID_PERSONA, **overrides})


def _service(persona, *, llm=None, ha=None, speak=None, dispatch=None, history=None):
    hist = history if history is not None else {}
    spoken = []
    dispatched = []
    svc = ConversationService(
        get_persona=lambda pid: persona,
        history_load=lambda pid: hist.setdefault(pid, []),
        history_save=lambda pid: None,
        dispatch=dispatch or (lambda *a: dispatched.append(a)),
        llm=llm,
        ha=ha,
        speak=speak or (lambda tid, text: spoken.append((tid, text))),
        ha_default_agent_id=None,
        history_cap=80,
    )
    svc._spoken = spoken
    svc._dispatched = dispatched
    return svc


def test_phrase_trigger_dispatches_and_yields_silent_single_delta():
    persona = _persona(
        triggers=[{"on": {"phrase": "show camera"},
                   "do": {"skill": "show_pip", "params": {"source": "cam.1"}}}],
        skills=["show_pip"],
    )
    svc = _service(persona)
    events = list(svc.run_turn("testbot", "show camera now"))

    types = [e.type for e in events]
    assert types == ["reply_started", "reply_delta", "reply_done"]
    assert events[1].payload["text"] == ""           # silent
    assert events[2].payload["text"] == ""
    assert svc._dispatched == [("testbot", "show_pip", {"source": "cam.1"})]
    assert svc._spoken == []                          # phrase path never speaks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_conversation_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.conversation'`

- [ ] **Step 3: Write the service skeleton + phrase path**

```python
# backend/services/__init__.py
```
(empty file)

```python
# backend/services/conversation.py
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

        # ── Deterministic phrase trigger (precedence: phrase → house_words → LLM) ──
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_conversation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/__init__.py backend/services/conversation.py tests/unit/test_conversation_service.py
git commit -m "feat(slice2): ConversationService phrase-trigger path

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `ConversationService` — streaming LLM path

**Files:**
- Modify: `backend/services/conversation.py` (replace the Task-3 placeholder tail with the real LLM path + `_system_prompt`)
- Test: `tests/unit/test_conversation_service.py` (add)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_conversation_service.py

class _StreamLLM:
    def __init__(self, chunks):
        self._chunks = list(chunks)
    def chat(self, messages, system_prompt=None):
        return "".join(self._chunks)
    def chat_stream(self, messages, system_prompt=None):
        for c in self._chunks:
            yield c


def test_llm_path_streams_deltas_speaks_and_persists():
    persona = _persona(persona_voice={"speaker_uuid": "v-1"})
    history = {}
    svc = _service(persona, llm=_StreamLLM(["Hel", "lo"]), history=history)
    events = list(svc.run_turn("testbot", "hi"))

    assert [e.type for e in events] == [
        "reply_started", "reply_delta", "reply_delta", "reply_done",
    ]
    assert [e.payload["text"] for e in events[1:3]] == ["Hel", "lo"]
    assert events[-1].payload["text"] == "Hello"          # assembled reply
    assert svc._spoken == [("testbot", "Hello")]          # TTS whole, at reply_done
    assert history["testbot"][-2:] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello"},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_conversation_service.py::test_llm_path_streams_deltas_speaks_and_persists -v`
Expected: FAIL — the assembled `reply_done` text is `""` and nothing was spoken (placeholder tail still runs).

- [ ] **Step 3: Replace the placeholder tail with the real LLM path**

In `backend/services/conversation.py`, replace the two placeholder lines at the end of `run_turn` (the `# LLM / house-word paths land in Tasks 4 & 5.` block) with:

```python
        history = self._history_load(target_id)
        system_prompt = self._system_prompt(persona)
        history.append({"role": "user", "content": text})

        # ── House-word / HA delegation lands in Task 5; LLM path here ──
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
```

Add the `_system_prompt` helper to the class (faithful port of `PlayAIdes.chat`, typos preserved to keep behavior identical):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_conversation_service.py -v`
Expected: PASS (phrase-trigger + streaming tests both green)

- [ ] **Step 5: Commit**

```bash
git add backend/services/conversation.py tests/unit/test_conversation_service.py
git commit -m "feat(slice2): ConversationService streaming LLM path

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `ConversationService` — house-word / HA path

**Files:**
- Modify: `backend/services/conversation.py` (insert the house-word branch before the LLM path; add `_ha_turn`)
- Test: `tests/unit/test_conversation_service.py` (add)

- [ ] **Step 1: Write the failing test**

```python
# add to tests/unit/test_conversation_service.py
from conftest import _MockHAClient   # the HA stub already in conftest


def test_house_word_delegates_to_ha_single_delta():
    persona = _persona(house_words=["house"])
    ha = _MockHAClient()
    ha.script(speech_text="Lights on.", conversation_id="c-1")
    svc = _service(persona, llm=_StreamLLM(["unused"]), ha=ha)
    events = list(svc.run_turn("testbot", "house turn on the lights"))

    assert [e.type for e in events] == ["reply_started", "reply_delta", "reply_done"]
    assert events[1].payload["text"] == "Lights on."
    assert ha.calls[0]["text"] == "turn on the lights"      # house word stripped
    assert svc._spoken == [("testbot", "Lights on.")]


def test_house_word_with_no_residual_short_circuits():
    persona = _persona(house_words=["house"])
    ha = _MockHAClient()
    svc = _service(persona, llm=_StreamLLM(["unused"]), ha=ha)
    events = list(svc.run_turn("testbot", "house"))
    assert events[1].payload["text"] == "What about the house?"
    assert ha.calls == []                                   # no HA call
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_conversation_service.py -k house_word -v`
Expected: FAIL — the LLM path runs instead (`reply_delta` text is `"unused"`, HA never called).

- [ ] **Step 3: Insert the house-word branch + `_ha_turn`**

In `run_turn`, replace the LLM block (everything from `chunks: list[str] = []` down to `response = "".join(chunks)`) with the branch:

```python
        # ── House-word / HA delegation ──
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
```

Add the `_ha_turn` helper (faithful port of the HA block in `PlayAIdes.chat`):

```python
    def _ha_turn(self, persona, target_id: str, residual: str) -> str:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_conversation_service.py -v`
Expected: PASS (phrase + streaming + 2 house-word tests, all green)

- [ ] **Step 5: Commit**

```bash
git add backend/services/conversation.py tests/unit/test_conversation_service.py
git commit -m "feat(slice2): ConversationService house-word/HA path

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire `PlayAIdes` — DisplayChannel + ConversationService; `chat()` delegates

**Files:**
- Modify: `playAIdes.py` — `__init__` (construct `self.display`, `self.conversation`); `speak_as_persona` + `_skill_send` (push via `self.display`); `chat` (delegate to `run_turn`)
- Test: `tests/unit/test_playaides_chat.py` (existing — must stay green; this is a regression gate)

- [ ] **Step 1: Run the existing chat tests first to capture the green baseline**

Run: `docker compose -f docker-compose.harness.yml exec -T backend pytest tests/unit/test_playaides_chat.py -v`
Expected: PASS (record the count — this must not regress).

- [ ] **Step 2: Construct the port + service in `__init__`**

In `playAIdes.py` `__init__`, immediately after the `self.incarnation_server = ... if args.use_avatar else None` block, add:

```python
        from incarnation_server import WebSocketDisplayChannel
        from backend.services.conversation import ConversationService
        self.display = (
            WebSocketDisplayChannel(self.incarnation_server)
            if self.incarnation_server is not None else None
        )
        self.conversation = ConversationService(
            get_persona=lambda pid: self.current_persona,
            history_load=self._load_history,
            history_save=self._save_history,
            dispatch=self._dispatch_skill,
            llm=self.llm,
            ha=self.ha_client,
            speak=self.speak_as_persona,
            ha_default_agent_id=self.args.ha_default_agent_id,
            history_cap=CHAT_HISTORY_CAP,
        )
```

(`self.ha_client` is set later in `__init__` today — move this block to **after** the `self.ha_client` assignment so it is non-None when present. Place it just before the `for persona in args.persona:` load loop.)

- [ ] **Step 3: Route `speak_as_persona` + `_skill_send` through `self.display`**

In `speak_as_persona`, replace the two `self.incarnation_server.broadcast_to_persona(...)` calls and their guards:

```python
        if self.display is not None:
            self.display.push(
                target_id, "assistant_message", {"text": text, "persona_id": target_id},
            )
```
and
```python
        if self.args.use_avatar and self.display:
            import urllib.parse
            safe_text = urllib.parse.quote(text)
            proxy_url = (
                f"http://localhost:8765/api/tts/proxy?text={safe_text}"
                f"&speaker_id={voice.speaker_uuid}"
            )
            if self.current_persona.language:
                proxy_url += f"&language={urllib.parse.quote(self.current_persona.language)}"
            logger.info(f"Sending start_lip_sync: {proxy_url}")
            self.display.push(target_id, "start_lip_sync", {"url": proxy_url})
```

In `_skill_send`, replace:

```python
        if self.display is not None:
            self.display.push(persona_id, cmd_type, payload)
```

- [ ] **Step 4: Make `chat()` delegate to `run_turn`**

Replace the body of `PlayAIdes.chat` with the thin draining wrapper (preserves the `-> str` contract for `main.py` and existing tests):

```python
    def chat(self, user_input: str, persona_id: Optional[str] = None) -> str:
        if not self.current_persona:
            return "No persona loaded."
        target_id = persona_id or self.current_persona.name.strip().lower().replace(" ", "_")
        reply = ""
        for ev in self.conversation.run_turn(target_id, user_input):
            if ev.type == "reply_done":
                reply = ev.payload.get("text", "")
        return reply
```

- [ ] **Step 5: Run the existing chat tests — verify no regression**

Run: `docker compose -f docker-compose.harness.yml exec -T backend pytest tests/unit/test_playaides_chat.py -v`
Expected: PASS — same count as Step 1. (The `FakeTTS.stream_calls` and `StubIncarnationServer.commands` assertions still hold: `chat` → `run_turn` → `speak_as_persona` → `self.display.push` → `broadcast_to_persona` on the stub.)

- [ ] **Step 6: Commit**

```bash
git add playAIdes.py
git commit -m "feat(slice2): route PlayAIdes through DisplayChannel + ConversationService

chat() now drains ConversationService.run_turn; speak_as_persona/_skill_send
push via the DisplayChannel port. The domain no longer references the concrete
server for push — the circular dependency is broken.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: WS adapter — `user_input` branch delegates to `run_turn`

**Files:**
- Modify: `playAIdes.py` — the `user_input` branch of `_handle_incarnation_message`
- Test: `tests/integration/test_conversation_ws.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_conversation_ws.py
import pytest


@pytest.mark.usefixtures("no_incarnation", "tmp_personas_dir")
def test_user_input_drives_run_turn_and_pushes_frames(monkeypatch):
    from playAIdes import PlayAIdes, PlayAIdesArgs
    from model_interfaces import MockLLM

    ai = PlayAIdes(PlayAIdesArgs(persona=["personas/testbot/persona.json"],
                                 use_avatar=True, llm=MockLLM()))
    server = ai.incarnation_server          # the StubIncarnationServer
    server.commands.clear()

    ai._handle_incarnation_message({"type": "user_input",
                                    "payload": {"text": "hello there"}})

    types = [c[0] for c in server.commands]
    assert "reply_started" in types
    assert "reply_done" in types
    assert "assistant_message" in types     # the subtitle still fires (viewer unchanged)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.harness.yml exec -T backend pytest tests/integration/test_conversation_ws.py -v`
Expected: FAIL — only `assistant_message` is recorded; no `reply_started`/`reply_done` (the old branch calls `self.chat`, which drains silently without forwarding turn events).

- [ ] **Step 3: Rewrite the `user_input` branch**

In `_handle_incarnation_message`, replace the `if msg_type == "user_input":` block with:

```python
        if msg_type == "user_input":
            text = (payload.get("text") or "").strip()
            if not text:
                return
            persona_id = (payload.get("persona_id") or "").strip() or None
            target_id = persona_id or (
                self.current_persona.name.strip().lower().replace(" ", "_")
                if self.current_persona else None
            )
            if not target_id:
                return
            try:
                for ev in self.conversation.run_turn(target_id, text):
                    if self.display is not None:
                        self.display.push(target_id, ev.type, ev.payload)
            except Exception as e:
                logger.exception(f"user_input run_turn failed: {e}")
            return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.harness.yml exec -T backend pytest tests/integration/test_conversation_ws.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_conversation_ws.py
git commit -m "feat(slice2): WS user_input delegates to run_turn, forwards turn events

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: REST adapter — `POST /api/v1/personas/{id}/messages`

**Files:**
- Create: `backend/api/conversation.py`
- Modify: `incarnation_server.py` (mount the router; set `app.state.conversation_service`)
- Modify: `playAIdes.py` (`__init__`: stash the service on the app for the router)
- Test: `tests/integration/test_conversation_rest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_conversation_rest.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api.conversation import router
from backend.services.conversation import TurnEvent


class _FakeConv:
    def run_turn(self, persona_id, text):
        yield TurnEvent("reply_started", {"persona_id": persona_id})
        yield TurnEvent("reply_delta", {"persona_id": persona_id, "text": "Hi "})
        yield TurnEvent("reply_delta", {"persona_id": persona_id, "text": text})
        yield TurnEvent("reply_done", {"persona_id": persona_id, "text": f"Hi {text}"})


def _client():
    app = FastAPI()
    app.state.conversation_service = _FakeConv()
    app.include_router(router)
    return TestClient(app)


def test_post_message_drains_to_full_reply(with_api_key):
    client = _client()
    resp = client.post("/api/v1/personas/silver/messages",
                       json={"text": "there"},
                       headers={"Authorization": f"Bearer {with_api_key}"})
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Hi there"}


def test_post_message_requires_auth():
    resp = _client().post("/api/v1/personas/silver/messages", json={"text": "x"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/integration/test_conversation_rest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.api.conversation'`

- [ ] **Step 3: Write the REST router**

```python
# backend/api/conversation.py
"""REST adapter for the conversation turn (slice 2). Drains the same
ConversationService.run_turn generator the WS path streams, returning the
assembled reply (the stream:false path). Mirrors backend/api/integrations.py:
a self-contained APIRouter behind require_api_key, mounted by the app."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.api.deps import require_api_key

router = APIRouter(
    prefix="/api/v1",
    tags=["conversation"],
    dependencies=[Depends(require_api_key)],
)


class MessageIn(BaseModel):
    text: str


class MessageOut(BaseModel):
    reply: str


@router.post("/personas/{persona_id}/messages", response_model=MessageOut)
def post_message(persona_id: str, body: MessageIn, request: Request) -> MessageOut:
    conv = request.app.state.conversation_service
    reply = ""
    for ev in conv.run_turn(persona_id, body.text):
        if ev.type == "reply_done":
            reply = ev.payload.get("text", "")
    return MessageOut(reply=reply)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/integration/test_conversation_rest.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Mount the router + stash the service**

In `incarnation_server.py`, alongside the existing `from backend.api.integrations import router as integrations_router`:

```python
from backend.api.conversation import router as conversation_router
```
and alongside `self.app.include_router(integrations_router)`:

```python
        self.app.include_router(conversation_router)
```

In `playAIdes.py` `__init__`, immediately after `self.conversation = ConversationService(...)`:

```python
        if self.incarnation_server is not None:
            self.incarnation_server.app.state.conversation_service = self.conversation
```

- [ ] **Step 6: Commit**

```bash
git add backend/api/conversation.py incarnation_server.py playAIdes.py tests/integration/test_conversation_rest.py
git commit -m "feat(slice2): REST /api/v1/personas/{id}/messages drains run_turn

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Live verification + docs sweep

**Files:**
- Modify: `CONTINUITY.md` (mark slice 2 done in TODO + add a Decision)

- [ ] **Step 1: Confirm the hermetic suite is green**

Run: `bin/test pytest tests/unit/test_display_channel.py tests/unit/test_llm_stream.py tests/unit/test_conversation_service.py tests/integration/test_conversation_rest.py -v`
Expected: PASS (all).

- [ ] **Step 2: Confirm the playAIdes-wiring suite is green (harness container)**

Run: `docker compose -f docker-compose.harness.yml exec -T backend pytest tests/unit/test_playaides_chat.py tests/integration/test_conversation_ws.py -v`
Expected: PASS (no regression in the existing chat tests).

- [ ] **Step 3: Live end-to-end — Silver actually speaks via the keystone**

The harness backend auto-reloads (watchfiles) on the edits. Drive a real turn through the REST adapter and confirm the avatar speaks on the kiosk:

```bash
curl -sS -X POST http://localhost:8765/api/v1/personas/silver/messages \
  -H "Authorization: Bearer $PLAYAIDES_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"text":"say hello in one short sentence"}'
```
Expected: `{"reply":"..."}` (non-empty), and on the kiosk/`:5173` view Silver speaks the line (subtitle + lip-sync) — confirming `run_turn` → `speak_as_persona` → `DisplayChannel` → WS → viewer + the (still-legacy) TTS proxy all work end-to-end.

- [ ] **Step 4: Update CONTINUITY.md**

Tick the slice-2 TODO item (`- [x] **Slice 2 …`) and add under `## Decisions`:

```markdown
- [2026-06-09] **Slice 2 (ConversationService + DisplayChannel) shipped.** Extracted the
  conversation turn from PlayAIdes.chat into `backend/services/conversation.py` (yields a
  reply_started→delta*→done turn-event stream); introduced the `DisplayChannel` push port
  (`backend/ports/display.py` + `WebSocketDisplayChannel`) — the domain no longer references
  the concrete server for push, breaking the incarnation_server⇄PlayAIdes circular dependency.
  Added `LLMInterface.chat_stream`; WS forwards turn events, REST `POST /api/v1/personas/{id}/messages`
  drains them. Viewer unchanged (subtitle still via `assistant_message`). TTS-consumer migration
  to `/v1/audio/speech` + the RED full-suite fix remain their own next slice.
```

- [ ] **Step 5: Commit**

```bash
git add CONTINUITY.md
git commit -m "docs(slice2): mark ConversationService/DisplayChannel slice done

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- `ConversationService.run_turn` + ported proxy → Tasks 3 (phrase), 4 (LLM/stream), 5 (house-word/HA). ✔
- `DisplayChannel` port + `WebSocketDisplayChannel` → Task 1; routed through in Task 6. ✔
- Turn-event model + `{type, payload}` WS envelope → `TurnEvent` (Task 3), forwarded in Task 7. ✔
- Streaming (`chat_stream`; subtitles stream; TTS whole at `reply_done`) → Task 2 + Task 4 (`_speak` after deltas). ✔
- Both transports → WS (Task 7) + REST (Task 8) over one `run_turn`. ✔
- Speak path (pushes via port; TTS seam injected, no `voicebox_client` in the service) → Task 6 + `speak` injected in Task 3. ✔
- Strangler-fig (collaborators injected from living `PlayAIdes`; `chat()` preserved) → Task 6. ✔
- Out of scope (TTS migration, RED-suite fix, other 14 msg types) → untouched; noted in Task 9 decision. ✔

**2. Placeholder scan:** No `TBD`/`TODO`/"handle errors"/"similar to". Every code step shows complete code; every run step shows the exact command + expected outcome. ✔

**3. Type consistency:** `DisplayChannel.push(persona_id, event_type, payload)` is used identically in `WebSocketDisplayChannel`, `RecordingDisplayChannel`, `_skill_send`, and the WS adapter. `TurnEvent(type, payload)` and the three type strings (`reply_started`/`reply_delta`/`reply_done`) are consistent across Tasks 3–8. `ConversationService.__init__` keyword params (`get_persona`, `history_load`, `history_save`, `dispatch`, `llm`, `speak`, `ha`, `ha_default_agent_id`, `history_cap`) match every construction site (the test `_service` helper and the Task-6 wiring). `chat_stream(messages, system_prompt)` matches between `model_interfaces.py` and its callers. ✔

**Note on test execution:** hermetic tests (Tasks 1,2,3,4,5,8) run via `bin/test`; tests importing `playAIdes` (Tasks 6,7) run in the harness backend container (has voicebox). This split is the current RED-suite reality and is resolved by the later TTS-consumer migration slice.
