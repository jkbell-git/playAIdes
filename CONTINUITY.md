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

**`fate-basic` + `manga-basic` are built, user-approved, AND wired into the live viewer**
(2026-06-07). The full game-UI (Topics list, action menu, bond pips, status meter, control
bar) is evaluated on the **design-preview page**; the live viewer now re-skins the REAL
chrome (nameplate, date, camera PiP, dialogue, mic, backdrop) — switch with
`?theme=fate-basic|manga-basic` on `:8765` (rebuilt). Decorative widgets stay preview-only
(not in `index.html`'s DOM). To wire them live, `viewer.css` `@import`s the theme files and
`index.html` gained the fate/manga backdrop fx layers + an `#ink-edge` SVG filter. p5-basic
is unchanged. See *Decisions*. NO Japanese in manga (look only).

**Next concrete steps:**
1. Resolve the two Fire-TV launch issues (see *Known issues*: fullscreen + audio test).
2. (Optional, on demand) **Wire a chosen theme live**: one-line `@import` of its `theme-*.css`
   into `viewer.css` — only the real elements re-skin; the decorative widgets stay
   preview-only (they're not in `index.html`'s DOM).
3. Polish: manga PiP's "GYM CAM · LIVE / ● REC" labels are cramped at the panel's top edge.
4. Then `-max` variants with custom art when the user supplies PNGs.

Test/iterate loop: edit `incarnation/` → `cd incarnation && npx vite build` → reload
`http://192.168.0.7:8765/` (backend serves `incarnation/dist`). Launch on the TV with
`bin/silver-launch.py bedroom`.

## TODO

- [x] Build `fate-basic` theme (navy/indigo + gold filigree). Done 2026-06-07, full game-UI.
- [x] Build `manga-basic` theme (B&W halftone / ink / torn paper, no JP). Done 2026-06-07.
- [x] Wire fate/manga into the live viewer (`viewer.css` @imports + `index.html` fx layers +
      `#ink-edge` filter). Done 2026-06-07 — all three themes selectable live via `?theme=`.
- [ ] Polish: manga PiP top labels ("GYM CAM · LIVE / ● REC") are cramped on the panel edge.
- [ ] (Optional refactor) Extract the live p5 rules from `viewer.css` into a `theme-p5.css`
      for symmetry with fate/manga. Skipped now to avoid destabilising the on-TV p5 build;
      everything bundles into one CSS so it's cosmetic-only. See *Decisions* (CSS split).
- [ ] Add `-max` theme variants (custom art): user supplies transparent PNGs (torn frames,
      ornate emblems, splatter); agent wires them via `border-image` / overlays.
- [ ] **Update the stale spec** `docs/superpowers/specs/2026-06-07-ui-theme-system-camera-split-design.md`
      — it still says "camera split"; reality is camera = inked PiP, and the split is parked
      for a future multi-3D-model "cast".
- [ ] If Fire TV perf is poor, **bake** the p5 grain + torn-slash to static PNGs
      ("lock the look → bake"); `?quality=low` already drops them as a stopgap.
- [ ] Delete `data/_mock_p5.html` — now SUPERSEDED by `incarnation/design-preview.html`.
      (Agent's `rm` was blocked by the permission classifier; user to remove or approve.)
- [ ] (optional) Install `ha/silver_launch.yaml` in HA + tune the bedroom audio-unlock tap.
- [x] Refresh the stale README (Incarnation pages / Viewer / Running + HA endpoint count).
      Done 2026-06-07 via a living-docs sweep (full rewrite adopted from `LivDoc-README.md`).

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
- **[minor] `data/_mock_p5.html`** — throwaway p5 mock, now superseded by
  `incarnation/design-preview.html` (the switchable p5/fate/manga eval page). Safe to delete.

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
- [2026-06-07] **Full game-UI is design-eval only; decorative widgets are CSS-only.** The
  reference art (P5/Fate/Manga) shows many widgets — Topics list, action menu, bond pips,
  status meter (MOOD / Master-AP), control bar — that have NO backing data. They are styled
  but **never added to the live viewer DOM** (keeps the Fire TV lean). They render only on
  `incarnation/design-preview.html`, a switchable (p5/fate/manga, `?theme=`) page used to
  evaluate the look. The live viewer keeps showing only the real subset (date, nameplate,
  camera PiP, dialogue, mic, command-log, backdrop).
- [2026-06-07] **Per-theme source files, single served bundle.** New files
  `styles/theme-fate.css`, `styles/theme-manga.css`, `styles/theme-p5-extra.css` (p5's new
  widgets). The live `viewer.css` / `index.html` were left UNTOUCHED (p5 is mid-test on the
  TV — no regression risk). Rationale on perf: Vite bundles all CSS into one hashed
  `/assets/*.css`, and the backend has no `/styles` mount + a SPA catch-all, so true runtime
  per-theme lazy-loading would fight the build. The real Fire-TV cost is RENDER (turbulence
  filters, grain, blend modes) and only the active `[data-theme]` triggers those — inactive
  themes match no live DOM. So one bundle is already performant; the split is for
  maintainability. Each theme re-points the semantic tokens (`--bg`/`--gold`/`--cream`/
  `--font-*`/`--ink-a*`) so the base chrome inherits its colours, then overrides shape/position.
- [2026-06-07] **No Japanese in manga-basic** (user call): B&W halftone/ink/torn-paper LOOK
  with English labels; don't fabricate JP strings that aren't in the data. Layouts mirror
  each reference (fate/manga: nameplate top-left, secondary info top-right) since position is
  just a per-theme CSS property on the shared DOM.
