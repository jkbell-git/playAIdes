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

**This session (2026-06-08), still on `feat/ui-theme-camera-split`:** the three themes
remain live-selectable; several refinements landed. (1) **Camera works again** — HA
removed/re-added the gym camera, so the hardcoded entity moved from
`camera.printer_gym_camera_live_view` to **`camera.printer_gym_camera_hd_stream`** (a
lighter `_sd_stream` also exists) across `personas/silver/persona.json`, `data/control.html`,
`ha/silver_launch.yaml`, `ha/README.md`. (2) The **manga backdrop pivoted to a focus-line
(集中線) montage** — 4 panels carved by two diagonal `clip-path` seams (genuinely angled
gutters), pure-CSS conic-gradient speed-lines (the hand-placed SVG was dropped), de-browned
to neutral B&W with charcoal `#34302a` darks. Tune it live without a rebuild via
`?scrim=&gap=&lw=` (dev-only; no params = baked defaults). (3) **PiP geometry is now one
shared source** (`:root --pip-top/--pip-left/--pip-w` in `viewer.css`); every theme derives
from the base so the PiP can't drift (fixed a bug where it had been tuned on
`[data-theme=p5-basic]`, leaving fate/manga smaller). (4) **Fate masthead now shows
month + weekday** (e.g. `JUN 07 SAT`) instead of the time-of-day word.

**Next concrete steps:**
1. ~~Fire-TV address-bar / fullscreen~~ **DONE 2026-06-08** — KEYCODE_MENU (82) ×2 hides
   Silk's bar, confirmed on the Cube. Remaining launch item: the audio-on-launch test (see
   *Known issues*).
2. Surface a "camera unavailable" notice in the viewer — right now an offline HA camera
   fails silently (see *Known issues*).
3. Bake/finalize the manga montage tuning (`scrim`/density) into the CSS defaults once the
   look is locked, and retire the dev `?scrim/gap/lw` knobs.
4. Then `-max` variants with custom art when the user supplies PNGs.

Test/iterate loop: edit `incarnation/` → `cd incarnation && npx vite build` → reload
`http://192.168.0.7:8765/` (backend serves `incarnation/dist`). Launch on the TV with
`bin/silver-launch.py bedroom`.

## TODO

- [x] Build `fate-basic` theme (navy/indigo + gold filigree). Done 2026-06-07, full game-UI.
- [x] Build `manga-basic` theme (B&W halftone / ink / torn paper, no JP). Done 2026-06-07.
- [x] Wire fate/manga into the live viewer (`viewer.css` @imports + `index.html` fx layers +
      `#ink-edge` filter). Done 2026-06-07 — all three themes selectable live via `?theme=`.
- [~] Polish: manga PiP top labels ("GYM CAM · LIVE / ● REC") at the panel edge. RE-EVAL'd
      2026-06-08 — the PiP now derives from the shared base geometry (same size/position in
      every theme), so the manga-specific cramping is largely resolved; verify on the TV and
      close if the labels now fit.
- [ ] (Optional refactor) Extract the live p5 rules from `viewer.css` into a `theme-p5.css`
      for symmetry with fate/manga. PARTIALLY superseded 2026-06-08 — the PiP geometry was
      hoisted to a shared `:root` base (per-theme rules keep only skin), so the base/skin
      split now exists for the PiP; the rest of p5's live rules are still inline in
      `viewer.css`. See *Decisions* (CSS split, shared PiP geometry).
- [ ] (optional) Full month/weekday NAMES for the fate masthead (currently abbreviated, e.g.
      `JUN 07 SAT`). Date data already carries the abbreviated form; long form would need
      either richer date data or client-side expansion.
- [ ] (optional) Surface a "camera unavailable" notice in the viewer when an HA camera is
      offline (see *Known issues* — `skills/pip.py` currently fails silently).
- [ ] (optional) Bake the manga montage tuning (`scrim`/line-density) into the CSS defaults
      once the look is locked, then drop the dev-only `?scrim/gap/lw` URL knobs.
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

- **[minor, Fire TV / Silk] Viewer doesn't go truly fullscreen** — Silk keeps its URL bar;
  `requestFullscreen()` is NOT honored on Fire TV Silk (confirmed 2026-06-08) and touch
  swipes are ignored (Fire TV is remote-driven). **RESOLVED 2026-06-08:** the launch sends
  KEYCODE_MENU (`input keyevent 82`) ×2 — the remote's Menu / hamburger button — which DOES
  hide the bar (confirmed working on the bedroom Cube; `bin/silver-launch.py --menu-presses`,
  default 2). The earlier DPAD_DOWN scroll attempt did NOT hide it. The bar still re-shows on
  Silk's ~6 h refresh — accepted as good-enough. Kiosk-browser alternatives evaluated in
  `docs/firetv-kiosk-browsers.md`. Surfaced 2026-06-07.
- **[major, Fire TV / audio] No audio on launch** — partly expected: `bin/silver-launch.py`
  only *opens* the viewer; Silver doesn't speak until a greet/conversation, so there's
  nothing to hear yet. To test audio, trigger `script.silver_greet` or `data/control.html` →
  "Say on TV". The audio-unlock `input tap 960 540` may also miss if the Samsung isn't 1080p
  — tune `bin/silver-launch.py --tap X Y`. Surfaced: 2026-06-07.
- **[minor, perf] p5-basic effects may be heavy on the Fire TV Cube** — SVG
  turbulence/displacement (torn frames) + film grain. `?quality=low` (sets `body.lowfx`)
  drops the grain + big slash filter. "Bake to PNG" is the durable fix if still heavy.
- **[minor, Fire TV GPU] Avatar renders with wireframe dress + banded face on the Cube** —
  the VRM is FINE (clean on desktop, 2026-06-08); the Cube's GPU mangles the normal-mapped
  knit + layered face decals. NOT z-fighting: `?gpufix=1` (tighter near plane) did not help,
  so it's shader/normal precision (mediump) on the weak GPU — a hardware limit. Options if
  it matters: strip the dress normal map (loses knit detail), a lighter model, or accept.
  Surfaced 2026-06-08 (bed + living).
- **[minor, perf] Slow avatar load on weak TVs (bed + living)** — Silver's VRM is ~16 MB,
  downloaded + GPU-uploaded fresh. Mitigated: a loading overlay (so it reads as loading, not
  frozen) + a `?quality=low` launch toggle. Durable fix: slim the VRM (texture downscale +
  Draco/meshopt). Surfaced 2026-06-08.
- **[minor] `data/_mock_p5.html`** — throwaway p5 mock, now superseded by
  `incarnation/design-preview.html` (the switchable p5/fate/manga eval page). Safe to delete.
- **[minor, UX] Offline HA camera fails silently** — when an HA camera entity is
  `unavailable`/offline, `skills/pip.py` `show_pip` returns `SkillResult(ok=False, error=...)`
  and sends nothing to the viewer: no PiP, no on-screen "camera unavailable" notice, so it
  looks like a bug to the user. Surfaced 2026-06-08. Fix: have `show_pip` push a viewer
  notice on the unresolved-source / offline path.

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
- [2026-06-08] **Manga backdrop → focus-line (集中線) montage** (PIVOT). Replaced the earlier
  dark-seinen / hand-placed-SVG direction with a full-page montage of radial speed-lines
  drawn purely in CSS (`repeating-conic-gradient`); dropped the SVG, de-browned to neutral
  B&W. The manga *chrome* (PiP/dialogue ink frames) is unchanged — only the *backdrop* pivoted.
  Rejected: keeping the hand-authored SVG (harder to tune, brown cast).
- [2026-06-08] **Manga montage = 4 panels with angled gutters** (clip-path). Simplified the
  initial 7-panel grid to 4 panels carved by two diagonal `clip-path` seams, so the gutters
  are genuinely angled rather than orthogonal. Retired the grid/border/`tilt` knobs; kept
  `scrim` + line-density (`lw`) as the live tuning dials, plus charcoal `#34302a` darks
  (lightened from near-black `#15120d`). Tunable live via dev-only `?scrim/gap/lw` (no rebuild).
- [2026-06-08] **Shared PiP geometry: tune the base, not per-theme.** PiP size/position lives
  once in `viewer.css` `:root` (`--pip-top/--pip-left/--pip-w`); the base `.pip-overlay` and
  all three cmd-logs derive from it, and per-theme rules keep only skin (p5 torn frame +
  intentional `rotate(-3deg)` slant; fate gold frame; manga ink frame). Fixes a drift bug
  where the PiP had been tuned on `[data-theme=p5-basic]` instead of the base, shrinking the
  fate/manga PiP. Rejected: continuing to set geometry per-theme (drifts).
- [2026-06-08] **Camera entity repointed to `camera.printer_gym_camera_hd_stream`.** HA
  removed and re-added the gym camera, retiring `camera.printer_gym_camera_live_view`; the
  hardcoded id was updated everywhere it's baked in (persona voice trigger, dev panel
  default, HA launch YAML + README). A lighter `_sd_stream` exists as an alternative. (The
  `demo_camera` event already templates `{payload.source}`, so the control panel stays generic.)
- [2026-06-08] **Fate masthead shows month + weekday** (e.g. `JUN 07 SAT`, weekday as the
  gold hero) instead of the time-of-day word (AFTERNOON/EVENING). CSS-only, fate-scoped,
  reuses the existing abbreviated date data.
- [2026-06-08] **Kiosk browser = stay on Silk** (no app install). The launch hides Silk's
  URL bar with KEYCODE_MENU presses (`input keyevent 82` ×2; `bin/silver-launch.py
  --menu-presses`) — the remote's Menu / hamburger button, confirmed working on the Cube; the
  ~6 h reappear is accepted. (DPAD_DOWN remote-scroll was tried first and did NOT hide it.)
  `requestFullscreen()` + touch swipes don't work on Silk.
  Dedicated kiosk browsers (Fully Kiosk = sideload but best, REST API + HA integration;
  ClickSimply Kiosk = Appstore, no sideload) were evaluated and parked in
  `docs/firetv-kiosk-browsers.md` for the future. Also added control.html launch toggles
  (`?quality=low`, `?gpufix=1`) for on-device testing. Rejected for now: installing a kiosk
  browser (sideload friction / app overhead) when Silk is good-enough.
