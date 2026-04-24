# Viewer Redesign — Design Spec

**Date:** 2026-04-24
**Branch:** `viewer_redesign`
**Status:** ready for implementation planning

## 1. Goals, scope, non-goals

### What this is

Replace `incarnation/index.html` with a new viewer page that is the persistent visual surface for talking to a persona. Targets two surfaces, in priority order:

1. **TVs around the house**, launched remotely by Home Assistant (URL-driven, no keyboard, voice-driven).
2. **Desktop browsers**, where typing and a chat transcript become useful.

The viewer is voice-first. A wake word (or continuous voice-activity detection) drives every conversation; the persona replies with TTS audio + lip-sync. One persona is on screen at a time per TV. The active persona can be **swapped at runtime** by speaking another persona's wake word — "Hey Silver" replaces whoever's there with Silver — and **dismissed** by speaking a dismiss phrase ("Goodnight Silver"), which returns that TV to a quiet "no persona" idle state.

A persona's **conversation memory is shared across TVs**. If you start chatting with Silver in the kitchen and then walk to the bedroom and say her wake word again, the conversation continues with full context. Per-TV display state (visible transcript, panel state, overlay flags) stays independent — only the LLM's chat history is shared, keyed by persona id and persisted to disk.

**Languages**: English and Japanese are first-class for v1. Whisper transcribes either; each persona's `language` field still drives TTS so a Japanese-speaking persona replies in Japanese, an English one in English. Wake words can be in either language (matched against transcripts as raw substrings — no language-aware tokenization needed).

The aesthetic matches the Persona Forge — gold and crimson on near-black, Cinzel / Chakra Petch type, P5 angular cuts — so the two pages are clearly the same product. The viewer wears those tokens **more quietly** than the Forge: the canvas dominates, chrome appears only when active.

### Non-goals (this spec, not just phase 1)

- Multiple VRMs in the scene at once.
- Per-TV UI mirroring. Each TV's UI state (which transcript items are visible, whether the chat panel is open, etc.) is independent. Only the LLM-context history is shared.
- Showing a video / camera input back to the user.
- Distinguishing speakers — all voice is treated as "the user".
- A general-purpose Home Assistant integration. We expose URL params + WebSocket hooks; HA can drive them however it wants.
- In-page settings UI. URL params cover all configuration in v1; an in-page tray is a follow-up.
- Word-level subtitle timing. v1 displays the full reply text at the start of `SPEAKING`.
- Languages beyond English and Japanese for v1. Whisper's multilingual model technically transcribes more, but only EN/JP are tested + supported as persona languages.

## 2. State machine

The viewer is always in exactly one of five states (the four chat states + an explicitly empty `EMPTY`). The active persona's avatar is driven by the state.

```
                ┌──────────────┐
                │    EMPTY     │  no persona on screen, mic still listening
                └──────────────┘
                       │ wake word for any persona detected
                       ▼
   boot ─────▶ ┌──────────────┐
   (default    │  INTRO       │  intro animation playing, audio not yet started
    persona)   └──────────────┘
                       │ intro anim ends
                       ▼
                ┌──────────────┐
                │   AMBIENT    │ ◀────── reply ends
                └──────────────┘
                       │ wake word detected (or VAD trip in continuous mode)
                       ▼
                ┌──────────────┐
                │  LISTENING   │
                └──────────────┘
                       │ user stops speaking (silence > N seconds)
                       ▼
                ┌──────────────┐
                │   THINKING   │  Whisper STT, then LLM
                └──────────────┘
                       │ reply text + audio stream ready
                       ▼
                ┌──────────────┐
                │   SPEAKING   │  TTS streaming + lip sync
                └──────────────┘
                       │ audio stream ends
                       ▼
                    AMBIENT

   Any state can transition to EMPTY via a dismiss phrase
   ("Goodnight Silver" / configured dismiss_words).
```

### Persona swap

When a *different* persona's wake word is detected (in any state, including `EMPTY`), a swap transition fires:

1. Brief P5-style red diagonal wipe across the canvas (~200 ms).
2. Old VRM + old background are unloaded (if any).
3. New persona's VRM + background load.
4. State enters `INTRO` (intro animation plays once, if configured) → `AMBIENT` or directly into `LISTENING` if the swap utterance contained additional content beyond the wake word.

A swap **does not reset** chat history. The new persona has their own per-persona history, persisted on disk and shared across TVs (see §6).

### Intro animation

When a persona becomes active (boot, swap, or summoned out of `EMPTY`), the viewer plays the persona's `avatar.intro_animation` once if configured (e.g. `"cute_greeting_twirl"`). When the clip finishes (or immediately if not configured), the viewer transitions to `AMBIENT` and plays `avatar.idle_animation` on loop. The legacy "send `cute_greeting_twirl` then crossfade to idle" flow in `playAIdes.py` collapses into this single configurable schema field.

### Dismiss

When the active persona's `dismiss_words` are matched in a transcript, the viewer transitions to `EMPTY`:

1. Brief fade-out of the VRM + background (~250 ms).
2. Mic indicator stays alive (the TV is still listening for any wake word).
3. Subtitle band, name plate, and chat-panel header all clear.
4. The persona's chat history is **preserved** on disk — re-summoning continues the conversation.

Dismiss is **per-TV**: dismissing Silver from the kitchen TV does not affect Silver on the bedroom TV, and does not delete her chat history. To "really" send a persona away, the user closes the tab or HA navigates to a different URL.

## 3. Architecture

```
                       browser tab (TV or desktop)
  ┌────────────────────────────────────────────────────────────────┐
  │  viewer.html / viewer.js / viewer.css                          │
  │   • mic capture (getUserMedia + VAD)                           │
  │   • lip-sync analyser                                          │
  │   • UI state machine + overlays                                │
  │   • wake-word match against transcript                         │
  └────────┬─────────────────────────────────────────────────┬─────┘
           │ WebSocket /ws                                   │ HTTP
           │  ▸ user_input          (text after STT)         │  POST /api/stt/proxy   ◀ new
           │  ▸ start_lip_sync      (existing)               │  GET  /api/tts/proxy   (existing)
           │  ▸ set_active_persona  ◀ new                    │  GET  /api/personas/…  (existing)
           │  ▸ assistant_message   ◀ new (server→browser)   │
           │  ▸ persona_changed     ◀ new (server→browser)   │
           │  ▸ get_personas / personas_list                 │
           │                                                 │
  ┌────────▼─────────────────────────────────────────────────▼─────┐
  │  incarnation_server (FastAPI on :8765)                          │
  │   • forwards user_input → PlayAIdes.chat()                      │
  │   • new STT proxy: streams audio → Whisper container :9000      │
  │   • set_active_persona → PlayAIdes.set_persona()                │
  └────────┬───────────────────────────────────────┬─────────┬─────┘
           │                                       │         │
   PlayAIdes (CLI)                          Whisper container   TTS container
                                            (new, port 9000)    (existing, 8009)
```

### Wake-word and dismiss matching

Whisper transcribes the full utterance. The browser checks the transcript against:

1. The active persona's `dismiss_words` first — if matched, transition to `EMPTY` and stop.
2. Each loaded persona's `wake_words` — case-insensitive substring match across English and Japanese characters. On a hit, that persona is activated and the rest of the transcript (with wake-word phrase stripped) becomes the user message. If the transcript is *only* the wake word, transition to `AMBIENT` and wait for the next utterance.
3. If neither matches and the active persona is set, the transcript becomes user input (in `continuous` activation mode) or is dropped (in `wake` mode).

No JS wake-word library is shipped — Whisper is the wake-word detector and the STT engine. The latency cost is one Whisper round-trip per utterance (already there for STT regardless).

### Voice activation modes

- `wake` (default): every transcript is checked for any persona's wake word; only matches start a conversation. Dismiss words always work regardless of activation mode.
- `continuous`: every transcript is forwarded as user input to the active persona; no wake-word gate. Dismiss words still work.

Selected via `?activation=` URL param at boot.

### Multi-TV memory model

Conversation history is keyed by **persona id**, not by browser session, and persists to disk:

```
personas/<id>/chat_history.json   # appended on every turn
```

`incarnation_server` exposes a single `chat_histories: Dict[persona_id, List[Message]]` map that is loaded from disk at startup. Each `user_input` from any TV:

1. Routes to the persona id that the sending TV currently has active.
2. Appends to that persona's history.
3. The LLM sees the full per-persona history regardless of which TV sent the message.
4. The reply is broadcast over the WS to **all clients currently bound to the same persona id**, so any other TV showing that persona sees the new turn appear in its transcript pane.
5. The updated history is persisted before the response is acknowledged.

Concurrency model: only one persona is "actively responding" at any moment — last-writer-wins per persona. If the kitchen TV and bedroom TV both send user input for Silver in the same second, they're processed serially via an asyncio.Lock keyed by persona id. PlayAIdes itself stays single-threaded.

### Multilingual STT

Whisper runs the multilingual `base` (or `small` for better accuracy) model — *not* the `.en`-only variant. Auto-detect handles which language a given utterance is in. Each persona's `language` field still drives TTS, so a Japanese-speaking Silver replies in Japanese even if the user spoke English (the LLM is asked to respond in the persona's language via the system prompt).

## 4. UI layout

### Page skeleton

```
┌─────────────────────────────────────────────────────────────────┐
│  forge-strip   (thin red+gold P5 ribbon, top)                   │  z: 100
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                                                                  │
│                          ┌────────────┐                          │
│                          │            │                          │
│                          │   VRM      │   ← canvas (full page,   │
│                          │            │      window-sized)       │
│                          │            │                          │
│                          └────────────┘                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  subtitle band  (only when SPEAKING; configurable)       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  [● mic]    ←── corner: state indicator       [Silver]  ←── name│  z: 80
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                                            ┌─ chat panel ─┐
                                            │ collapsed by │
                                            │ default,     │  z: 90
                                            │ slides from  │
                                            │ right        │
                                            └──────────────┘
```

The canvas fills the viewport (same as today). All overlays are absolutely positioned; the chat panel slides in from the right when expanded.

### Overlay layers (each independently togglable)

| Overlay | Position | Behavior | URL param | Default |
|---|---|---|---|---|
| Mic / state indicator | bottom-left corner | dot whose color + animation tracks state | `?mic=` | on |
| Subtitle band | bottom center, full-width band | hidden by default; fades in during `SPEAKING`; fades out 2 s after audio ends | `?subtitles=` | on |
| Name plate | top-left under strip | small Genshin-style chip: persona name + connection dot | `?nameplate=` | off |
| Master cinematic | — | overrides all of the above to off | `?cinematic=` | off |

### State-specific visuals

| State | Mic dot | Subtitle band | Avatar |
|---|---|---|---|
| AMBIENT | dim gold, slow pulse | hidden | idle anim |
| LISTENING | crimson, fast pulse + outer glow | shows a `listening…` placeholder (faded gold) — replaced with the final transcription once STT returns | idle (or "listening" head-tilt anim if available) |
| THINKING | gold, spinning ring | shows last user utterance (greyed) | idle |
| SPEAKING | dim red | shows persona reply (full crimson) | speaking anim + lip sync |

### Aesthetic — matching Forge but quieter

Same color tokens, fonts, and clip-path language as `creator.css`, but less ornamentation:

- No film grain (TVs already dither — would be muddy).
- Filigree corners only on the chat panel and subtitle band, not floating on the canvas.
- Overlay backgrounds use `backdrop-filter: blur(12px)` over the scene rather than opaque panels.
- Shared CSS variable file (`tokens.css`) extracted from `creator.css` so the two pages stay in sync. `creator.css` and `viewer.css` both `@import` it.

## 4b. Backgrounds

Three tiers, auto-detected by file extension on `avatar.background_url`.

| Tier | Extensions | What happens | When to use |
|---|---|---|---|
| Flat image | `.jpg .jpeg .png .webp` | Set as `scene.background` (texture) — same as today | Quick, cheap, posters |
| HDRI panorama | `.hdr .exr` | Equirectangular: `scene.background` for the panorama + `scene.environment` (via `PMREMGenerator`) for image-based lighting on the VRM | Best ratio of "looks 3D" to "cheap" |
| 3D scene | `.glb .gltf` | `GLTFLoader` loads the scene, added to `THREE.Scene` alongside the VRM. Any lights/cameras packed in the glb apply | True dioramas; heaviest |

A single helper in `scene.js` dispatches by extension:

```js
function loadBackground(url) {
  if (!url) return clearBackground();
  const ext = url.split('.').pop().toLowerCase();
  if (['jpg', 'jpeg', 'png', 'webp'].includes(ext)) return loadFlatImage(url);
  if (['hdr', 'exr'].includes(ext))                return loadHDRI(url);
  if (['glb', 'gltf'].includes(ext))               return load3DScene(url);
  console.warn('[scene] unknown background extension:', ext);
}
```

### Persona schema (no break)

Existing `avatar.background_url` stays a flat string. Two **optional** new sub-fields on `avatar` for cases where defaults aren't right:

```json
"avatar": {
  "model_url": "models/silver_maid/Silver.vrm",
  "background_url": "scene/castle_interior.glb",
  "spawn_point":   [0, 0, 0],
  "camera_target": [0, 1.1, 0]
}
```

Both default to sensible values (origin / head height) when omitted.

### Lifecycle

- **Boot**: viewer loads default persona → loads its background per the rules above.
- **Persona swap**: same red-diagonal wipe covers the VRM + background swap. Both old and new are off-screen for ~200 ms, then both fade in together.
- **3D scenes share the existing lighting rig** by default — the rim lights / key light from `scene.js` still hit the persona. If a `.glb` includes its own lights, they're added on top.
- **Failure fallback**: if a `.glb` background fails to load, fall back to flat-grey + a console warning rather than a black screen.

### Out of scope

- Animated backgrounds (video, sprite sheets, particle systems running independently of the persona).
- Per-conversation background changes ("set the scene to a beach" via voice command).
- Editor UI for picking a background — that belongs in the Persona Forge, separate spec.

## 5. Chat panel + typed input

### Visibility model

- **Collapsed by default** on every launch (TV-first principle).
- A single small **handle** on the right edge, always visible — gold-rimmed, ~28 × 80 px, with a `‹` glyph. Click/tap to expand, click again to collapse.
- URL param `?chat=open` opens it pre-expanded for desktop sessions.

### Layout when expanded

- Slides in from the right, **440 px wide**, full viewport height.
- **Overlays** the canvas (`position: fixed; right: 0`) — does not reflow / shrink the scene.
- Structure:

```
┌── Chat panel ─────────────────────────────────────────┐
│  ▾ persona name  ·  active wake word                  │   ← header
│  ──────────────────────────────────────────────────   │
│                                                       │
│  ▸ TRANSCRIPT                                         │   ← scrolling region
│   You      "what's the weather like in your land?"    │     (auto-scrolls
│   Silver   "An overcast spring, milord. Pleasant…"    │      to newest)
│                                                       │
│  ──────────────────────────────────────────────────   │
│  [ type to speak…                              ] [▶]  │   ← text input row
└───────────────────────────────────────────────────────┘
```

### Transcript items

- **User lines**: gold accent caret, "You" label, body text in cream.
- **Assistant lines**: crimson accent caret, persona name as label, body text in cream.
- Each line carries an optional state pip when LIVE: pulsing dot during `LISTENING` (user line being captured), shimmer during `THINKING`, fade-in during `SPEAKING`.
- **Auto-scroll** to bottom on new entries, but **freeze** if the user has scrolled up — Discord/Slack semantics.
- Plain text only; no markdown rendering. Newlines preserved.

### Text input

- Single-line input + send button. Enter or click sends.
- **Disabled while in `SPEAKING`** — re-enabled the instant audio ends.
- Sending text takes the same path as voice → STT → text → `user_input` WS message; it just skips the STT step.
- No autosuggest, no slash commands.

### Persistence

- The transcript displayed in the panel lives only in browser memory and clears on reload (per-tab UI state, deliberately not synced).
- The **LLM-context history** the persona uses is server-side, per-persona, persisted to `personas/<id>/chat_history.json`. On `set_active_persona`, the server emits a `history_loaded` event so the panel can rehydrate the visible transcript from disk if the user wants to scroll back through prior turns. See §6 for the storage details.

### Subtitle interaction

- Chat panel **closed**: subtitle band (if enabled) shows the assistant's reply during `SPEAKING`.
- Chat panel **open**: subtitle band is **suppressed** to avoid duplicating text.

### Out of scope

- In-page settings UI.
- Conversation export / save / replay.
- Multi-turn editing, message deletion, re-rolling a reply.
- Persona switcher inside the panel — wake-word swap is the only switching mechanism v1 ships.

## 6. Backend additions

### New WebSocket messages

**Browser → server**

| `type` | Payload | Triggers |
|---|---|---|
| `user_input` | `{ text, persona_id }` | `PlayAIdes.chat(text, persona_id)` — routes to the named persona's history |
| `set_active_persona` | `{ id }` | New `PlayAIdes.set_persona(id)` — also marks this client as bound to that persona id for broadcast routing |
| `dismiss_persona` | `{ id }` | Server clears this client's persona binding; chat history on disk is **not** deleted |

**Server → browser**

| `type` | Payload | When |
|---|---|---|
| `assistant_message` | `{ text, persona_id }` | Sent immediately before `start_lip_sync`. Broadcast to all clients bound to `persona_id` |
| `persona_changed` | `{ persona, ok, error? }` | After `set_active_persona` |
| `history_loaded` | `{ persona_id, history }` | After `set_active_persona`, sent only to the requesting client so its transcript can rehydrate from disk |

(Existing messages — `start_lip_sync`, `play_animation`, `personas_list`, `persona_data`, `persona_created`, `persona_updated`, `persona_deleted`, `voice_designed`, `voice_tested`, etc. — keep their current shapes.)

### New HTTP endpoint

**`POST /api/stt/proxy`**

- Request body: `multipart/form-data` with `audio` file (browser sends a webm or wav blob).
- Forwards the body to the Whisper container's `POST /asr` (multipart pass-through). No `language` hint — let Whisper auto-detect EN vs JP.
- Returns `{ "text": "transcribed string", "language": "en" | "ja" }`.
- Symmetric with the existing `/api/tts/proxy` — the Whisper container is never directly reachable from a browser.

### New `PlayAIdes.set_persona(id)`

```python
def set_persona(self, persona_id: str) -> Optional[Persona]:
    """Reload the active persona at runtime.

    Loads personas/<id>/persona.json, runs _validate_persona, swaps
    current_persona, and ensures that persona's chat history is
    loaded into the in-memory map (lazy: from disk on first access).
    Idempotent: no-op if id == current_persona.id.
    """
```

- Path-traversal guarded the same way `delete_persona` is.
- Raises `PersonaLoadError` on bad input — the WS handler catches it and emits `{type: "persona_changed", payload: {ok: false, error: <msg>}}`.
- **Does not reset history.** History is per-persona, persisted, and survives swaps.

### Per-persona chat history persistence

```python
class PlayAIdes:
    chat_histories: Dict[str, List[Dict[str, str]]]   # persona_id -> messages
```

- Loaded lazily on first `set_persona` (or first `chat` call) for a given id, from `personas/<id>/chat_history.json`.
- Appended on every turn (user message + assistant reply).
- Persisted to disk after each turn — atomic write via tempfile + `os.replace`.
- Capped at the most recent **N=80** messages on load (older entries trimmed in-place). Configurable later.
- New `delete_history(persona_id)` clears both in-memory and on-disk; not exposed to WS in v1 but available for future "/forget" commands.

### `PlayAIdes.chat(text, persona_id=None)` signature change

Optional `persona_id` arg routes the message to that persona's history. If omitted (CLI usage), uses `current_persona`. Backwards-compatible.

### Client-binding registry in `incarnation_server`

`incarnation_server` keeps an in-memory `Dict[WebSocket, persona_id]` so it can broadcast `assistant_message` to all clients bound to a given persona. Bindings are set when a client sends `set_active_persona`, cleared on `dismiss_persona` or disconnect.

### New Whisper container in `docker-compose.live.yml`

```yaml
whisper:
  image: onerahmet/openai-whisper-asr-webservice:latest
  container_name: playaides-whisper
  environment:
    - ASR_MODEL=base                # multilingual; supports EN + JP
    - ASR_ENGINE=faster_whisper
  ports: []
  healthcheck:
    test: ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:9000/docs', timeout=2)\""]
    interval: 15s
    timeout: 5s
    retries: 40
    start_period: 60s
```

GPU optional; CPU is fine for `base`. The `.en`-only variant is **not** used because we need Japanese. Add a `WHISPER_URL` env var read by `incarnation_server` (`POST /api/stt/proxy` target), defaulting to `http://localhost:9000`.

### Test additions

- `tests/unit/test_set_persona.py` — happy path, refuses unknown id, refuses path traversal, no-op when same id, history is loaded (not reset).
- `tests/unit/test_chat_history.py` — round-trip load/save per persona, cap at N messages, atomic write semantics.
- `tests/integration/test_stt_proxy.py` — `TestClient` posts a tiny wav, mocked Whisper returns text + language, asserts pass-through.
- `tests/integration/test_persona_routing.py` — two mock WS clients bound to different personas; verify `assistant_message` only reaches the matching one.
- `tests/live/test_whisper_live.py` — real Whisper container, sub-second smoke audio in both English and Japanese; marker `live` so it auto-skips without the live stack.
- New `wake_words`, `dismiss_words`, `intro_animation`, and `is_default` covered by `test_persona.py` schema tests.

## 7. Configuration surface

### URL params (read once at viewer boot)

| Param | Values | Default | Effect |
|---|---|---|---|
| `persona` | persona id | (the `is_default: true` persona, else first found) | Persona to load at boot |
| `activation` | `wake` \| `continuous` | `wake` | Voice activation mode |
| `cinematic` | `0` \| `1` | `0` | Master overlay kill-switch (overrides all overlay flags to off) |
| `mic` | `0` \| `1` | `1` | Show mic / state indicator |
| `subtitles` | `0` \| `1` | `1` | Show subtitle band |
| `nameplate` | `0` \| `1` | `0` | Show persona name plate |
| `chat` | `closed` \| `open` | `closed` | Chat panel initial state |
| `ws` | URL | `ws://localhost:8765/ws` | WebSocket URL override |
| `api` | URL | `http://localhost:8765` | REST base URL override |

A single `config` object built from these params is passed to the orchestrator. URL changes require a reload — no live re-config.

### Persona schema additions (`persona.py`)

Four optional fields on `Persona`:

```python
class Persona(BaseModel):
    # … existing fields …
    wake_words: Optional[List[str]] = None
    dismiss_words: Optional[List[str]] = None
    is_default: Optional[bool] = False
    # `language` already exists — enforce one of: "English", "Japanese" for v1.
```

- **`wake_words`**: phrases that summon this persona. e.g. `["hey silver", "silver", "シルバー"]`. Case-insensitive substring match against each transcript. Empty / missing → persona can't be wake-summoned (only set explicitly via URL or `set_active_persona`).
- **`dismiss_words`**: phrases that send the active persona back to `EMPTY`. e.g. `["goodnight silver", "dismiss", "おやすみ"]`. Same matching semantics. Recommended default in the Persona Forge: at minimum `["goodnight <name>", "bye <name>"]`. Empty / missing → persona can't be voice-dismissed (a different persona's wake word still swaps).
- **`is_default`**: at most one persona per repo carries `true`. Used as the boot persona when `?persona=` is omitted. If none flagged, fall back to the first persona alphabetically and log a warning.

Two optional `Avatar` sub-fields:

```python
class Avatar(BaseModel):
    # … existing fields …
    intro_animation: Optional[str] = None         # plays once on activation
    spawn_point: Optional[List[float]] = None     # [x, y, z]
    camera_target: Optional[List[float]] = None   # [x, y, z]
```

- **`intro_animation`**: name of an animation to play once when the persona becomes active (boot, swap, summon out of `EMPTY`). Falls back to `idle_animation` if missing. Replaces the hardcoded `"cute_greeting_twirl"` in the legacy `playAIdes.load_default_animations`.

All defaults preserve backwards compatibility — existing personas keep working unmodified.

### Language model

The existing `language` field on `Persona` carries through unchanged. v1 supports `"English"` and `"Japanese"`. Whisper auto-detects the user's language; the persona's `language` drives TTS and is injected into the LLM system prompt ("respond in Japanese") so reply language tracks the persona, not the speaker. Wake words and dismiss words can be in either language since they're matched as raw substrings against the transcribed text.

## 8. Testing strategy

### What's tested

| Layer | Coverage |
|---|---|
| Unit | `set_persona` (5 cases), persona schema with `wake_words` + `is_default`, URL-extension classification helper for backgrounds |
| Integration | `/api/stt/proxy` happy + upstream-error paths (Whisper mocked); WS round-trips for `user_input` and `set_active_persona` |
| Live | `tests/live/test_whisper_live.py` smoke against the real container |
| Manual | UI states, audio routing, lip-sync, wake-word matching against real transcriptions, TV resolutions |

### What's deliberately not tested in this spec

- JS unit / browser tests. The codebase has no Vitest / Jest / Playwright today; adding it is its own follow-up.
- Performance on specific TV hardware. Manual sanity-check only.

## 9. Open questions / known limitations

These are documented so they don't surprise anyone in implementation, but resolving them is **out of scope** for this spec.

- **Mic permission UX on a TV**: `getUserMedia` will prompt on first launch. Solving "TVs grant mic permission once and remember it" is browser-flag / kiosk-mode territory.
- **Word-level subtitle timing**: v1 dumps the full reply text into the subtitle band at the start of `SPEAKING`. True caption sync would need word timestamps from the TTS server.
- **VAD library choice**: prototype with a simple energy-threshold VAD on `AnalyserNode` data. If flaky, swap in `@ricky0123/vad-web` later.
- **Whisper-down behaviour**: viewer shows mic indicator in `error` state (red); typed input still works as a fallback.
- **HTTPS required for `getUserMedia`**: TVs reaching `http://htpc.local:5173/` will get blocked mic access on most browsers. Production deployment needs a reverse proxy with TLS, or `chrome://flags/#unsafely-treat-insecure-origin-as-secure` configured per-device. Manual setup, out of scope here.

## 10. Implementation phases

The spec covers the whole vision; implementation ships in five sequential phases. Each phase merges to `main` independently with passing tests before the next begins.

| Phase | Scope | Independent ship value |
|---|---|---|
| **1. Viewer redesign + ambient overlays + intro/idle anim** | New HTML/CSS/JS for the viewer page replacing `index.html`. Extracted `tokens.css`. Configurable overlays via URL params. State machine scaffolded; `INTRO` plays `avatar.intro_animation` (or skips when missing) → `AMBIENT` plays `avatar.idle_animation`. Existing terminal-driven chat still works for `SPEAKING`. No mic. Backgrounds still load via existing `set_background` command. | Stage looks right on a TV; persona greets you on load; nothing regresses |
| **2. Voice input pipeline + multilingual STT** | Whisper container (multilingual `base` model) + `/api/stt/proxy`. Browser mic capture with VAD. New `LISTENING` and `THINKING` states wired. Voice in → PlayAIdes → voice out, in EN or JP. `user_input` + `assistant_message` WS messages with `persona_id`. | Viewer is actually conversational, in two languages |
| **3. Wake-word + dismiss matching** | `wake_words` and `dismiss_words` fields on personas. Browser switches activation modes (`wake` vs `continuous`) per `?activation=`. In wake-word mode, only the **currently-active** persona's wake words are checked. Dismiss words always work and transition to `EMPTY`. Cross-persona swap deferred to phase 4. | Hands-free start + dismiss for the active persona |
| **4. Runtime persona swap + per-persona memory** | `set_active_persona` WS + `PlayAIdes.set_persona()`. Wake-word matching expands to **all** personas; a hit on a different one triggers an unload/load of VRM + background with the red-diagonal wipe. Per-persona chat history persisted in `personas/<id>/chat_history.json`, capped at N=80, loaded on summon. Client-binding registry routes `assistant_message` to all TVs bound to the same persona id. `is_default` persona resolution at boot. | Summoning + cross-room conversation memory |
| **5. Backgrounds upgrade + collapsible chat panel** | Three-tier background loader (flat / HDRI / 3D). `spawn_point` + `camera_target` schema. Right-edge handle, transcript (rehydrated from `history_loaded` on summon), text input. URL `?chat=` toggle. | Polish + desktop story |

Each phase will get its own implementation plan via the writing-plans skill.

## 11. References

- Existing files this replaces / extends: `incarnation/index.html`, `incarnation/src/main.js`, `incarnation/src/scene.js`, `incarnation/src/incarnation.js`, `incarnation/styles/main.css`.
- Existing patterns to follow: `incarnation/creator.html` and `creator.js` for the panel/overlay vocabulary; `incarnation_server.py:proxy_tts_stream` for the `/api/stt/proxy` shape; `tests/integration/test_incarnation_server_http.py` for the integration test pattern.
- External: [`onerahmet/openai-whisper-asr-webservice`](https://github.com/ahmetoner/whisper-asr-webservice) for the Whisper container.
