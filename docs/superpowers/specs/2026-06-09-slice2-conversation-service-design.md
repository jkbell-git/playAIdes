# Slice 2 — ConversationService + the DisplayChannel keystone

- **Status:** Designed 2026-06-09 (brainstormed) · ready for implementation plan
- **Type:** Migration slice (strangler-fig) — slice 2 of the backend/frontend re-architecture
- **Parent (standing reference):** `docs/superpowers/specs/2026-06-09-backend-frontend-architecture-redesign.md`
  (migration sequence §"Migration sequence", item 2). This slice pins the items that doc deferred:
  the WS frame envelope, the turn-event shape, and exactly where `ConversationService` cleaves off
  `PlayAIdes`.
- **Related:** `2026-06-08-integrations-console-v1-design.md` (slice 1 — the package layout this matches:
  root `backend/` with `api/ clients/ stores/`); `model_interfaces.py` (the `LLMInterface` seam this
  extends with streaming).

## Context

`PlayAIdes` (`playAIdes.py`, 945 lines) and `IncarnationServer` (`incarnation_server.py`, 564 lines) are
knotted by a **circular dependency**: the server calls *into* the domain
(`on_message_callback = self._handle_incarnation_message`), and the domain calls *back* into the server
(`self.incarnation_server.broadcast_to_persona(...)`). Neither can be reworked without disturbing the
other. This is the actual problem the redesign exists to fix — not file size.

Slice 2 is the **keystone**: it extracts the conversation turn into a `ConversationService` and breaks
the circle with one dependency-inversion port (`DisplayChannel`), the exact pattern already used for the
LLM (`LLMInterface` → `OpenAICompatLLM`/`MockLLM`). After this slice, the domain no longer imports the
server, and the remaining `PlayAIdes`/`IncarnationServer` decomposition (slices 3+) can proceed freely.

## Goal

1. Extract the conversation turn (`PlayAIdes.chat`) into a transport-free **`ConversationService`** that
   yields a **turn-event stream** (`reply_started → reply_delta* → reply_done`).
2. Introduce the **`DisplayChannel` port** so the domain pushes to the browser through an injected
   interface, not a concrete server reference — **breaking the circular dependency**.
3. Add **LLM streaming** (`LLMInterface.chat_stream`) so a streaming turn emits real deltas; deterministic
   replies are the single-delta special case.
4. Wire **both transports over the one service**: the WS live path and a new REST
   `POST /api/v1/personas/{id}/messages` (drains the same generator → assembled reply).

Behavior is **ported, not redesigned** (strangler-fig). The vanilla viewer needs **no change** in this
slice (see §Streaming).

## Scope

`_handle_incarnation_message` dispatches **15 message types**. Slice 2 carves out **exactly one**:

| Carved out now (slice 2) | Stays in `_handle_incarnation_message` (slices 3+) |
|---|---|
| **`user_input` → `ConversationService.run_turn`** | `get_personas`, `get_persona`, `create/update/delete_persona`, `set_active_persona`, `dismiss_persona` → *PersonaService* |
| | `model_uploaded`, `animation_uploaded`, `status`(ready/loaded/finished) → *AvatarService* |
| | `design_voice`, `test_voice` → *Voice / TTS-consumer migration* |

**Out of scope** (explicitly): the other 14 message types; the TTS-consumer migration to
`/v1/audio/speech` (its own later slice — see §"Out of scope" below); fixing the RED full-suite (rides
with the TTS slice, which removes the offending `voicebox_client` import); the `incarnation_server.py`
route decomposition; any persona/history/skill/avatar service extraction.

## Design

### 1. `ConversationService`  (`backend/services/conversation.py`)

A near-verbatim port of `PlayAIdes.chat`'s orchestration — the **proxy** the architecture spec describes:
precedence **phrase-trigger → house-words/HA → LLM**, then push the reply, then persist history. No
FastAPI, no `requests`, no `voicebox_client`. Collaborators are injected at construction.

```python
class ConversationService:
    def __init__(self, *, personas, history, skills, llm, ha, display, speaker, args): ...

    def run_turn(self, persona_id: str, text: str) -> Iterator[TurnEvent]:
        """Yield the turn-event stream for one user turn. Pushes avatar/subtitle
        frames via `display` as it goes; persists history at the end."""
```

`run_turn` mirrors today's `chat` exactly:
1. **Phrase trigger** (`match_phrase_trigger`) → `skills.dispatch(...)` → a **single-delta** turn carrying
   the skill's announce text (usually empty). `reply_started → reply_delta("") → reply_done`.
2. **History load** (`history.load(persona_id)`), append the user message.
3. **House-word / HA** (`match_keyword_prefix` on `persona.house_words`) → `ha.converse(...)`, optional
   LLM rephrase. Non-streaming → a **single-delta** turn.
4. **Else LLM** → if the turn streams, `llm.chat_stream(...)` yields many `reply_delta`s; otherwise
   `llm.chat(...)` is one delta.
5. **Speak**: at `reply_done`, push the subtitle + fire TTS (see §"Speak path", §Streaming).
6. **Persist**: append assistant reply, trim to `CHAT_HISTORY_CAP`, `history.save(persona_id)`.

The system-prompt construction and the HA conversation-id cache move into the service with the turn.

### 2. The `DisplayChannel` port  (`backend/ports/display.py`)

```python
class DisplayChannel(Protocol):
    def push(self, persona_id: str, event_type: str, payload: dict) -> None: ...
```

Identical signature to today's `IncarnationServer.broadcast_to_persona`. The transport provides the
implementation; the service depends only on the Protocol.

```python
# implemented in / near incarnation_server.py
class WebSocketDisplayChannel:           # wraps the existing broadcast
    def __init__(self, server): self._server = server
    def push(self, persona_id, event_type, payload):
        self._server.broadcast_to_persona(persona_id, event_type, payload)
```

`broadcast_to_persona` is already **thread-safe** (`_safe_send_text` uses
`asyncio.run_coroutine_threadsafe`), so the service may run on a worker thread and push frames as they
arrive without touching the WS event loop. Every `self.incarnation_server.broadcast_to_persona(...)` in
the carved-out turn path becomes `self.display.push(...)`. **This is the one inversion that breaks the
circle.** A `MockLLM`-style recording fake (`RecordingDisplayChannel`) backs the unit tests.

### 3. The turn-event model + WS envelope

Today's WS frame (from `broadcast_to_persona`) is **`{"type": <str>, "payload": <dict>}`** — slice 2
keeps that envelope and adds three frame `type`s:

| `TurnEvent` | WS frame | Notes |
|---|---|---|
| `reply_started` | `{type:"reply_started", payload:{persona_id}}` | turn begins |
| `reply_delta` | `{type:"reply_delta", payload:{persona_id, text}}` | one chunk (many for a streaming LLM turn; one for deterministic) |
| `reply_done` | `{type:"reply_done", payload:{persona_id, text}}` | `text` = the assembled full reply |

These are **additive**. The existing `assistant_message` and `start_lip_sync` frames are still emitted at
`reply_done` exactly as today, so the vanilla viewer keeps working unchanged (see §Streaming).

### 4. Both transports, one brain

- **WS live path:** the `user_input` branch of `_handle_incarnation_message` calls
  `ConversationService.run_turn(...)` and the **WS adapter** forwards each `TurnEvent` as a frame via
  `DisplayChannel`, plus the compat `assistant_message`/`start_lip_sync` at `reply_done`.
- **REST adapter** (`backend/api/conversation.py`, an `APIRouter` mounted like slice-1's
  `integrations.py`): `POST /api/v1/personas/{id}/messages` `{ "text": "..." }` → **drains** the
  generator and returns the assembled reply `{ "reply": "..." }`. Behind the existing API-key dep
  (`backend/api/deps.py`). This proves "one `run_turn`, two adapters" cheaply.

### 5. Streaming  (`LLMInterface.chat_stream`)

Add to the LLM seam (in the existing `model_interfaces.py`; re-homing to `backend/clients/llm.py` is
deferred — see Open items):

```python
def chat_stream(self, messages, system_prompt=None) -> Iterator[str]:
    """Yield reply chunks. OpenAICompatLLM sets stream:true and parses SSE
    deltas; MockLLM yields its single mock string as one chunk."""
```

**Pinned decision — how streaming coexists with TTS and the viewer:**
- The **LLM text streams** as `reply_delta` frames over WS as chunks arrive.
- **TTS fires once on the assembled reply at `reply_done`** — slice 2 does **not** chunk TTS. (TTS is the
  TTS-consumer migration's concern; the architecture spec puts TTS internals out of this slice's scope.)
- **The vanilla viewer needs no change in slice 2.** The subtitle keeps coming from the existing
  `assistant_message` frame (pushed once at `reply_done`); the new `reply_*` frames are additive and the
  viewer ignores them until a later, focused frontend follow-up adopts per-token rendering. So the
  *capability* to stream is built and tested here; *browser-side delta rendering* is deferred.

### 6. The speak path

`speak_as_persona` decomposes cleanly:
- `display.push(persona_id, "assistant_message", {text, persona_id})` — the subtitle (compat frame).
- if avatar: `display.push(persona_id, "start_lip_sync", {url: <tts-proxy-url>})` — a `DisplayChannel`
  push (no voicebox import).
- else (CLI-only): the injected **`speaker`** seam fires TTS. Today that is
  `PlayAIdes.tts.generate_speech_stream(...)` via the already-injectable `args.tts`. Slice 2 injects the
  **existing** speak/TTS behavior as the `speaker` collaborator, so `ConversationService` **never imports
  `voicebox_client`** — the dead interface stays referenced only in `playAIdes.py` until the TTS slice
  replaces it.

### 7. Wiring (where things are constructed)

In `PlayAIdes.__init__` (or `main.py` startup), after `self.incarnation_server` exists:
```python
display  = WebSocketDisplayChannel(self.incarnation_server)   # the port impl
conv     = ConversationService(
    personas=<persona accessor>, history=<history load/save>, skills=<dispatch>,
    llm=self.llm, ha=self.ha_client, display=display, speaker=<existing speak seam>, args=self.args,
)
```
The `user_input` branch delegates to `conv.run_turn`; the REST router is constructed with the same
`conv`. The injected collaborators (`personas`/`history`/`skills`/`speaker`) are **thin adapters over the
still-living `PlayAIdes`** — strangler-fig. They become real `PersonaService`/`AvatarService` in slices 3+.

## Testing strategy

- **`ConversationService` unit tests (hermetic, no GPU, no network):** drive `run_turn` against
  `MockLLM` (+ new `chat_stream`), `_MockHAClient`, a fake `speaker`, fake `personas`/`history`/`skills`,
  and a **`RecordingDisplayChannel`** that asserts the right `reply_started/delta/done` +
  `assistant_message`/`start_lip_sync` frames fire, in order, for each path (phrase-trigger /
  house-word / streaming LLM / non-streaming LLM). These run in the plain test container — the new module
  imports no `voicebox_client`, so the RED-suite cause does not touch it.
- **REST boundary:** `TestClient` test for `POST /api/v1/personas/{id}/messages` (auth, full-reply drain,
  error shape `{"detail": ...}`).
- **WS smoke:** a turn over the WS produces the expected frame sequence (the no-thread
  `incarnation_server` fixture from `tests/integration`).
- **Live verification:** run a real turn against the **running harness** (kokoro voicebox, backend
  `:8765`) and confirm Silver actually speaks — evidence before "done."

## Package layout (new/changed files)

```
backend/ports/__init__.py           (new)
backend/ports/display.py            (new)  DisplayChannel Protocol
backend/services/__init__.py        (new)
backend/services/conversation.py    (new)  ConversationService + TurnEvent
backend/api/conversation.py         (new)  REST router: POST /api/v1/personas/{id}/messages
model_interfaces.py                 (edit) + chat_stream on LLMInterface/OpenAICompatLLM/MockLLM
incarnation_server.py               (edit) + WebSocketDisplayChannel; user_input branch delegates;
                                            mount the conversation router
playAIdes.py                        (edit) construct DisplayChannel + ConversationService; user_input
                                            path delegates to run_turn; speak pushes via the port
```

## Out of scope (named, so they aren't assumed done)

- **TTS-consumer migration to `/v1/audio/speech`** — the finished voicebox removed the `voicebox_client`
  Python API (`voicebox_client/` has no source; `PersonaTTS`/`VoiceboxClient` are gone) and is now
  HTTP-OpenAI only. playAIdes' TTS consumer therefore needs migrating to a thin `clients/tts.py` against
  `/v1/audio/speech` + `/v1/audio/voice_design`, repointing `/api/tts/proxy` + `/api/speakers/.../ref_audio`,
  and `speaker_uuid → voice`. **This is its own later slice** (architecture-spec item 4) and is what fixes
  the RED full-suite (it removes the dead import). Slice 2 keeps the legacy path working via the seam.
- **Browser-side per-token rendering** of `reply_delta` — a focused frontend follow-up.
- **The other 14 WS message types** and the `incarnation_server` route decomposition — slices 3+.

## Open items (for the implementation plan)

- **Turn consumption / threading.** Exact mechanism for consuming `run_turn`'s generator off the WS event
  loop (likely a worker thread; pushes are already thread-safe via `_safe_send_text`). Confirm the
  blocking-LLM-on-the-async-loop question the current sync `chat` already has.
- **REST router mount point.** Match how slice-1's `integrations.py` router is mounted into the app.
- **`chat_stream` SSE parsing.** The `OpenAICompatLLM` streaming body (`stream:true`, parse
  `choices[].delta.content`); reuse the `reasoning_content` fallback.
- **Persona accessor shape.** Whether `run_turn` takes a persona-id and looks it up via the injected
  `personas` accessor, or the active persona is resolved as today (single-operator).
- **Re-homing `model_interfaces.py` → `backend/clients/llm.py`** (per the layer model) vs. editing in
  place — deferred; default is edit-in-place to keep the slice focused.

## Self-Review

- **Placeholder scan:** none. Genuinely-open choices are collected under "Open items," not hidden as TBDs.
- **Internal consistency:** the `DisplayChannel` signature matches `broadcast_to_persona`; the WS envelope
  matches today's `{type, payload}`; the single-delta mapping makes deterministic and streaming replies
  the same shape on both transports; the speak path keeps `assistant_message` so the viewer is unchanged.
- **Scope:** one branch (`user_input`) carved out; everything else explicitly deferred. Appropriately
  sized for a single plan.
- **Ambiguity:** the streaming↔TTS↔viewer interaction is pinned (subtitles via additive `reply_*`; the
  existing `assistant_message` keeps the viewer working; TTS whole at `reply_done`; browser delta-render
  deferred). "Breaks the circular dependency" is made concrete (the one `DisplayChannel` inversion).
