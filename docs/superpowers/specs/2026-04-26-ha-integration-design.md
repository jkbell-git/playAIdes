# Home Assistant Integration — Design Spec

**Date:** 2026-04-26
**Branch:** TBD (suggested: `ha_integration`)
**Status:** ready for implementation planning
**Scope:** Phase 1 (trigger ergonomics) + Phase 2 (persona → HA skills via explicit delegation)
**Deferred to future specs:** Phase 3 (HA → persona events), Phase 4 (HACS conversation-agent custom_component)

---

## 1. Goals, scope, non-goals

### What this is

Make playAIdes addressable from Home Assistant in two directions:

1. **Phase 1 — Trigger ergonomics.** HA can swap, dismiss, and read the state of the playAIdes backend over HTTP. Combined with HA's existing `fully_kiosk.load_url` / `browser_mod.navigate` services and the already-shipping `?persona=<id>` URL param, this lets HA fully own "show persona X on TV Y" without playAIdes needing any TV identity model.
2. **Phase 2 — Skills via explicit delegation.** The user can invoke HA's own conversation agent through the persona by prefixing an utterance with a configured "house word" (e.g. "house turn off the kitchen lights"). The residual text is forwarded to HA's `/api/conversation/process`; HA's LLM handles tool reasoning + entity actuation; HA's response is spoken via the persona's TTS / lip-sync (verbatim by default, optionally rephrased).

### Non-goals (this spec)

- **No TV identity model.** TVs are anonymous WebSocket connections to playAIdes, as today. HA decides which TV to address via Browser Mod / Fully Kiosk; playAIdes neither knows nor cares.
- **No persona-LLM tool-calling.** The current `LLMInterface` (text-in/text-out) is unchanged. HA's LLM does the tool work.
- **No automatic routing.** No regex-trigger heuristics, no LLM-as-router. Delegation is explicit via `house_words` — the user opts in per utterance.
- **No direct HA entity reads/writes from playAIdes.** All HA interaction goes through the conversation agent. `ha_client.py` is structured so direct entity calls *could* be added later, but Phase 2 stays in the LLM-decision loop.
- **No HA-driven persona events.** "Door opened → persona says welcome" is Phase 3, deferred. See § 7.
- **No HACS custom_component.** "Persona is HA's conversation agent" is Phase 4, deferred. See § 7.

### Tech stack

Same as Phases 1–5 of the viewer redesign — Pydantic v2, FastAPI, vanilla JS + Vitest, Three.js. New deps: `responses` (test-only HTTP mock — only if not already present in dev deps).

---

## 2. Architecture overview

```
┌──────────────────┐       ┌──────────────────────────┐       ┌─────────────────┐
│ Home Assistant   │ ───►  │  IncarnationServer       │ ────► │ Browser tabs    │
│                  │       │  (existing FastAPI:8765) │       │ (existing WS)   │
│ • rest_command   │       │                          │       │                 │
│ • Fully Kiosk    │       │  + 3 new HTTP endpoints  │       │                 │
│   load_url       │       │    (Phase 1)             │       │                 │
│                  │  ◄──  │                          │       │                 │
│ /api/conversation│       │  + ha_client.py          │       │                 │
│   /process       │       │  + chat() routing on     │       │                 │
│   (HA's LLM)     │       │    house_words           │       │                 │
└──────────────────┘       └──────────────────────────┘       └─────────────────┘
        ▲                              │
        │                              ▼
        │                         (existing) Ollama LLM, TTS, Whisper
        │                              │
        └────── Phase 2 calls ─────────┘
               (only when house_words match)
```

**Two flows added.** Phase 1 is HA → playAIdes (trigger). Phase 2 is playAIdes → HA, but only on explicit user-initiated delegation. Both flows are independent — Phase 1 ships standalone if Phase 2 is descoped.

**Deployment.** Single host as today. HA runs wherever it normally runs and reaches playAIdes at `http://<playaides-host>:8765`. Local network only — no public exposure assumed.

---

## 3. Components

Six discrete units. Three new files; the rest extend existing code.

### 3.1 `incarnation_server.py` extensions — three new HTTP routes + auth

Existing FastAPI app gets three new routes, all behind a `require_api_key` dependency that checks `Authorization: Bearer ${PLAYAIDES_API_KEY}`:

| Route | Body | Behavior | Response |
|---|---|---|---|
| `POST /api/personas/{id}/activate` | none | calls existing `_handle_incarnation_message({type:"set_active_persona", payload:{id}})` synchronously | `{ok, active_persona_id}` on success, `{ok:false, error}` on unknown id |
| `POST /api/dismiss` | none | dispatches `{type:"dismiss_persona"}` through the same path | `{ok}` |
| `GET /api/state` | none | reads in-memory state | `{active_persona_id, state, bound_client_count}` |

`require_api_key` is skipped (with a startup warning) when `PLAYAIDES_API_KEY` is unset, for dev convenience. New code lives in `incarnation_server.py` itself — surface is small enough not to warrant a new file.

### 3.2 `ha_client.py` *(new file, ~80 LOC)*

Single class wrapping the HA REST conversation endpoint:

```python
class HAClient:
    def __init__(self, base_url: str, token: str, timeout: float = 5.0): ...

    def converse(
        self,
        text: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ConversationResponse: ...

    def health_check(self) -> bool: ...

@dataclass
class ConversationResponse:
    success: bool
    speech_text: str
    conversation_id: Optional[str]
    error_code: Optional[str]   # e.g. "no_intent_match", "ha_unreachable"
```

POSTs to `{base_url}/api/conversation/process` with the long-lived bearer token. Pure HTTP wrapper, no playAIdes internals — fully unit-testable with `responses` or `requests-mock`.

### 3.3 `persona.py` schema extensions

Three new optional fields on the existing `Persona` Pydantic v2 model:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `house_words` | `List[str]` | `[]` | Trigger phrases that route the residual text to HA. Empty = HA delegation disabled. |
| `rephrase_ha_response` | `bool` | `False` | If true, HA's response text is passed back through the persona's own LLM ("Rephrase this in Silver's voice: …") before TTS. |
| `ha_agent_id` | `Optional[str]` | `None` | Which HA conversation agent to address. None = use `HA_DEFAULT_AGENT_ID` env var. |

Backwards compatible: existing `persona.json` files load unchanged.

### 3.4 `playAIdes.py` `chat()` routing branch

At the top of `chat(user_input, persona_id)`, after persona resolution and **before** the LLM call:

1. Strip-match `user_input` against `current_persona.house_words`. Match logic: case-insensitive, leading/trailing whitespace tolerated, the house word must appear as the first non-whitespace token (prefix match — *not* anywhere in the sentence) so "house turn off lights" matches but "play the song House of the Rising Sun" doesn't. Implemented as a small new helper module `match_keywords.py` (mirrors the semantics of the frontend's `transcriptMatcher.js` `matchWakeWord` function but Python-side; both files reference the same documented rules so they stay aligned). On no match, fall through to the existing LLM path; nothing else changes.
2. On match → compute `residual` (text after the matched house word, leading whitespace stripped).
3. If residual is empty, speak a fixed default phrase `"What about the house?"` and return — no HA call. (A per-persona override field can be added later if it matters; v1 keeps it hardcoded.)
4. Otherwise call `ha_client.converse(residual, agent_id=persona.ha_agent_id or HA_DEFAULT_AGENT_ID, conversation_id=cached_for_persona)`. The `conversation_id` is cached per-persona in memory for the lifetime of the active chat session and cleared on persona dismiss or swap — this lets HA's conversation agent maintain multi-turn context within a session, like "turn off the lights … no wait, just the kitchen ones."
5. If `success=False`, take the `speech_text` field as a user-friendly fallback message and skip rephrase. Otherwise:
   - If `persona.rephrase_ha_response`: pass `speech_text` through `self.llm.chat([rephrase prompt])`. On LLM failure, fall back to verbatim and log a warning.
   - Else: take `speech_text` verbatim.
6. The downstream code (history append, `_save_history`, broadcast `assistant_message`, `start_lip_sync` emit) is bit-identical to the existing LLM path. One injection point at the top, one shared exit at the bottom.

### 3.5 `PlayAIdesArgs` + env wiring

New optional CLI args (each with an env-var fallback):

| Arg | Env var | Default | Purpose |
|---|---|---|---|
| `--ha-url` | `HA_URL` | unset | HA base URL, e.g. `http://homeassistant.local:8123`. If unset, all HA features disabled with a startup log. |
| `--ha-token` | `HA_TOKEN` | unset | HA long-lived access token. Required when `HA_URL` is set. |
| `--ha-default-agent-id` | `HA_DEFAULT_AGENT_ID` | unset | Conversation agent to address when a persona has no `ha_agent_id`. |
| `--api-key` | `PLAYAIDES_API_KEY` | unset | Bearer token for incoming HA → playAIdes calls. Unset = dev mode (no auth). |

`HAClient` is constructed in `PlayAIdes.__init__` only if both `HA_URL` and `HA_TOKEN` are set. Personas with non-empty `house_words` but no `HAClient` (or no `ha_agent_id` AND no default) log a startup warning and behave as if `house_words` were empty.

### 3.6 `docs/ha-integration.md` *(new doc, no code)*

HA-side configuration reference — copy-pasteable YAML. Sections:

- Long-lived token creation walkthrough (Settings → Profile → Long-Lived Access Tokens).
- `rest_command` snippets for each Phase 1 endpoint.
- Sample automations using each (e.g. "show Silver in the kitchen at 7 AM").
- `fully_kiosk.load_url` and `browser_mod.navigate` examples for cold-start kiosk launches with `?persona=<id>`.
- How to find your `agent_id` (Settings → Voice Assistants → click an assistant → entity_id pattern is `conversation.<name>`).
- A persona-config example with `house_words`, `ha_agent_id`, and `rephrase_ha_response`.
- Manual smoke test recipe (see § 5.4).

---

## 4. Data flow

### 4.1 Scenario A — HA swaps persona on a running TV (Phase 1)

```
HA automation                     playAIdes                        Browser tab(s)
─────────────                     ─────────                        ──────────────
rest_command:                                                      (already showing
  POST /api/personas/silver/      ─►  require_api_key dep          Rin, WS connected)
       activate                          ▼
  Bearer ${PLAYAIDES_API_KEY}        _handle_incarnation_message(
                                       {type:"set_active_persona",
                                        payload:{id:"silver"}})
                                          ▼
                                       set_persona("silver")
                                          ▼
                                       broadcast_to_persona +
                                       broadcast_to_all (existing      ─►  set_active_persona
                                       Phase 4 routing)                    persona_active
                                          ▼                                load_model
                                       200 {ok:true,                       (existing flow)
                                            active_persona_id:
                                            "silver"}
HA receives 200 ◄─────────────────────────
```

No browser reload. The new endpoint synthesizes the same WS message a browser would have sent.

### 4.2 Scenario B — Persona delegates an utterance to HA (Phase 2)

User has woken Silver and says: **"house turn off the kitchen lights"**

```
Frontend                                      playAIdes                          HA
(in conversation, wake-word stripped)
────────────────────────────────────          ─────────                          ──
WS user_input                            ─►   chat("house turn off the
{text:"house turn off the kitchen              kitchen lights", persona_id)
       lights"}                                    ▼
                                               strip-match house_words
                                               ["house"] on text
                                                   ▼
                                               match → residual = "turn off
                                               the kitchen lights"
                                                   ▼
                                               ha_client.converse(             ─►  POST /api/conversation
                                                 residual,                          /process
                                                 agent_id=                          {text, agent_id,
                                                   persona.ha_agent_id              conversation_id}
                                                   or HA_DEFAULT_AGENT_ID,
                                                 conversation_id=                  (HA's LLM does tool
                                                   per-persona cached)              reasoning, calls
                                                                                    light.turn_off)
                                                   ▼                           ◄── 200 {response:
                                               ConversationResponse                 {speech:{plain:
                                               .speech_text = "OK"                   {speech:"OK"}}}}
                                                   ▼
                                               if persona.rephrase_ha_response:
                                                   self.llm.chat([rephrase prompt])
                                                   → "All taken care of, hon."
                                               else:
                                                   speech = "OK"
                                                   ▼
                                               history.append({
                                                 role:"assistant",
                                                 content:speech})
                                               _save_history()
                                                   ▼
                                       (existing path) broadcast assistant_message,
                                                   start_lip_sync, save history
                                                   ▼
                                              ─► WS assistant_message → browser TTS + lipsync
```

The right-most third (history, broadcast, lipsync) is identical to a normal LLM response. Only the *content source* changes.

### 4.3 Failure modes

| What breaks | Where caught | Behavior |
|---|---|---|
| `PLAYAIDES_API_KEY` missing on HA call | `require_api_key` dependency | 401 to HA; HA's `rest_command` logs the error |
| `HA_URL` unset, persona has `house_words` | `PlayAIdes.__init__` | startup warning; chat() treats house_words as empty |
| `HA_URL` set but unreachable mid-conversation | `ha_client.converse()` | `ConversationResponse(success=False, speech_text="I can't reach the house right now.")`; spoken verbatim |
| HA returns `no_intent_match` | `ha_client` parses error_code | fallback string spoken: "I didn't catch that — try rephrasing?" |
| HA returns 401/500 | `ha_client` | generic fallback string + log warning with status code |
| `house_words` matched, residual empty (user said only "house") | `chat()` routing | speak per-persona prompt phrase; no HA call |
| `rephrase_ha_response=True` but persona LLM call fails | `chat()` rephrase branch | fall back to verbatim HA text + log warning; never block on rephrase failure |

---

## 5. Testing approach

Same TDD posture as Phases 1–5. Frontend isn't touched, so JS tests stay at 89.

### 5.1 Phase 1 — HTTP endpoints
**File: `tests/integration/test_ha_trigger_endpoints.py` (new)**
- Auth dependency: missing header → 401; wrong token → 401; correct token → 200; `PLAYAIDES_API_KEY` unset → 200 + warning.
- `POST /api/personas/{id}/activate`: known id → 200 with `active_persona_id`, calls into `_handle_incarnation_message` (verify by command-log assertion, same pattern as existing `test_set_active_persona_ws.py`).
- Unknown id → 4xx with the same shape as a WS-driven failure (mirror `persona_changed.ok=false`).
- `POST /api/dismiss`: 200, dispatches dismiss path.
- `GET /api/state`: returns expected shape from a known fixture state.

### 5.2 Phase 2 — `ha_client.py`
**File: `tests/unit/test_ha_client.py` (new)**
Pure unit tests with `responses`:
- Success → parses `speech_text` correctly.
- HA returns `no_intent_match` → `ConversationResponse.success=False`, error_code preserved.
- 401 / 500 → `success=False` with generic message.
- Network error / timeout → `success=False` with "I can't reach the house" string.
- `health_check()` returns true on 200, false on anything else.

### 5.3 Phase 2 — `chat()` routing
**File: `tests/integration/test_ha_routing.py` (new)** — uses a new `mock_ha_client` fixture (parallel to existing `fake_tts`):
- `house_words=["house"]`, input "house turn off lights" → ha_client called once, response spoken verbatim. No persona LLM call.
- Same persona, input "how are you?" → no ha_client call, persona LLM normal path.
- `rephrase_ha_response=True` → both ha_client AND persona LLM called. Final assistant_message uses LLM output.
- House word matched but residual empty → no ha_client call, default phrase spoken.
- ha_client returns `success=False` → fallback message spoken, no rephrase even if enabled.
- Rephrase enabled but persona LLM raises → verbatim HA text used, warning logged.
- `house_words=[]` (default) → ha_client never consulted regardless of input content.

### 5.4 New test fixtures in `tests/conftest.py`
```python
@pytest.fixture
def mock_ha_client():
    """Inject scripted ConversationResponse values."""

@pytest.fixture
def with_api_key(monkeypatch):
    """Set PLAYAIDES_API_KEY for endpoints that require it."""
```

### 5.5 Schema validation
Extend the existing `Persona` schema test class to assert defaults and that a stripped-down legacy `persona.json` (no HA fields) loads cleanly.

### 5.6 Manual smoke recipe (in `docs/ha-integration.md`)
1. Real HA at `homeassistant.local:8123` with one conversation agent configured (Settings → Voice Assistants).
2. Long-lived token in `HA_TOKEN`, agent_id in `HA_DEFAULT_AGENT_ID`, key in `PLAYAIDES_API_KEY`.
3. One persona with `house_words: ["house"]`.
4. Curl each Phase 1 endpoint, verify state changes match the WS broadcast.
5. Talk/type "house, what's the temperature in the kitchen" → verify lipsync fires, verify HA logs show conversation hit.

### 5.7 Test count targets
- Going in: 138 Python / 89 Vitest.
- Going out: ~155–160 Python (~17–22 new across the four new test areas) / 89 Vitest. Exact count depends on how many failure variants we cover in `test_ha_routing.py`.

---

## 6. Configuration reference

### 6.1 playAIdes env vars

| Env var | Required when | Purpose |
|---|---|---|
| `HA_URL` | any HA feature is used | HA base URL |
| `HA_TOKEN` | `HA_URL` is set | HA long-lived bearer token |
| `HA_DEFAULT_AGENT_ID` | a persona uses HA without setting `ha_agent_id` | default conversation agent |
| `PLAYAIDES_API_KEY` | recommended in any deployment | Bearer token for HA → playAIdes endpoints. Unset = dev mode (no auth) + warning |

### 6.2 Persona schema additions (`persona.json`)

```jsonc
{
  "name": "Silver",
  "wake_words": ["Hey Silver"],
  "dismiss_words": ["Goodnight Silver"],
  "house_words": ["house"],
  "rephrase_ha_response": false,
  "ha_agent_id": "conversation.openai_assist",
  ...
}
```

All three HA fields are optional. Empty `house_words` = HA delegation disabled.

### 6.3 HA-side config (canonical example)

```yaml
# configuration.yaml
rest_command:
  playaides_activate_persona:
    url: "http://playaides.local:8765/api/personas/{{ persona_id }}/activate"
    method: POST
    headers:
      Authorization: !secret playaides_api_key
    timeout: 5

  playaides_dismiss:
    url: "http://playaides.local:8765/api/dismiss"
    method: POST
    headers:
      Authorization: !secret playaides_api_key
    timeout: 5
```

---

## 7. Out of scope (deferred to future specs)

These are intentionally not part of this spec. Pick one up later by spawning a fresh brainstorm session referencing this section.

### 7.1 Phase 3 — HA → Persona event-driven automations

**Problem:** HA wants to push events into playAIdes that aren't user-initiated. Examples: "front door opened → Silver says 'welcome home'", "morning routine → Silver greets the room", "smoke detector → all personas play an urgent animation."

**Approach sketch:** New `POST /api/event` endpoint accepting `{event, persona_id?, action, data}`. Action types include `say` (assistant_message text), `play_animation`, `swap_persona` (subset of Phase 1), `interrupt` (cancel current activity). State-machine integration is the open design question — what happens if the persona is already SPEAKING or LISTENING when an event lands? Queue, interrupt, drop? Per-persona allow-list controls which HA events can drive which actions.

**Why deferred:** Each policy choice (queue vs interrupt vs drop) has UX implications worth their own brainstorm. Phase 1 + 2 don't depend on Phase 3 — they ship cleanly without it.

### 7.2 Phase 4 — HACS `homeassistant-playaides` custom_component

**Problem:** HA voice satellites (M5 Atom Echo, ESPHome voice, etc.) deliver audio through HA's Assist pipeline. To reach those satellites, playAIdes must register as a `ConversationEntity` inside HA. There is no external/REST way to do this — HA only accepts conversation agents implemented as a Python `custom_component` running inside HA itself.

**Approach sketch:** A separate repo (likely `homeassistant-playaides`) installable via HACS. The custom_component subclasses `homeassistant.components.conversation.ConversationEntity` and proxies `_async_handle_message(user_input, chat_log)` calls to playAIdes over HTTP/WebSocket. Persona selection happens via the entity's `agent_id` (one HA conversation entity per persona, perhaps).

**Why deferred:** Different codebase entirely (Python in HA's runtime), different distribution model (HACS), different testing surface. Worth doing once Phase 1 + 2 prove the integration shape works.

### 7.3 Persona-LLM native tool-calling

**Problem:** If we ever want the persona's *own* LLM to make tool calls (not just delegate to HA's LLM), we'd need to extend `LLMInterface` to support `tools=[...]` and parse tool-call response shapes.

**Why deferred:** The user explicitly chose "route to HA's conversation agent" instead of native tool-calling. Revisit only if HA's conversation agent proves too restrictive (e.g. you want the persona to use non-HA tools, or you want different model behavior than your HA conversation agent provides).

### 7.4 Multi-TV identity model

**Problem:** Today TVs are anonymous WS connections. A future need to address a specific TV (e.g. "say this on the kitchen TV only") would require a TV-id concept.

**Why deferred:** HA owns the "which TV" question via Browser Mod / Fully Kiosk URL routing. Until you hit a use case where playAIdes needs to push to a *specific* TV (not just broadcast to all bound clients), this isn't worth building.

---

## 8. Free-text notes (append over time)

Use this section to capture stray thoughts about Phases 3 / 4 between now and when they're picked up. Notes here persist in git and survive session resets.

(Empty — add as ideas arise.)
