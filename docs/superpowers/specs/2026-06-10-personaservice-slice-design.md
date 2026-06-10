# PersonaService slice — persona CRUD / history / triggers behind `/api/v1`

- **Date:** 2026-06-10
- **Type:** Design spec for one strangler-fig migration slice
- **Parent:** `2026-06-09-backend-frontend-architecture-redesign.md` (migration sequence, "Slices 3+ —
  domain services"; this is the first of them)
- **Unblocks:** `2026-06-09-console-trigger-redesign-PARKED.md` (its resume condition is exactly this
  slice: "PersonaService + persona/trigger store + `/api/v1` triggers API")
- **Precedents:** slice 1 (`2026-06-08-integrations-console-v1-design.md` — api→store pattern,
  `require_api_key` extraction) and slice 2 (`ConversationService` + `DisplayChannel`).

## Goal

Extract the persona domain — CRUD, chat-history I/O, and triggers — out of the `PlayAIdes` god object
into `PersonaService` + two stores + an `/api/v1/personas` router, and migrate the creator page's
persona CRUD from WS frames to REST so the corresponding WS dispatcher branches are **deleted**, not
delegated.

## Decisions (settled during brainstorm)

- **D1 — Scope: CRUD + history + triggers.** Activation (`set_persona`, the `set_active_persona` WS
  choreography), uploads (`model_uploaded`/`animation_uploaded`), and voice frames stay in `PlayAIdes`
  for the later avatar slice. *(Rejected: including activation — tangled with avatar choreography;
  CRUD-only — leaves the parked trigger console blocked.)*
- **D2 — Triggers API is whole-list replace.** `GET`/`PUT /api/v1/personas/{id}/triggers`; rows stay
  anonymous list entries, no ID scheme, no data migration. Single-operator system; the console edits
  rows client-side and saves the list. *(Rejected: per-row CRUD with generated IDs — needs a
  migration for a console that can list-replace; index-based rows — indexes shift on delete.)*
- **D3 — Validate all writes.** Every create/update/trigger-replace round-trips through the
  `Persona`/`Trigger` Pydantic models before touching disk; invalid → 422, file untouched. Closes
  today's corrupt-file hole (raw `json.dump` of unvalidated dicts). *(Rejected: REST-only validation,
  no validation — both keep the data-integrity bug alive on a "clean" service.)*
- **D4 — Frontend rides along: creator.js CRUD → REST.** The CRUD WS frames' only consumer is
  creator.js, so migrating it lets the dispatcher branches be deleted outright; backend-only would
  mean writing shape-preserving delegation shims that a later slice throws away. A new
  `incarnation/src/apiClient.js` (in the `consoleApi.js` mold) is the spec's shared-client seed.
  **viewer.js is untouched** — its read-only `get_personas` stays a WS frame (touching the
  Fire-TV/Silk page drags the TV into the test matrix for no architectural gain; it migrates with
  the avatar/viewer slice).
- **D5 — Approach A: service + two stores, full ICD shape.** `stores/personas.py` + `stores/history.py`
  (pure file I/O) composed by `services/persona.py` (domain rules), per the parent spec's named layout.
  *(Rejected: service-only with inline I/O — diverges from the ICD and re-extracts later when
  history/memories grow backends; stores-only without a service — the domain logic has no home.)*
- **D6 — Fix the `get_persona` latent bug.** `ConversationService` is constructed today with
  `get_persona=lambda pid: self.current_persona` — it ignores the id, so a REST turn targeted at a
  non-active persona runs with the *active* persona's character and the *target's* history. Rewire to
  `PersonaService.get_model(pid)` (load by id). This is a deliberate behavior change, pinned by a test.
- **D7 — New-surface error semantics are correct, not bug-compatible.** Create-collision → 409
  (today: silent overwrite); update of a missing persona → 404 (today: silently creates);
  delete-active → 409 (today: silent `False`). The old behaviors are bugs on an unvalidated surface,
  not contracts; nothing depends on them (creator.js treats them as success today and gets no signal
  at all).

## Components

### `backend/stores/personas.py` — `PersonaStore`

Pure file I/O over `personas/<id>/persona.json`. No Pydantic, no business rules.

- `__init__(base_dir: str | Path = "personas")` — constructor-arg base dir so tests run on `tmp_path`.
- `list_ids() -> list[str]` — subdirectories containing a `persona.json`.
- `read(persona_id) -> dict` — parsed JSON; raises `KeyError` if missing.
- `write(persona_id, data: dict) -> None` — `json.dump(indent=2)`, creating the directory if needed.
- `delete(persona_id) -> None` — `shutil.rmtree` of the persona directory; raises `KeyError` if missing.
- `exists(persona_id) -> bool`.
- **Path-traversal guard** (the existing `"/" | "\\" | "." | ".."` check) lives here — it protects the
  filesystem, so it belongs at the filesystem layer. Suspicious ids raise `ValueError`.

### `backend/stores/history.py` — `HistoryStore`

Pure file I/O over `personas/<id>/chat_history.json`.

- `__init__(base_dir = "personas")`.
- `read(persona_id) -> list[dict]` — missing file → `[]`; unreadable JSON → warn + `[]` (ported).
- `write(persona_id, history: list) -> None` — atomic tempfile + `os.replace`, ported verbatim from
  `PlayAIdes._save_history` (including the unlink-on-failure cleanup).
- `delete(persona_id) -> None` — remove the file if present.
- Same traversal guard as `PersonaStore`.

### `backend/services/persona.py` — `PersonaService`

The domain owner. Composes the two stores plus one injected callable.

```python
PersonaService(
    persona_store: PersonaStore,
    history_store: HistoryStore,
    active_persona_id: Callable[[], Optional[str]],   # supplied by PlayAIdes; delete guard
    history_cap: int = 80,                            # CHAT_HISTORY_CAP moves here
)
```

Typed exceptions (module-level): `PersonaNotFound`, `PersonaExists`, `PersonaActive`. Pydantic
`ValidationError` propagates as itself.

**CRUD** (validated per D3, slug rule `name.strip().lower().replace(" ", "_")` lives here):

- `list() -> list[dict]` — every readable persona doc, each with `"id"` injected; corrupt files are
  logged and skipped (today's behavior — one bad file must not take down the list).
- `get(persona_id) -> dict` — doc + `"id"`; `PersonaNotFound` if missing.
- `create(name, description) -> dict` — slugs the id; `PersonaExists` on collision (D7); builds the
  doc through the `Persona` model (full defaulted document, not today's partial dict), writes, returns
  doc + `"id"`.
- `update(persona_id, data: dict) -> dict` — `PersonaNotFound` if missing (D7); strips `"id"`,
  validates via `Persona(**data)`, writes `model_dump()`, returns doc + `"id"`.
- `delete(persona_id) -> None` — `PersonaNotFound` if missing; `PersonaActive` if
  `active_persona_id()` matches (D7).
- `get_model(persona_id) -> Persona` — typed load for internal consumers (ConversationService, D6).

**History** (cache + cap move here from `PlayAIdes` — single owner):

- `load_history(persona_id) -> list[dict]` — cache hit or store read, capped at `history_cap`,
  cached. Same contract as `PlayAIdes._load_history`.
- `save_history(persona_id) -> None` — persist the cached list via the store.
- `delete_history(persona_id) -> None` — drop cache entry + file.
- `histories` cache is exposed read-only where `PlayAIdes` needs it (the `history_loaded` WS frame
  at activation reads it).

**Triggers** (D2):

- `get_triggers(persona_id) -> list[dict]` — the `triggers` field of the doc (default `[]`).
- `replace_triggers(persona_id, triggers: list[dict]) -> list[dict]` — validate the *whole persona*
  with the new list spliced in (each row through `Trigger`, and the doc stays coherent), write, return
  the new list.

### `backend/api/personas.py` — the router

`APIRouter(prefix="/api/v1", tags=["personas"], dependencies=[Depends(require_api_key)])`, reaching
the service via `request.app.state.persona_service` (the slice-2 pattern; 503 if absent). Mounted in
`incarnation_server.py` beside the integrations and conversation routers.

| Route | Behavior |
|---|---|
| `GET /api/v1/personas` | `service.list()` |
| `POST /api/v1/personas` | body `{name, description}` → 201 + doc; `PersonaExists` → 409 |
| `GET /api/v1/personas/{id}` | doc; `PersonaNotFound` → 404 |
| `PUT /api/v1/personas/{id}` | full-document replace; 404 / `ValidationError` → 422 |
| `DELETE /api/v1/personas/{id}` | 204; 404; `PersonaActive` → 409 |
| `GET /api/v1/personas/{id}/triggers` | the list; 404 |
| `PUT /api/v1/personas/{id}/triggers` | whole-list replace; 404 / 422 |

`ValueError` from the traversal guard maps to 404 (don't leak guard details). Errors are FastAPI's
uniform `{"detail": ...}`. History gets **no REST surface** this slice (rehydration stays on the WS
`history_loaded` frame at activation; the parent ICD lists no history resource).

### `incarnation/src/apiClient.js` — shared REST client (seed)

Plain-JS module in the `consoleApi.js` mold (same API-key header handling), importable by vanilla
pages and React alike — the parent spec's "HAL for the backend", seeded with the persona surface:
`listPersonas()`, `getPersona(id)`, `createPersona(name, description)`, `updatePersona(id, doc)`,
`deletePersona(id)`, `getTriggers(id)`, `replaceTriggers(id, list)`. Whether `consoleApi.js` is
refactored to import from it is the implementer's call (nice-to-have, not required this slice).

## What shrinks / what's deleted

**`PlayAIdes`** constructs the stores + service at init and exposes it (also via
`incarnation_server.app.state.persona_service`):

- `list_personas` / `get_persona_by_id` / `create_persona` / `update_persona` / `delete_persona`
  become one-line delegations (internal callers — `set_persona`, the upload branches — still use
  them; they keep their current dict-in/dict-out signatures, with the new exceptions translated back
  to today's `None`/`False` returns where internal callers expect them).
- `_history_path` / `_load_history` / `_save_history` / `delete_history` delegate to the service;
  `self.chat_histories` becomes a property reading the service's cache (the `chat_history` legacy
  alias and the `history_loaded` frame keep working).
- `CHAT_HISTORY_CAP` is passed into the service; the constant keeps its home.
- `ConversationService` wiring changes (D6): `get_persona=self.personas.get_model`,
  `history_load=self.personas.load_history`, `history_save=self.personas.save_history`.

**WS dispatcher (`_handle_incarnation_message`):** the `get_persona`, `create_persona`,
`update_persona`, `delete_persona` branches (and their `persona_data` / `persona_created` /
`persona_updated` / `persona_deleted` reply frames) are **deleted** — creator.js was their only
consumer. `get_personas` stays and delegates (viewer.js consumes it, untouched per D4).

**creator.js:** the CRUD `conn.send`/`addEventListener` pairs are replaced with `apiClient.js` calls
(async/await, list refresh after each mutation, same UI flow). Voice frames (`design_voice` /
`test_voice`) and the existing REST uploads are untouched. Failed REST calls surface through the
existing `toast(...)` mechanism (today's WS failures show nothing at all).

## Error handling summary

- Service: typed exceptions (`PersonaNotFound` / `PersonaExists` / `PersonaActive`), Pydantic
  `ValidationError`, store `ValueError` (traversal) / `KeyError` (missing).
- Router maps: 404 / 409 / 409 / 422 / 404 respectively, `{"detail": ...}` bodies.
- Store I/O behavior ported: corrupt persona file → logged + skipped in `list()`, raises on `get`;
  corrupt history → warn + start empty.
- Atomic history writes preserved (tempfile + `os.replace`).

## Test plan

Three established tiers; all current tests stay green (341 passed / 5 skipped baseline).

**Unit (hermetic, `tmp_path`):**

- `PersonaStore` / `HistoryStore`: round-trip, missing-id behavior, traversal-guard rejects, atomic
  write (tempfile cleaned up on failure), corrupt-file handling.
- `PersonaService` (real stores on tmp dirs): slug rule; create collision → `PersonaExists`; create
  writes a full defaulted doc; update validates (bad doc → `ValidationError`, file untouched);
  delete-active guard via the injected callable; history cache + cap + idempotent load;
  `replace_triggers` validates rows and persists; `get_model` returns a `Persona`.
- Router (FastAPI `TestClient`, fake service): every status-code mapping in the table; 503 when the
  service is absent; auth dependency present (one 401 check with a key set).

**Regression / integration:**

- `ConversationService` rewire: a test pinning D6 — `run_turn` against a non-active persona id uses
  *that* persona's system prompt (the old always-active behavior is the bug).
- Existing suites: `tests/unit/test_persona.py` (hardcoded Silver UUID), conversation tests, WS
  dispatcher tests (updated: deleted branches' tests are removed, `get_personas` delegation kept).
- `PlayAIdes` delegation shims: internal callers (`set_persona`, upload branches) behave as before.

**JS:**

- `apiClient.js` unit tests in the `consoleApi.test.js` mold (URL shapes, auth header, error paths).
- creator flow re-verified in a desktop browser (list/create/edit/save/delete + a triggers-field
  save). No TV involvement.

## Out of scope (do not creep)

Activation (`set_persona` + `set_active_persona` choreography) · uploads · voice frames · viewer.js ·
history REST endpoints · the trigger-console UI (the parked brainstorm this slice unblocks) ·
memories/VectorDB · refactoring `consoleApi.js` onto `apiClient.js` (optional courtesy only).

## Self-review

**Placeholder scan:** none — every component lists its full surface; the one implementer-discretion
item (consoleApi refactor) is explicitly optional, not unspecified.

**Internal consistency:** the router table, service exceptions, and error-handling summary name the
same statuses; D4/D6/D7 are each realized in exactly one component section; the history cache has one
owner (service) with one declared reader (the activation frame via the `chat_histories` property).

**Scope check:** one service + two stores + one router + one frontend page — comparable to slice 2;
fits a single implementation plan.

**Ambiguity check:** "whole-persona validation on trigger replace" (not just per-row) is stated;
delegation shims' exception-to-legacy-return translation is stated; viewer's `get_personas` is
explicitly kept WS.
