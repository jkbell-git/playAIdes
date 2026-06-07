# Continuity log

## Now & Next

Building a **themeable "game-UI" chrome** for the `incarnation/` viewer — a Persona-5 /
Fate / Manga look inspired by ChatGPT concept images (saved by the user in the folder
*above* this repo). Work is on branch **`feat/ui-theme-camera-split`** (off
`feat/persona-skill-framework`), not merged.

**Right now:** `p5-basic` is the default theme, live and being tested on the bedroom Fire
TV (Cube, `media_player.fire_tv_192_168_0_233`). It has the full chrome: red-room backdrop
(slash + ritual ring + grain + vignette), slashy date masthead, star nameplate, torn-white
camera PiP, torn black dialogue box, red diamond mic, and a sanitized command-log console
under the PiP.

**Next concrete steps:**
1. Resolve the two Fire-TV launch issues (see *Known issues*: fullscreen + audio test).
2. Build **`fate-basic`** (navy/indigo + gold filigree) and **`manga-basic`** (B&W
   halftone/ink) reusing the p5-basic chrome structure.
3. Then `-max` variants with custom art when the user supplies PNGs.

Test/iterate loop: edit `incarnation/` → `cd incarnation && npx vite build` → reload
`http://192.168.0.7:8765/` (backend serves `incarnation/dist`). Launch on the TV with
`bin/silver-launch.py bedroom`.

## TODO

- [ ] Build `fate-basic` theme (navy/indigo + gold filigree) — reuse p5-basic chrome.
- [ ] Build `manga-basic` theme (B&W halftone / ink / torn paper) — reuse p5-basic chrome.
- [ ] Add `-max` theme variants (custom art): user supplies transparent PNGs (torn frames,
      ornate emblems, splatter); agent wires them via `border-image` / overlays.
- [ ] **Update the stale spec** `docs/superpowers/specs/2026-06-07-ui-theme-system-camera-split-design.md`
      — it still says "camera split"; reality is camera = inked PiP, and the split is parked
      for a future multi-3D-model "cast".
- [ ] If Fire TV perf is poor, **bake** the p5 grain + torn-slash to static PNGs
      ("lock the look → bake"); `?quality=low` already drops them as a stopgap.
- [ ] Remove the throwaway preview mock `data/_mock_p5.html` when done.
- [ ] (optional) Install `ha/silver_launch.yaml` in HA + tune the bedroom audio-unlock tap.
- [ ] Refresh the README "Incarnation pages" + "Running" sections — stale: they describe
      the Vite dev server on `:5173` and three HTML pages, but the viewer is now served by
      the backend on `:8765` and has the theme system. (User to do next session.)

## Known issues

- **[major, Fire TV / Silk] Viewer doesn't go fullscreen** — Silk's chrome/address bar
  stays; the viewer's `requestFullscreen()` on first gesture isn't honored on Fire TV Silk.
  Surfaced: 2026-06-07 (bedroom Cube). Workaround/fix: a kiosk browser app (Fully Kiosk),
  or Silk-specific fullscreen handling. Not yet implemented.
- **[major, Fire TV / audio] No audio on launch** — partly expected: `bin/silver-launch.py`
  only *opens* the viewer; Silver doesn't speak until a greet/conversation, so there's
  nothing to hear yet. To test audio, trigger `script.silver_greet` or `data/control.html` →
  "Say on TV". The audio-unlock `input tap 960 540` may also miss if the Samsung isn't 1080p
  — tune `bin/silver-launch.py --tap X Y`. Surfaced: 2026-06-07.
- **[minor, perf] p5-basic effects may be heavy on the Fire TV Cube** — SVG
  turbulence/displacement (torn frames) + film grain. `?quality=low` (sets `body.lowfx`)
  drops the grain + big slash filter. "Bake to PNG" is the durable fix if still heavy.
- **[minor] `data/_mock_p5.html`** — an untracked throwaway preview mock (served at
  `/data/_mock_p5.html`); delete when theming is settled.

## Decisions

- [2026-06-07] **UI direction:** themeable game-UI chrome (Persona 5 / Fate / Manga) from
  ChatGPT concept images. Naming: `<theme>-basic` = procedural CSS/SVG, no custom art
  (shipping now); `<theme>-max` = with custom art assets (later). Default = `p5-basic`.
- [2026-06-07] **Camera = floating PiP** with a theme-selectable inked/comic frame —
  **not** a screen split. The split-screen primitive (`stageLayout.js` + CSS + DOM) is
  parked for a future multi-3D-model "cast" view. (Earlier camera-split work was redirected.)
- [2026-06-07] **Transparent 3D canvas** (`scene.js`: renderer `alpha:true` +
  `scene.background=null`) so the themed CSS backdrop shows behind the avatar.
- [2026-06-07] **Frontend architecture** (see `docs/frontend-architecture.md`): Vite
  multi-page app; the kiosk/viewer stays **vanilla** (perf, old Fire TV Silk); **React** is
  allowed for future PC/mobile pages (character creation/customization); the CSS theme
  tokens are the shared cross-framework layer. No React in the viewer. Rejected: rewriting
  the viewer in React (no benefit, bigger bundle, worse on Silk).
- [2026-06-07] **3-layer CSS theme system** (palette → semantic roles → `[data-theme]`
  recipes) in `tokens.css`; precomputed alpha tokens (no `color-mix()` — old Silk).
- [2026-06-07] **Command-log console** (p5-basic): shows the real WS command stream,
  sanitized (secret fields → `***`, host/IP → `playaides`, truncated); fades like the
  subtitles; opt-out via `?cmdlog=0`.
- [2026-06-07] **`bin/silver-launch.py`** replicates the `ha/silver_launch.yaml` launch
  sequence via the HA REST API (reads `HA_TOKEN` from env/`.env`, never printed) — makes
  the previously one-off TV launch reproducible.
