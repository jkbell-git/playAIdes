# playAIdes

What's working:

**PlayAIdes**
- Chatting with Ollama
- Loading personas from JSON files
- Basic chat interface

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
