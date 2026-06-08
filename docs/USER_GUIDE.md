# User guide

## What it is

playAIdes drives a 3D VRoid avatar ("Silver") on a screen (e.g. a Fire TV) you talk to by
voice or text; it can show camera feeds and act through Home Assistant. The front-end
viewer (`incarnation/`) renders the avatar plus a themeable "game-UI" chrome.

## Setup

- **Backend + services** run via Docker Compose (the dev/test stack):
  `docker compose -f docker-compose.harness.yml up -d` — backend on `:8765` plus
  ollama / whisper / voicebox.
- **Front-end** (the viewer the backend serves): `cd incarnation && npm install` (first
  time), then `npx vite build` → outputs `incarnation/dist`, served by the backend at `/`.
- **Home Assistant** (optional): set `HA_URL` / `HA_TOKEN` in `.env`
  (see `README.md` → "Home Assistant integration").
- Full details live in the repo `README.md` (Running + HA sections).

## Run it

```bash
# 1. bring up the harness (backend + LLM/STT/TTS)
docker compose -f docker-compose.harness.yml up -d

# 2. (re)build the viewer after any incarnation/ change
cd incarnation && npx vite build

# 3a. open the viewer in a browser
#     http://192.168.0.7:8765/                         # default theme = p5-basic
#     http://192.168.0.7:8765/?kiosk=1&nameplate=1     # TV / kiosk

# 3b. or launch it on a Fire TV via Home Assistant
bin/silver-launch.py bedroom                            # also: box8 | living
```

Useful viewer URL params: `?theme=p5-basic|fate-basic|manga-basic|classic`, `?kiosk=1`,
`?nameplate=1`, `?quality=low` (drop heavy FX on weak GPUs), `?cmdlog=0` (hide the command
console), `?ws=` / `?api=` (point at a remote backend).

## Examples / common tasks

- **See a theme:** `http://192.168.0.7:8765/?theme=p5-basic`
- **Compare all theme widgets (dev/design):** open `incarnation/design-preview.html` via the Vite dev server (`:5173`, switch with `?theme=`) — a full game-UI eval page, not the live viewer.
- **Camera in the PiP:** open `http://192.168.0.7:8765/data/control.html` → "Show camera on TV".
- **Test audio (greet):** `data/control.html` → "Say on TV" (or HA `script.silver_greet`).
- **Launch on the bedroom TV:** `bin/silver-launch.py bedroom`.

## Troubleshooting

Common issues are tracked in [CONTINUITY.md](../CONTINUITY.md#known-issues).
