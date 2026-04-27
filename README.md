# playAIdes

What's working:

**PlayAIdes**
- Chatting with Ollama
- Loading personas from JSON files
- Basic chat interface
- Home Assistant integration — HTTP triggers (swap / dismiss / state) and skills delegation via per-persona `house_words` (see [Home Assistant integration](#home-assistant-integration) below)

**Incarnation**
- Basic model loading (local file)
- Basic animation loading (local file)
- Animation playback over WebSockets

## Incarnation pages

The `incarnation/` directory is a Vite app (`npm run dev`, default port `5173`) that serves three top-level HTML pages. Open each at `http://localhost:5173/<filename>`.

| Page | URL | Status |
|------|-----|--------|
| **Viewer** | `/index.html` (or `/`) | next slated for redesign |
| **Persona Forge** (persona creator) | `/creator.html` | active |

### `index.html` — Viewer

Full-screen 3D canvas. This is what runs during a live chat session: the loaded VRM stands in the center, animations play over WebSocket commands from `playAIdes.py`, and lip-sync visemes drive the mouth from the streaming TTS audio. No interactive UI besides camera orbit and a tiny status pill in the bottom-left. Chat input still happens in the terminal.

- **Entry script**: `src/main.js`
- **Styles**: `styles/main.css`
- **Used by**: `python main.py … --use_avatar` (the page is the `incarnation_server` WS client)

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
| `scene.js` | Three.js scene/camera/renderer for the **Viewer** (window-sized) |
| `creatorScene.js` | Same idea but bound to a specific canvas, used by Persona Forge |
| `incarnation.js` | Top-level orchestrator for the Viewer (model + managers + WS dispatch) |
| `connectionManager.js` | WebSocket client to `incarnation_server` on port 8765 |
| `modelLoader.js`, `vrmaLoader.js`, `loadMixamoAnimation.js` | VRM / VRMA / Mixamo file loaders |
| `animationManager.js`, `expressionManager.js`, `visemeManager.js`, `lipSyncManager.js` | Runtime controllers for skeletal animation, facial expressions, mouth shapes |
| `mixamoVRMRigMap.js` | Bone-retargeting table for Mixamo → VRM |
| `creator.js` | Behavior for `creator.html` |
| `ui/uploader.js` | Tiny shared file-input helper |

## Home Assistant integration

playAIdes can be driven from Home Assistant in two complementary ways. Full HA-side YAML reference + manual smoke recipe lives in **[docs/ha-integration.md](docs/ha-integration.md)**. Architectural design + deferred phases are documented in **[docs/superpowers/specs/2026-04-26-ha-integration-design.md](docs/superpowers/specs/2026-04-26-ha-integration-design.md)**.

### 1. HTTP triggers (HA → playAIdes)

Three HTTP endpoints on the existing FastAPI server (port 8765), gated by a shared bearer token (`PLAYAIDES_API_KEY` env var):

| Endpoint | Purpose |
|---|---|
| `POST /api/personas/{id}/activate` | Swap the active persona on already-loaded TVs (no browser reload) |
| `POST /api/dismiss` | Send all bound clients to "no persona" (broadcasts `unload_model`, clears bindings) |
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

- **HA → persona event triggers** ("door opened → say welcome home"). State-machine integration is the open design question. Spec § 7.1.
- **HACS `homeassistant-playaides` custom_component** so HA voice satellites can use a persona as their conversation agent. Different codebase entirely (Python in HA's runtime, HACS distribution). Spec § 7.2.

## Running the test suite

Everything runs in Docker — **no Python or dependencies need to be installed on the host**. Only requirements are `docker` + `docker compose` + `make`.

```bash
make test           # Unit + integration tests (fast, offline)
make test-unit      # Unit tests only
make test-integration  # FastAPI TestClient integration tests only
make test-live      # End-to-end against real Ollama + TTS containers (needs NVIDIA GPU for TTS)
make coverage       # Run tests and export coverage.xml to the repo root
make shell          # Drop into a shell in the test image for poking around
make clean          # Tear down containers, volumes, and .test-output/
```

Test layout:

```
tests/
├── conftest.py        # Shared fixtures (mock LLM, fake TTS, tmp personas dir, live-endpoint skippers)
├── unit/              # No network, no threads — pure logic
├── integration/       # FastAPI TestClient (HTTP + WebSocket)
└── live/              # Real Ollama + TTS — marked `live`, auto-skipped when URLs unset
```

Live tests auto-skip when `OLLAMA_URL` / `TTS_URL` aren't set or unreachable, so `make test` is always green regardless of which backend services are running.

## Notes
Can't push model and persona files to GitHub because of licensing/size.
