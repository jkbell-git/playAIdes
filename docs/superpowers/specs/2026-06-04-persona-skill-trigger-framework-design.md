# Persona Skill + Trigger Framework — Design

**Date:** 2026-06-04 · **Status:** design (awaiting review) → implementation plan
**Grounded in:** [`research/2026-06-04-agentic-core-triggers-tools-pluggable-framework.md`](../../research/2026-06-04-agentic-core-triggers-tools-pluggable-framework.md) and Positioning & Roadmap **D6** / item **#7**.
**One-liner:** a pluggable, per-persona **deterministic** trigger→skill framework — skills are capabilities behind one common interface (kinds: internal / bash / http / provider-pack); triggers are deterministic `on → do` rules (voice phrase or inbound event); the user picks per persona what each can do. Designed so the future **agentic router** (LLM tool-calling / MCP) drops in over the *same* skill registry with no skill rewrite.

---

## 1. Goal & scope

**Goal:** give every persona a deterministic, configurable set of **skills** (actions) fired by **triggers** (voice phrases or external events), with no LLM in the decision loop. Generalize playAIdes' inbound-HA trigger moat to "wire anything to a skill." Ship PiP and language-following subtitles on top of it.

**In scope (v1):**
- The common **`Skill`** interface + **`SkillContext`** + **`SkillResult`**.
- Skill **kinds**: **internal** (hard-typed Python — `show_pip`, `dismiss_pip`), **`bash`** (argv), **`http`** (web request). The **`SkillProvider`** interface is *defined* (for external packs) but discovery/loading is deferred.
- **Skill registry** + loading: internal skills registered in code; declarative (bash/http) skills loaded from a global **`skills/`** directory; enabled per-persona by name.
- **Trigger model** + **deterministic router**: `on.phrase` (post-wake speech) and `on.event` (inbound), first-match-wins.
- **`POST /api/event`** endpoint — generic event intake (anything that can POST wires a trigger).
- **Per-persona config** additions to the `Persona` model: `brain_model`, `skills`, `triggers`, `captions`.
- **`brain_model`** selection with load-on-activation.
- **PiP frontend overlay** (the `show_pip` render target).
- **Subtitles as a persona mode** (`captions`) — *not* a skill.

**Deferred (documented, designed-for, not built):** external skill-pack discovery/loading (interface only); phrase **slot extraction** (`"show the {x} camera"`); the **agentic router** (LLM tool-calling / MCP / pi·Hermes delegation); **timer/cron** trigger source; per-display multi-room routing beyond the existing binding; pack **sandboxing**.

**Non-goals:** no AI in the decision loop; no bespoke tool protocol (the agentic future adopts MCP).

---

## 2. Architecture overview

```
                 ┌──────────────────────────────────────────────┐
  inbound event  │              ROUTER (deterministic)           │
  POST /api/event│   • phrase path: post-wake speech → match     │
   {name,payload}│   • event path : event name+conds → match     │──┐
        +        │   (first enabled trigger wins; no LLM)         │  │ dispatch(skill, params)
  post-wake      └──────────────────────────────────────────────┘  │
  speech ───────────────────────────────────────────────────────── │
                                                                    ▼
                                                      ┌──────────────────────────┐
                                                      │      SKILL REGISTRY        │
                                                      │ name → Skill (any kind)    │
                                                      │ internal · bash · http ·   │
                                                      │ [provider-pack, deferred]  │
                                                      └────────────┬───────────────┘
                                                                   │ execute(params, ctx)
                                              ┌────────────────────┼─────────────────────┐
                                              ▼                    ▼                     ▼
                                    ctx.send_display(WS)     subprocess(argv)      httpx request
                                    ctx.speak(TTS)           (bash kind)           (http kind)
                                    (internal kind →
                                     PiP overlay, etc.)

  Persona config (persona.json): brain_model · skills[] · triggers[] · captions{}
  Subtitles = a persona MODE read by the STT→brain→render pipeline (NOT a skill).
```

**Where it sits:** all backend pieces live in the existing FastAPI app (`incarnation_server.py` for the WS + the new REST endpoint; `playAIdes.py` orchestrator for the voice-path hook; `persona.py` for config). The frontend PiP overlay follows the existing `ViewerOverlays` + WS-message pattern. Nothing here is a new service.

**The pluggability seam (why it "supports it all"):** skills are defined once behind `Skill`. The **router** is the only component that knows *how* an input chooses a skill. The deterministic router ships now; a future **agentic router** is an alternative that tool-calls the same registry — and because a deterministic skill and an MCP tool share the shape `(name, typed params, execute)`, the same registry can later be exposed as MCP tools and consume external MCP servers as `SkillProvider`s.

---

## 3. Components

### 3.1 `Skill`, `SkillContext`, `SkillResult`

```python
class SkillResult(BaseModel):
    ok: bool = True
    output: str | None = None        # e.g. bash stdout / http body excerpt
    error: str | None = None

class SkillContext:                  # injected at dispatch; the skill's only door to the system
    persona: Persona                 # the active persona that owns this invocation
    async def send_display(self, message: dict, target: DisplayTarget = ACTIVE) -> None: ...  # WS → bound display(s)
    async def speak(self, text: str) -> None: ...   # route text through the persona's TTS + lip-sync
    http: httpx.AsyncClient          # shared client for http-kind skills
    logger: Logger

class Skill(Protocol):
    name: str
    Params: type[BaseModel]          # typed param schema (validated before execute)
    kind: Literal["internal", "bash", "http", "provider"]
    async def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult: ...
```

`Skill` is AI-agnostic. A skill touches the system *only* through `ctx`, which keeps skills isolated and testable with a fake context.

### 3.2 Skill kinds

- **internal** — a Python class implementing `Skill` directly; full typed `ctx` access. For tightly-integrated functions (`show_pip`, `dismiss_pip`, future internal persona/frontend actions).
- **`bash`** — declarative. Runs an **argv array** (never a shell string). Params are validated against `Params`, then substituted as **discrete argv elements** (no string concatenation into a shell → no injection). Captures stdout/exit code into `SkillResult`. Spec fields: `{name, kind:"bash", command:[...], params:{...}, timeout_s?, announce_output?}`.
- **`http`** — declarative. Builds a request from `{method, url, headers?, body?, params}`; params interpolate into url/headers/body via a safe templating step (values url/JSON-encoded, never raw-concatenated). Optional response→`SkillResult.output`.
- **`provider`** (interface defined, loading deferred) — `class SkillProvider(Protocol): def skills(self) -> list[Skill]: ...`. The path for an external pack (HA pack, another product) to register skills. v1 defines the Protocol and the registry's ability to accept provider-sourced skills; it does **not** implement discovery/auto-load.

### 3.3 Skill registry & loading

- A `SkillRegistry: dict[str, Skill]`, built at startup:
  1. **Internal** skills registered in code (decorator or explicit `register()`).
  2. **Declarative** skills loaded from the global **`skills/`** directory — pack files (JSON/YAML) of `bash`/`http` skill definitions, each validated into a typed declarative-skill object. Reusable across personas.
  3. **Provider** skills (deferred): when implemented, providers contribute via `provider.skills()`.
- **Validation at load:** duplicate names, unknown kinds, malformed specs → fail-fast at startup with a clear message.
- A persona's `skills: [...]` is the **enable-list** — only names present in both the registry *and* the persona's list are invocable for that persona (the flat "skill-tree"; prerequisites/tiers deferred).

### 3.4 Trigger model

```json
{ "on": { "phrase": "show the front door" },
  "do": { "skill": "show_pip", "params": { "source": "camera.front_door", "kind": "live" } } }

{ "on": { "event": "front_door_motion", "match": { "state": "on" } },
  "do": { "skill": "show_pip",
          "params": { "source": "camera.front_door", "kind": "live",
                      "announce": "Someone's at the front door." } } }
```

- `on.phrase` — a literal phrase matched against post-wake speech (deterministic; see §3.5).
- `on.event` — an event `name` plus an optional `match` object (shallow equality against the event payload).
- `do.skill` + `do.params` — the skill to fire and its params; params may reference event payload fields (`"{payload.entity_id}"`) for the event path.
- **Ordering:** triggers are evaluated in declared order; **first enabled match wins**.
- Triggers live per-persona in `persona.json` (`triggers: [...]`).

### 3.5 Deterministic router

Two entry points, no LLM in either:

- **Voice path** — hooks into `playAIdes.chat()` for post-wake utterances, evaluated **before** LLM conversation and alongside the existing `house_words` check. Reuses/extends `match_keyword_prefix` semantics (case-insensitive, word-boundary). On a phrase-trigger match → dispatch the skill and **short-circuit** (the utterance does not also go to the LLM). On no match → normal conversation (or `house_words` delegation) as today.
- **Event path** — `POST /api/event` (§3.6) → resolve the target persona(s) → evaluate that persona's `event` triggers (name + `match`) → dispatch with params (payload-interpolated).

Precedence within the voice path: **phrase-trigger → house_words → normal conversation.**

### 3.6 `POST /api/event` endpoint

- Bearer-token auth, same scheme as the existing `POST /api/personas/{id}/activate` / `/api/dismiss`.
- Body: `{ "name": str, "payload": object }`.
- Routes to the **active** persona's matching event-triggers (multi-display: the persona's bound displays). Synthesizes skill dispatch through the same path as the voice router. Returns `{matched: bool, skill?: str}`.
- This is the "wire anything" intake: an HA automation, an email watcher, n8n, a cron job elsewhere — all just POST an event.

### 3.7 Dispatch & `SkillContext` wiring

- `dispatch(persona, skill_name, params)`: verify the skill is registry-present **and** enabled for the persona → validate params against `skill.Params` → build `SkillContext` (bound to the persona + its display binding) → `await skill.execute(params, ctx)` → handle `SkillResult` (log; on error, optional persona error-speak).
- `ctx.send_display` targets the persona's bound display(s) (reusing the existing WS `_bindings`); default `ACTIVE` = wherever the persona currently is. Multi-room per-display routing beyond this is deferred to the existing binding work.

### 3.8 Persona model additions (`persona.py`)

All new fields **optional** → existing `persona.json` files keep working unchanged.

```python
class Trigger(BaseModel):
    on: TriggerOn          # {phrase: str} | {event: str, match?: dict}
    do: TriggerDo          # {skill: str, params?: dict}

class Captions(BaseModel):
    follow_my_language: bool = False
    mode: Literal["respond_in_language", "translate"] = "respond_in_language"

class Persona(BaseModel):
    # ...existing fields...
    brain_model: Optional[str] = None        # per-persona LLM (model name on the OpenAI-compatible endpoint)
    skills: List[str] = []                    # enabled skill names (the flat skill-tree)
    triggers: List[Trigger] = []
    captions: Optional[Captions] = None
```

### 3.9 `brain_model` + load-on-activation

- On persona activate, the brain LLM = `brain_model` (a model name passed to the existing OpenAI-compatible backend; Ollama *or* the local llama.cpp+MoE wrapper). If unset, fall back to the current default.
- **Load-on-activation, evict-on-idle** — no simultaneous multi-model residency required (only one persona is active per display). Ollama does this automatically; the llama.cpp wrapper needs a load/unload (or a `llama-swap`-style shim) — that shim is the only net-new piece, and it's small.
- In the **deterministic** layer the brain does conversation + persona voice only; **tool-calling quality is irrelevant**, so `gemma4-e4b` vs `qwen3` is a free per-persona preference.

### 3.10 PiP frontend overlay (the `show_pip` render target)

- New WS messages: **`show_pip`** `{source, kind, dismiss, announce?}` and **`dismiss_pip`** `{}`.
- New overlay element `#pip-overlay` in `index.html`, driven by a method on `ViewerOverlays` (matches the existing subtitle-band pattern). Layered over the WebGL canvas (`pointer-events:none` container; higher `z-index` than canvas, coexisting with the subtitle band — both honor TV title-safe insets).
- **Content kinds:** `snapshot` → `<img src=...>` (still image / email attachment / camera snapshot); `live` → MJPEG `<img src=...camera_proxy_stream...>` (most reliable on Fire TV Silk per the prior research; WebRTC-in-WebView avoided).
- **Dismiss policy** (`dismiss`): `{type:"timeout", seconds}` | `{type:"until_dismissed"}` | tied to a `dismiss_pip` trigger (voice "dismiss that"). Remote-press also dismisses.
- **Kiosk-aware:** styled under `body.kiosk`; default-off, re-enableable, consistent with the existing overlay-flag convention.
- `announce` (optional) → the persona speaks the line via `ctx.speak` when the panel appears.

### 3.11 Subtitles as a persona mode (NOT a skill)

- Config: `captions: {follow_my_language, mode}`. Read by the STT→brain→render pipeline, not the trigger router.
- **Signal already exists:** Whisper returns `stt_response.language` (today logged and discarded). Store it as the **current conversation language** (persisted across the turn, not re-detected per utterance — short utterances misdetect).
- **`respond_in_language` (default, simpler):** instruct the brain to respond in the conversation language; the subtitle is that response **verbatim** (one source of truth; no translation hop). Reuses the existing `#subtitle-band` rendering.
- **`translate`:** brain responds in its base language; an extra LLM pass translates the caption into the conversation language (spoken audio and caption then differ by design). Heavier — see Open Question Q1 for v1 phasing.
- Per-language render: ensure a CJK-capable font fallback on the subtitle band.

---

## 4. Data flow examples

1. **Voice skill:** STT → "show the front door" → router matches phrase-trigger → `dispatch(show_pip)` → `ctx.send_display(show_pip)` → overlay renders the live feed (utterance does *not* hit the LLM).
2. **Event skill:** HA motion automation → `POST /api/event {name:"front_door_motion", payload:{state:"on"}}` → matches event-trigger → `show_pip(announce=...)` → overlay + `ctx.speak("Someone's at the front door.")` via TTS.
3. **Captions mode:** user speaks Spanish → STT `language=es` → conversation language = `es` → (`respond_in_language`) brain replies in Spanish → subtitle band shows the reply verbatim.

---

## 5. Security

- **`bash`:** argv arrays only — params substituted as discrete argv elements, never concatenated into a shell; `shell=False`; per-skill `timeout_s`. No user-free-text reaches a shell.
- **`http`:** params url/JSON-encoded into the request (no raw interpolation); optional per-skill URL allowlist.
- **Packs / providers (when implemented):** loaded only from the configured `skills/` dir; documented to run with app privileges (single trust domain — self-hosted, single user); sandboxing deferred but called out.
- **`POST /api/event`:** bearer auth (existing scheme). The bearer token lives in the secret store / `.env` and is read from env — never pasted through chat.

## 6. Error handling

- Unknown / disabled skill name → log + no-op (never crash a turn). Param validation failure → log + no-op (+ optional persona error-speak). `execute` exception → caught, logged, skill marked failed. Malformed event body → `400`. Phrase no-match → fall through to conversation. Registry load errors (dup names, bad specs) → **fail-fast at startup**.

## 7. Testing

Follows the existing `bin/test` (Python) / `bin/test-js` (vitest) discipline; keep matching/building logic **pure** for unit tests:
- Phrase matcher (extends `match_keyword_prefix`); trigger matching + precedence; param validation; **bash argv building (injection attempts)**; http request building; registry load + validation; `dispatch` with a fake `SkillContext`; event-endpoint routing.
- Frontend (vitest): PiP overlay render + dismiss policies; coexistence/layout with the subtitle band; kiosk styling.

## 8. Module boundaries (isolation)

- `skills/` — registry, the `Skill`/`SkillContext`/`SkillResult` types, the kind implementations (internal/bash/http), the `SkillProvider` interface, the global-dir loader.
- `triggers` — `Trigger` model + the deterministic router (pure matchers).
- `incarnation_server.py` — `POST /api/event`; WS `show_pip`/`dismiss_pip`.
- `persona.py` — config additions.
- frontend `viewerOverlays.js` + `index.html` + `viewer.css` — PiP overlay; captions-mode read in the STT/render path.
Each unit answers: what it does, how it's used, what it depends on — and is testable alone.

## 9. Rough v1 build order

1. Persona config fields + `Skill`/`ctx`/registry + internal `show_pip`/`dismiss_pip` + dispatch.
2. Deterministic **phrase** router + `chat()` hook (precedence: phrase → house_words → conversation).
3. PiP frontend overlay + WS messages.
4. `POST /api/event` + **event** router.
5. `bash` + `http` kinds + global `skills/` loader.
6. `captions` persona-mode (`respond_in_language` first — see Q1).
7. `SkillProvider` interface (defined, not loaded).
Tests alongside each.

## 10. Deferred / future

External pack discovery/loading · phrase slot-extraction · agentic router (MCP/PydanticAI/pi·Hermes) · timer/cron triggers · translate-caption polish · pack sandboxing · multi-room per-display routing.

---

## Resolved decisions (approved 2026-06-04)

- **Q1 — Captions v1 phasing → ACCEPTED.** Design carries **both** modes; **implement `respond_in_language` first** (reuses the existing Whisper language signal + subtitle band, no translation hop), **`translate` is a fast-follow.**
- **Q2 — Voice-trigger acknowledgment → ACCEPTED.** A voice phrase that fires a skill is **silent (acts only) unless the trigger sets `announce`.**
- **Q3 — `brain_model` default → ACCEPTED.** A persona omitting `brain_model` **falls back to the global default model.**
