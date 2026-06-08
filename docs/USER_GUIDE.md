# User guide

## What it is

playAIdes drives a 3D VRoid avatar ("Silver") on a screen (e.g. a Fire TV) you talk to by
voice or text; it can show camera feeds and act through Home Assistant. The front-end
viewer (`incarnation/`) renders the avatar plus a themeable "game-UI" chrome.

## Setup

- **Backend + services** run as a Docker Compose stack — start it with `bin/harness up`
  (wraps `docker compose -f docker-compose.harness.yml up -d`): backend on `:8765` plus
  ollama / whisper / voicebox. The helper also has `down`, `ps`, `logs`, `restart`.
- **Front-end** (the viewer the backend serves): `cd incarnation && npm install` (first
  time), then `npx vite build` → outputs `incarnation/dist`, served by the backend at `/`.
- **Home Assistant** (optional): set `HA_URL` / `HA_TOKEN` in `.env`
  (see `README.md` → "Home Assistant integration").
- Full details live in the repo `README.md` (Running + HA sections).

## Getting the assets (characters & animations)

The avatar models and animations are **not** included in the repo — characters are kept
private, and the animation pack can't be legally redistributed (see the license note below).
A fresh clone runs the UI but has no avatar to show until you supply two things. Both live
under gitignored paths, so your assets stay local and won't get committed.

### 1. A character (VRM model + persona)

1. Get a `.vrm` avatar — make one for free in
   [VRoid Studio](https://vroid.com/en/studio), or use any VRM you have the rights to.
2. Drop the model under the viewer's models dir:
   `incarnation/public/models/<name>/<name>.vrm`
3. Add a persona so the backend can load it — create `personas/<id>/persona.json`
   pointing at the model (`model_url` is relative to `incarnation/public/`):

   ```json
   {
     "name": "Aria",
     "is_default": true,
     "avatar": {
       "model_url": "models/aria/aria.vrm",
       "idle_animation": "model_pose",
       "intro_animation": "VRMA_01"
     }
   }
   ```

   The backend loads the persona with `is_default: true` (else the first alphabetically).
   `personas/handy.json` is a minimal reference example. You can also upload a VRM live from
   the creator UI (`POST /api/upload/avatar`).

### 2. Animations (VRMA pack)

The viewer plays `.vrma` (VRM Animation) clips from `incarnation/public/vrma/animations/`.
Each file's name (without `.vrma`) is the clip name personas reference via `idle_animation`
/ `intro_animation`; the built-in fallback idle is `model_pose` (`DEFAULT_IDLE_ANIMATION` in
`playAIdes.py`).

1. Download the free **VRoid Project "VRM Animation" 7-pack** from the official BOOTH page:
   <https://vroid.booth.pm/items/5512385> (motions: full-body, greeting, peace sign, shoot,
   spin, model pose, squat).
2. Copy the `.vrma` files into `incarnation/public/vrma/animations/`. Ensure a
   `model_pose.vrma` exists for the default idle (the pack's "Model pose" is `VRMA_06`).

**License:** copyright pixiv Inc.; free to use (including commercially) but **do not
redistribute the raw/riggable files** — that's why they aren't bundled here. If you use them,
credit *"Animation credits to pixiv Inc.'s VRoid Project"*. Full terms ship in the pack's
readme.

## Run it

```bash
# 1. bring up the harness (backend + LLM/STT/TTS); stop later with: bin/harness down
bin/harness up

# 2. (re)build the viewer after any incarnation/ change
cd incarnation && npx vite build

# 3a. open the viewer in a browser
#     http://192.168.0.7:8765/                         # default theme = p5-basic
#     http://192.168.0.7:8765/?kiosk=1&nameplate=1     # TV / kiosk

# 3b. or launch it on a Fire TV via Home Assistant — from the CLI:
bin/silver-launch.py bedroom                            # also: box8 | living
#     ...or self-service: open data/control.html → "Fire TV" buttons (pick a theme + TV)
```

Useful viewer URL params: `?theme=p5-basic|fate-basic|manga-basic|classic`, `?kiosk=1`,
`?nameplate=1`, `?quality=low` (drop heavy FX on weak GPUs), `?cmdlog=0` (hide the command
console), `?ws=` / `?api=` (point at a remote backend).

The **manga** theme's backdrop is a focus-line (集中線) montage — 4 panels split by angled
gutters. Dev-only, tune it live (no rebuild) on the manga theme:
`?theme=manga-basic&scrim=.25&gap=2&lw=.6` — `scrim` = darkening over the panels, `lw` =
speed-line thickness, `gap` = line spacing (bigger = sparser). Omit them for the baked-in
defaults. (The angled gutters between panels are fixed in the CSS, not a URL knob.)

## Examples / common tasks

- **See a theme:** `http://192.168.0.7:8765/?theme=p5-basic`
- **Compare all theme widgets (dev/design):** open `incarnation/design-preview.html` via the Vite dev server (`:5173`, switch with `?theme=`) — a full game-UI eval page, not the live viewer.
- **Camera in the PiP:** open `http://192.168.0.7:8765/data/control.html` → "Show camera on TV".
  The entity field defaults to `camera.printer_gym_camera_hd_stream` (a lighter `_sd_stream`
  also exists); edit it to point at any HA camera entity_id.
- **Test audio (greet):** `data/control.html` → "Say on TV" (or HA `script.silver_greet`).
- **Talk to Silver (mic):** open `control.html` over **HTTPS** (`https://playaides-local.hogu.dev/data/control.html`) → hold "Talk to Silver" and speak; the mic needs a secure context, and Silver's reply plays on the bound TV.
- **Launch on the bedroom TV:** `bin/silver-launch.py bedroom`.

## Troubleshooting

Common issues are tracked in [CONTINUITY.md](../CONTINUITY.md#known-issues).
