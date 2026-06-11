# playAIdes

What's working:

**PlayAIdes**
- Chatting with an OpenAI-compatible LLM (Ollama by default; any `/v1` endpoint — llamacpp-wrapper, etc.)
- Loading personas from JSON files (`personas/<id>/persona.json`)
- Voice input — browser mic → STT (Whisper) → LLM, with wake-word / dismiss-word gating and cross-persona wake (saying another persona's wake word swaps to it)
- A persistent bottom text-input console ("type to speak") in the viewer, usable alongside (or instead of) voice
- Streaming TTS reply with lip-sync visemes driving the mouth
- Home Assistant integration — HTTP triggers (swap / dismiss / state / event) and skills delegation via per-persona `house_words` (see [Home Assistant integration](#home-assistant-integration) below)

**Incarnation (the viewer)**
- VRM model loading + animation playback (VRMA / Mixamo) over WebSockets
- Themeable "game-UI" viewer chrome — nameplate, date masthead, camera PiP, dialogue/subtitle band, mic indicator, sanitized command-log, and per-theme procedural backdrops (p5 red-room, fate gold magic-circle, manga focus-line 集中線 montage) — switchable via `?theme=` (`p5-basic` default, plus `fate-basic`, `manga-basic`, `classic`)
- Floating camera **picture-in-picture** with a theme-selectable inked frame (driven by `show_pip` / `dismiss_pip` WS commands; HA can push a live camera feed into it)
- Sanitized **command-log console** showing the real WS command stream (secrets redacted, host/IP masked, truncated); opt out with `?cmdlog=0`
- **Kiosk mode** (`?kiosk=1`) for unattended TVs: chrome defaults off, cursor hidden, camera director owns framing, best-effort keep-awake + fullscreen
- **Fire TV launch** via `bin/silver-launch.py` (CEC power-on → open Silk → audio-unlock tap), mirrored HA-side by `ha/silver_launch.yaml`
- Persona Forge creator page (`creator.html`) for identity / model / animation / voice design

## Project docs

- [Continuity log](./CONTINUITY.md) — current focus, open TODOs, known issues, decisions
- [User guide](./docs/USER_GUIDE.md) — how to install and run this

## Incarnation pages

The `incarnation/` directory is a Vite multi-page app with two top-level HTML pages
(`index.html` — the viewer, and `creator.html` — the Persona Forge). For an always-on
display the viewer is **built** (`cd incarnation && npx vite build` → `incarnation/dist`)
and **served by the backend** at `http://<host>:8765/` (see [Running](#running)). A Vite
dev server (`npm run dev`, port `5173`) is also available for hot-reload during frontend
work — see [Running](#running) for when to use which.

| Page | Served at | Status |
|------|-----------|--------|
| **Viewer** | `:8765/` (built) or `:5173/index.html` (dev) | active — themed chrome, voice + text input, kiosk |
| **Persona Forge** (persona creator) | `:5173/creator.html` (dev) | active |

### `index.html` — Viewer

Full-screen 3D canvas with a themeable "game-UI" chrome. This is what runs during a live
session: the loaded VRM stands in the scene (over a themed CSS backdrop — the canvas is
transparent), animations play over WebSocket commands from `playAIdes.py`, and lip-sync
visemes drive the mouth from the streaming TTS audio.

The viewer now has full interactive UI:

- a **nameplate** + date masthead,
- a floating **camera PiP** with a theme-selectable inked/comic frame,
- a bottom **`console-bar`** with a text input — type to speak; Silver's reply shows on the line above (stays visible even in kiosk),
- a **mic indicator** and voice capture (STT) for spoken input,
- a sanitized **command-log** console (`?cmdlog=`),
- the **theme system** (`?theme=`) and **kiosk mode** (`?kiosk=1`).

- **Entry script**: `src/viewer.js`
- **Styles**: `styles/viewer.css` (which `@import`s the shared `styles/tokens.css` theme tokens)
- **Config**: `src/viewerConfig.js` parses URL params (`?theme=`, `?kiosk=`, `?cmdlog=`, `?persona=`, `?mic=`, `?subtitles=`, `?nameplate=`, `?quality=low`, `?ws=`, `?api=`)
- **Served by**: the backend at `:8765/` (built into `incarnation/dist`); the page is the `incarnation_server` WS client

A **design-preview page** (`incarnation/design-preview.html`, open it via the Vite dev
server on `:5173` and switch themes with `?theme=`) renders the FULL game-UI for each theme
— including decorative widgets (Topics list, action menu, bond pips, status meter, control
bar) that have no backing data. It's a dev/design-eval tool only; those widgets are **not**
added to the live viewer DOM, and the page is not part of the backend-served `dist` build.

### `creator.html` — Persona Forge

Persona-5 × Genshin Impact aesthetic. Stacked left column with sections (Identity / Vessel / Repertoire / Voice) — no tabs. Right side is a framed character card with the live VRM and stage controls (play / pause / stop / face / reset). Click any animation to play it on the model; click it again to pause/resume.

- **Entry script**: `src/creator.js`
- **Scene module**: `src/creatorScene.js` (canvas-bound, sizes to the character card)
- **Styles**: `styles/creator.css`
- **Status**: identity editing, model upload, animation upload + click-to-play, voice design + preview, persona delete, idle-animation auto-play, "talk" button (opens Viewer + copies the launch command). Open follow-ups: in-page chat input, expression preview, multi-persona runtime switching.

### Shared modules under `src/`

These are imported by the pages above; not pages themselves:

| Module | Purpose |
|--------|---------|
| `scene.js` | Three.js scene/camera/renderer for the **Viewer** (window-sized, transparent canvas) |
| `creatorScene.js` | Same idea but bound to a specific canvas, used by Persona Forge |
| `incarnation.js` | Top-level orchestrator for the Viewer (model + managers + WS dispatch) |
| `viewerConfig.js`, `viewerState.js`, `viewerOverlays.js` | URL-param config, the viewer state machine, and overlay/chrome rendering |
| `connectionManager.js` | WebSocket client to `incarnation_server` on port 8765 |
| `audioCapture.js`, `sttClient.js`, `transcriptMatcher.js` | Mic capture, STT upload, wake/dismiss phrase matching |
| `cameraDirector.js`, `pipOverlay.js`, `wipeOverlay.js`, `chatPanel.js`, `personasRegistry.js` | Kiosk camera framing, camera PiP, persona-swap wipe, chat panel, persona registry |
| `modelLoader.js`, `vrmaLoader.js`, `loadMixamoAnimation.js` | VRM / VRMA / Mixamo file loaders |
| `animationManager.js`, `expressionManager.js`, `visemeManager.js`, `lipSyncManager.js` | Runtime controllers for skeletal animation, facial expressions, mouth shapes |
| `mixamoVRMRigMap.js` | Bone-retargeting table for Mixamo → VRM |
| `creator.js` | Behavior for `creator.html` |
| `apiClient.js` | Shared `/api/v1` REST client — persona CRUD; carries the optional bearer token |
| `ui/uploader.js` | Tiny shared file-input helper |

## Home Assistant integration

playAIdes can be driven from Home Assistant in two complementary ways. Full HA-side YAML reference + manual smoke recipe lives in **[docs/ha-integration.md](docs/ha-integration.md)**. Architectural design + deferred phases are documented in **[docs/superpowers/specs/2026-04-26-ha-integration-design.md](docs/superpowers/specs/2026-04-26-ha-integration-design.md)**.

### 1. HTTP triggers (HA → playAIdes)

Four HTTP endpoints on the existing FastAPI server (port 8765), gated by a shared bearer token (`PLAYAIDES_API_KEY` env var):

| Endpoint | Purpose |
|---|---|
| `POST /api/personas/{id}/activate` | Swap the active persona on already-loaded TVs (no browser reload) |
| `POST /api/dismiss` | Send all bound clients to "no persona" (broadcasts `unload_model`, clears bindings) |
| `POST /api/event` | Generic inbound-event intake (spec §3.6) — an HA automation (or webhook / n8n / cron) fires the active persona's configured event triggers. Runs off the WS loop so a blocking skill can't stall it |
| `GET /api/state` | Read current `active_persona_id` + `bound_client_count`. Unauthenticated by design — for HA dashboard polling |

HA owns "which TV" via Browser Mod / Fully Kiosk URL routing — the existing `?persona=<id>` URL param does cold-start, the new `/activate` endpoint does hot-swap.

### 2. Skills via explicit delegation (Persona → HA)

Personas opt in by configuring `house_words` in their `persona.json`. When a user's input prefix-matches a house word, the residual is forwarded to HA's `/api/conversation/process`. HA's LLM does the tool reasoning + entity actuation; HA's response is spoken via the persona's TTS / lip-sync.

```jsonc
{
  "name": "Silver",
  "wake_words": ["Hey Silver"],
  "dismiss_words": ["Goodnight Silver"],

  "house_words": ["house"],
  "rephrase_ha_response": false,
  "ha_agent_id": "conversation.openai_assist"
}
```

Speak *"house, turn off the kitchen lights"* → HA turns off the lights → persona narrates the result.

- `house_words` empty (or field omitted) = HA delegation disabled for this persona.
- `rephrase_ha_response: true` (optional) = HA's response is restyled by the persona's own LLM before TTS. Adds one LLM call of latency, adds personality.
- `ha_agent_id` selects which HA conversation agent to address. Omit to use the global default (`HA_DEFAULT_AGENT_ID` env).

### Required env vars

```bash
export PLAYAIDES_API_KEY="some-long-random-string"      # bearer token HA must send
export HA_URL="http://homeassistant.local:8123"
export HA_TOKEN="<long-lived-token-from-HA-profile>"
export HA_DEFAULT_AGENT_ID="conversation.openai_assist" # find in Settings → Voice Assistants
```

All four also accept matching CLI flags (`--api-key`, `--ha-url`, `--ha-token`, `--ha-default-agent-id`). `PLAYAIDES_API_KEY` unset = dev mode (no auth check, with a startup warning) — don't leave it unset on a network-exposed host.

If `HA_URL` / `HA_TOKEN` aren't set, all HA features are disabled with a startup log; personas with `house_words` log a warning and behave as if `house_words` were empty.

### Quick HA-side YAML

A minimal `configuration.yaml` snippet for the HTTP triggers. Full set of examples (sample automations, REST sensor polling, Fully Kiosk launch, secrets file) is in [docs/ha-integration.md](docs/ha-integration.md):

```yaml
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

### Deferred (not yet implemented)

- **Richer HA → persona event flows.** The inbound-event endpoint itself ships (`POST /api/event`, spec §3.6 — an HA automation can fire a persona's event trigger, e.g. "door opened → say welcome home"). What remains open is deeper state-machine integration (spec § 7.1).
- **HACS `homeassistant-playaides` custom_component** so HA voice satellites can use a persona as their conversation agent. Different codebase entirely (Python in HA's runtime, HACS distribution). Spec § 7.2.

## Running

### Runtime stack

Ollama runs externally (on the host or another machine). TTS lives in the standalone
`voicebox` service (started separately). Everything else lives in `docker-compose.yml`
at the repo root: `backend` (Python + `incarnation_server`, port `8765`), a `frontend`
Vite dev server (port `5173`, for hot-reload), and `whisper` (STT).

> There are four compose files: `docker-compose.yml` (this dev stack),
> `docker-compose.harness.yml` (a self-contained full-pipeline test harness with its own
> tiny Ollama + voicebox + whisper), and `docker-compose.test.yml` / `docker-compose.live.yml`
> (the test runners — see [Tests](#tests)). The USER_GUIDE walks the harness flow.

### Harness — the all-in-one stack (easiest, and what's usually running)

The **harness bundles its own** tiny LLM (Ollama), TTS (voicebox), and STT (whisper), so
nothing external is needed — it's the simplest way to run the whole thing. A helper script
wraps the compose `-f` flag so you don't have to remember it:

```bash
bin/harness up             # start backend :8765 + frontend :5173 + llm/stt/tts (detached)
bin/harness ps             # container status
bin/harness logs backend   # recent backend logs (bounded; add a line count: logs backend 100)
bin/harness restart        # restart the backend — RARELY needed (see hot-reload below)
bin/harness down           # stop & remove everything
```

You almost never need `restart`: saving a `*.py` file hot-reloads the backend in <2 s via
`watchfiles` (the repo is bind-mounted at `/app`). Use `restart` only for non-`.py` config
(e.g. `personas/silver/persona.json`) or env changes. Equivalent without the helper:
`docker compose -f docker-compose.harness.yml up -d`.

### Dev stack (alternative — for active frontend work; needs external Ollama + voicebox)

The viewer is normally **served by the backend on `:8765`** (it serves the built
`incarnation/dist`), which is what the Fire TV / kiosk and `bin/silver-launch.py` point at.
The `:5173` Vite dev server is the hot-reload alternative for frontend development.

```bash
ollama serve                   # if not already running on the host
cp .env.example .env           # first time only; edit with your HA_TOKEN etc.
# start voicebox (TTS) as its own compose project — see docker-compose.yml header
docker compose up -d           # backend + frontend (dev) + whisper
docker compose logs -f         # tail all logs
docker compose down            # stop everything
```

Then either:

- **Built viewer (kiosk / TV path):** build it once after any `incarnation/` change with
  `cd incarnation && npx vite build`, then open `http://localhost:8765/` (the backend serves
  `incarnation/dist`). This is the URL the Fire TV and `bin/silver-launch.py` use.
- **Dev viewer (hot-reload):** open `http://localhost:5173/` for the Vite dev server with
  HMR while editing frontend code. Backend HTTP/WS stays at `http://localhost:8765/`.

Useful viewer URL params: `?theme=p5-basic|fate-basic|manga-basic|classic`, `?kiosk=1`,
`?nameplate=1`, `?quality=low`, `?cmdlog=0`, `?persona=<id>`, `?ws=` / `?api=` (point at a
remote backend).

To restart a single service: `docker compose restart backend`.

To bring up only some services: `docker compose up -d backend whisper` (skips the Vite
frontend — useful when you're running the built viewer off `:8765`).

Hot-reload works for both languages:
- Save a `*.py` file → `watchfiles` restarts the backend container in <2s
- Save a frontend file → Vite HMR pushes the patch to the open `:5173` browser tab (rebuild `incarnation/dist` to refresh the `:8765`-served build)

### Switching LLM backends

The backend is just a `.env` change. The project doesn't know or care
which OpenAI-compatible API serves it.

```bash
# host Ollama (default)
LLM_URL=http://host.docker.internal:11434/v1
LLM_MODEL=gemma3:4b

# llamacpp-wrapper (better MoE control, faster on supported models)
LLM_URL=http://host.docker.internal:8081/v1
LLM_MODEL=gemma4-26b-q4
```

Then `docker compose down && docker compose up -d` to pick up the change.

See `.env.example` for more options. The backend default timeout is
120s to cover llamacpp-wrapper cold-start (~25-30s on Q4 first hit
while llama-swap spawns the llama-server child).

### Tests

```bash
bin/test                       # Python unit + integration (~25s wall, 1.8s pytest)
bin/test-js                    # Frontend Vitest
bin/test-all                   # both, sequentially
bin/test-live                  # full E2E with real Ollama + TTS containers (GPU needed)
bin/coverage                   # run tests + copy coverage.xml to repo root
bin/shell                      # interactive bash in the test image (run pytest natively for sub-second feedback)
bin/js-shell                   # interactive bash in the js-tests image
bin/clean                      # tear all stacks down + remove caches
```

`bin/test` passes extra args through to pytest:

```bash
bin/test pytest tests/unit -k ha_client -v
```

Each `bin/` script is a few lines of bash — `cat bin/test` shows exactly what it runs.

Test layout:

```
tests/
├── conftest.py        # Shared fixtures (mock LLM, fake TTS, tmp personas dir, live-endpoint skippers)
├── unit/              # No network, no threads — pure logic
├── integration/       # FastAPI TestClient (HTTP + WebSocket)
└── live/              # Real Ollama + TTS — marked `live`, auto-skipped when URLs unset
```

Live tests auto-skip when `LLM_URL` / `TTS_URL` aren't set or unreachable, so `bin/test` is always green regardless of which backend services are running.

## Notes
Can't push model and persona files to GitHub because of licensing/size.
