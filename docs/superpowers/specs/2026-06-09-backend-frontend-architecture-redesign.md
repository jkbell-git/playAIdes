# Backend / Frontend Architecture Redesign — clean separation behind a stable contract

- **Status:** Designed 2026-06-09 (brainstormed) · standing architecture reference
- **Type:** Architecture decision (standing reference) + migration strategy
- **Related:** `docs/frontend-architecture.md` (React-per-page), `docs/VOICEBOX_HTTP_API.md` (TTS
  contract), `docs/superpowers/specs/2026-06-08-integrations-console-v1-design.md` (the first slice),
  `model_interfaces.py` (`LLMInterface` — the existing seam this generalizes)

## Context

playAIdes is a **proven POC** that grew organically. It works, and **no one is using it yet** — which
makes this the right moment to re-architect cleanly, before more is built on the current shape. Two
"god-objects" carry most of the system and are tangled together:

- **`incarnation_server.py`** (`IncarnationServer`) — the FastAPI app, **all** routes defined inline as
  nested closures in one `_setup_routes()` method, the WebSocket handler, static-file serving, and the
  TTS/STT HTTP proxies. Mixes transport + serving + proxying + realtime in one ~830-line class.
- **`playAIdes.py`** (`PlayAIdes`) — a ~44 KB domain class: persona CRUD, voice/avatar setup, chat
  history, the conversation orchestrator (`chat`), skill dispatch, event handling, and a **~277-line
  `_handle_incarnation_message`** WebSocket dispatcher.

The root problem is **not file size — it's a circular dependency.** The server calls *into* the domain
(`on_message_callback`), and the domain calls *back into* the server to push to the browser
(`self.incarnation_server.broadcast_to_persona(...)`). Transport and domain are knotted, so neither can
be reworked without disturbing the other — and the frontend reaches into whatever shape happens to
exist.

**The goal that drives every decision below:** a **clean separation** anchored by a **stable API
contract**, so the frontend is built *once* against that contract and survives backend rework, and the
backend internals can be reorganized freely behind it. The contract is the durable artifact — think of
it as the **ICD** between frontend and backend.

## Goal

1. Define a **stable, versioned HTTP/WS API contract** (the front/back ICD) that protects the frontend
   from backend churn.
2. Define a **layered backend** (transport → domain services → external clients → stores) with
   one-directional dependencies, replacing the two god-objects.
3. Define a **strangler-fig migration** that realizes this incrementally — the Integrations Console as
   the first clean slice, existing surfaces migrated one at a time behind the stable contract — with
   **no big-bang rewrite** and the POC's behavior preserved (ported, not redesigned away).

This is a **standing reference**, not an implementation plan. Each migration slice gets its own
spec/plan; the console is slice 1.

## Key decisions

- **Contract = hybrid by transport, split by nature.** REST for everything request/response; a single
  narrow WebSocket for the one genuinely-realtime, bidirectional, streaming loop (the talking avatar).
  Each operation lives on exactly one transport. *(Rejected: unified WS-RPC — weak on
  documentability/versioning; all-REST + push-only WS — awkward for the streaming avatar loop.)*
- **Conversation is a server-side orchestrator (a "proxy"), kept as a first-class domain service.**
  playAIdes intercepts each turn and chooses **deterministic skill trigger → deterministic
  house-word/HA routing → LLM**. Those *static triggers exist only because the backend sits in the
  middle*; the redesign preserves this, it does not push conversation to the frontend.
- **One turn event model serves both streaming and non-streaming.** A turn is
  `reply_started → reply_delta* → reply_done` (+ interleaved avatar/status push). A streaming LLM turn
  emits many deltas; a deterministic trigger/house-word reply is the **single-delta** special case. A
  `stream:false` consumer gets the assembled full reply in one REST response. "Support both ways" = two
  thin transport adapters over one `ConversationService`.
- **Layer-first organization + one dependency-inversion port.** Layers: `api → services → clients /
  stores`, dependencies pointing **down only**. The single inversion is a **`DisplayChannel` push
  port** (the domain depends on an interface for server→client push; the transport implements it) — the
  minimal change that unknots the circular dependency. *(Rejected: feature-first vertical slices — a
  bigger reorg than the incremental migration wants; full hexagonal ports-for-everything —
  over-engineered for a single-operator app. The model clients are already ports-in-spirit via
  `LLMInterface`.)*
- **REST conventions:** a `/api/v1` prefix (versioned from day one) and the uniform error shape
  `{"detail": "..."}` — which is both FastAPI's default and what voicebox returns, so the whole stack
  speaks one error dialect.
- **Frontend:** the perf-critical vanilla Three.js viewer stays vanilla; new PC/mobile pages are React;
  both consume a **shared, typed API-client module** (the ICD's frontend side). FastAPI's auto-generated
  OpenAPI schema (`/docs`) is the machine-readable ICD and the future codegen path.
- **Migration:** strangler-fig, in-place. Console first (greenfield reference impl), then the
  conversation loop, then persona/avatar/event services, then the server decomposition falls out.
- **Out of scope / owned elsewhere:** the TTS/STT internals and the voicebox `/v1/*` consumer migration
  are owned by a separate concurrent session. This design leaves a clean seam for them (`TTSClient` /
  `STTClient` + proxy routers) but does not touch that code.

## Architecture

### Layer model

Dependencies point **downward only**. Nothing in a lower layer imports a higher one.

```
┌─ api/        FastAPI routers (REST) · ws live channel · static serving · deps (auth)
│              THIN: validate → call a service → shape the response. No domain logic.
│                  │ depends on services + ports
├─ services/   ConversationService (the proxy: triggers → house-words/HA → LLM, yields the
│              turn event stream) · PersonaService · AvatarService · EventService.
│              THE BRAIN: no FastAPI, no `requests`. Clients/stores injected at construction.
│                  │ depends on clients + stores + ports
├─ clients/    Model services: LLMClient (OpenAICompat, + streaming), TTSClient (voicebox),
│              STTClient (whisper). Provider seam: HAClient + integration providers.
│              Uniform HTTP clients; deployment-configured base URLs.
├─ stores/     persona files · chat history · config_store · secrets_store. Persistence only.
└─ ports/      DisplayChannel (server→client push). Services depend on it; api/ implements it.
```

**Why the `DisplayChannel` port (the one inversion).** Today the domain holds a reference to the
concrete server and calls `broadcast_to_persona`. Instead, the domain depends on a tiny interface:

```python
# ports/display.py
class DisplayChannel(Protocol):
    def push(self, persona_id: str, event_type: str, payload: dict) -> None: ...
```

The transport implements it (`api/` provides a `WebSocketDisplayChannel` wrapping the WS broadcast),
and it is **injected** into the services at startup. Dependencies now flow one way; the circle is
broken. This is the exact pattern already used for the LLM (`LLMInterface` → `OpenAICompatLLM` /
`MockLLM`), applied to the outbound push direction — and tests already fake it
(`StubIncarnationServer` records calls to `.commands`).

**Target package layout** (illustrative — the exact package root, e.g. a top-level `playaides/`
package vs. root-level packages, is locked by slice 1 since it sets the import namespace; existing
root modules like `ha_client.py` / `model_interfaces.py` are re-homed or re-exported as their slice
migrates):

```
api/        app.py · deps.py · personas.py · voices.py · conversation.py · integrations.py
            · launch.py · events.py · state.py · ws.py
services/   conversation.py · personas.py · avatar.py · events.py
clients/    llm.py · tts.py · stt.py · ha.py · providers/{base,fake,homeassistant,registry}.py
stores/     personas.py · history.py · config_store.py · secrets_store.py
ports/      display.py
```

### The API contract (the ICD)

**REST — everything request/response, resource-oriented, under `/api/v1`:**

| Resource | Operations (illustrative; exact paths locked per slice) |
|---|---|
| personas | list/create/get/update/delete · `activate` · upload `model` · upload `animations` |
| voices | `design` · list · `preview` |
| conversation | `POST /api/v1/personas/{id}/messages` → **full reply** (the `stream:false` path) |
| integrations | the console's connect/secret/health/scan/mappings/invoke routes |
| launch | `POST /api/v1/launch` (Fire-TV kiosk) |
| events | `POST /api/v1/events` (inbound triggers → skills) |
| state / health | `GET /api/v1/state` · `GET /health` |

All mutating/privileged routes sit behind the existing API-key dependency (extracted to `api/deps.py`).

**WebSocket `/ws` — the one live loop only:**

- **inbound (client→server):** `user_input` (start a streaming turn); socket-binding
  (`set_active_persona` / `dismiss_persona` — genuinely *this-socket* state, so it stays on the WS).
- **outbound push (server→client):** `reply_started`, `reply_delta`, `reply_done`; avatar commands
  (`load_model`, `unload_model`, `show_pip`, `play_animation`, `start_lip_sync`, `assistant_message`);
  `status`.

**Both chat modes, one brain.** `ConversationService.run_turn(persona_id, text)` yields the turn event
stream. The **WS adapter** forwards deltas as they arrive (streaming); the **REST adapter** drains the
stream and returns the assembled reply (`stream:false`). Deterministic trigger/house-word replies are
simply a single-delta turn — identical shape on both transports.

**Conventions:** `/api/v1` prefix (a future `/v2` ships without breaking v1); uniform `{"detail": ...}`
errors (FastAPI default + voicebox); CORS configured at the app layer (unchanged from today).

### The two seams (both behind `clients/`)

- **Model-services seam** — LLM (`OpenAICompatLLM`, already done; talks to llama.cpp / Ollama / vLLM /
  OpenAI via `/v1/chat/completions`; gains a `chat_stream()` generator for the streaming turn), TTS
  (voicebox `/v1/audio/speech`, per `VOICEBOX_HTTP_API.md`), STT (whisper). No capability discovery —
  pure model I/O behind base URLs.
- **Capability-provider seam** — HA today, web-API/agent providers later (the console). `health /
  discover / invoke` + entity→capability mappings.

These stay **distinct** — different shapes (model services have no `discover()`). They share only the
*"connect + configure + health-check an external service"* theme, which the console's UI shell may
surface side-by-side later (a "Model services" section is a v2+ roadmap line, not built here).

## Frontend relationship

- **Viewer/kiosk stays vanilla Three.js** (perf-critical, Fire-TV Silk) — consumes the WS live loop + a
  few REST calls.
- **New PC/mobile pages (console, future settings/creation) are React.**
- **Shared typed API client** — plain-JS `apiClient.js` (REST) + `liveChannel.js` (WS), imported by
  both vanilla and React pages. Pages call `api.getPersonas()`, never raw `fetch`. This module *is* the
  ICD on the frontend side: a contract change is a one-module change, not a per-page rewrite. It is the
  frontend's "HAL for the backend."
- **OpenAPI graduation path:** FastAPI auto-publishes an OpenAPI schema + Swagger UI at `/docs` — the
  ICD in machine-readable form. v1 hand-writes the small client; later, codegen a typed client from the
  schema so the two sides cannot drift. (Noted, not built in v1.)

## Testing strategy

The layering makes the existing pytest + fakes approach cleaner:

- **Services** — unit-tested in isolation against fakes (`MockLLM`, `FakeTTS`, `_MockHAClient`,
  `FakeProvider`, and a recording `DisplayChannel`); no FastAPI, no network. (Like driver logic against
  a mock HAL.)
- **Routers / transport** — `TestClient` boundary tests (the existing `tests/integration` pattern with
  the no-thread `incarnation_server` fixture).
- **Contract** — a thin smoke test per endpoint; the `DisplayChannel` recording fake asserts the right
  push events fire for a turn.
- **Frontend** — vitest for the logic modules (`apiClient`, `liveChannel`, `mappingsModel`); minimal
  component tests.

## Migration sequence (strangler-fig — no big-bang)

Build the new layers **in-place, alongside** the old files, and strangle the POC one slice at a time.
Each slice: port the POC's behavior (don't redesign it away), ship behind the stable contract, keep
tests green.

1. **Slice 1 — Integrations Console (greenfield).** Built clean end-to-end on the new pattern; the
   **reference implementation**, with zero risk to the running POC. The existing console spec/plan is
   **rebased** onto the layers: routes → `api/integrations.py` (an `APIRouter`), the provider seam →
   `clients/providers/`, the stores → `stores/`. Locks the package root + the `api/deps.py` auth
   extraction.
2. **Slice 2 — Conversation loop.** Extract `ConversationService` from `PlayAIdes.chat` (preserving the
   trigger + house-word/HA orchestration — the proxy), implement `run_turn` as the turn event stream,
   add LLM streaming (`chat_stream`), introduce the `DisplayChannel` port, and wire both the WS live
   channel and the REST `messages` endpoint to it. Highest value; where the streaming + port work lives.
3. **Slices 3+ — domain services.** Extract `PersonaService` (CRUD/history), `AvatarService`
   (model/animation/display), `EventService`; the ~277-line WS dispatcher shrinks to delegating;
   `incarnation_server.py`'s inline routes become `api/` routers.
4. **TTS/STT proxy routes** stay with the concurrent TTS session until the voicebox `/v1/*` consumer
   migration lands; then they become a thin `TTSClient` / `STTClient` + proxy router on the same
   pattern.

## Open items (for the per-slice plans)

- **Package root:** top-level `playaides/` package vs. root-level packages (`api/`, `services/`, …) —
  decided in slice 1 (affects every import); update `pyproject.toml` `py-modules` / `packages.find`
  accordingly.
- **WS frame envelope:** exact JSON shape for `reply_started/delta/done` and the avatar push events
  (a `{type, payload}` envelope, matching today's WS messages) — pinned in slice 2.
- **REST exact paths + request/response schemas** per resource — pinned in each surface's slice (the
  console's are already specified in its design doc).
- **Streaming transport detail:** confirm the WS carries chat deltas for the avatar loop (decided) and
  that the REST `messages` endpoint drains the same generator (no SSE needed in v1).

## Self-Review

**Placeholder scan:** none — paths/operations marked "illustrative" are intentionally deferred to
per-slice plans (this is a standing reference, not an implementation plan); the genuinely-open choices
are collected under "Open items," not hidden as TBDs.

**Internal consistency:** the layer model, the `DisplayChannel` port, the contract, and the migration
slices all reference the same components (`ConversationService`, the two seams, the turn event model).
The console slice's mapping (routes→`api/`, providers→`clients/`, stores→`stores/`) matches the layer
model.

**Scope:** this is one coherent *architecture* design (boundaries + contract + migration strategy), not
multiple subsystems crammed together. The actual *building* is decomposed into slices, each its own
spec/plan — so it is appropriately scoped as a standing reference.

**Ambiguity:** "support both ways" is made explicit (REST full-reply vs WS stream over one
`run_turn` generator; deterministic replies = single-delta). "Clean separation" is made explicit (a
versioned API contract as the durable seam + one-directional layer dependencies + the single push port).
