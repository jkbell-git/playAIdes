# Continuity log

## Now & Next

The active focus has **pivoted to a clean backend/frontend re-architecture** (2026-06-09).
playAIdes is a proven POC with no live users yet — the right moment to replace the two
god-objects (`incarnation_server.py` + `playAIdes.py`, circularly dependent) with a layered
backend behind a **stable, versioned API contract** (the ICD). The contract (REST `/api/v1/…`
for request/response; a narrow WebSocket for the live avatar loop) lets the frontend be built
once and survive backend churn. See the standing reference:
`docs/superpowers/specs/2026-06-09-backend-frontend-architecture-redesign.md`.

**Slice 1 — Integrations Console — DONE and merged to `main` (2026-06-09).** New
`backend/` package (`api`/`clients`/`stores`) is live. A generic provider seam
(`health/discover/invoke`), HA provider, config + write-only secrets stores, one-time
migration seed, a `/api/v1/integrations` APIRouter mounted into `incarnation_server.py`,
and a React console page at **`/console`** (Vite MPA, all four pages now built via
`incarnation/vite.config.js`). 41 backend tests + full JS suite green. `silver-launch.py`
rewired to read launch targets from the config store. PiP is now a **generic display slot**
(`{kind:"camera",...}` or `{kind:"url",...}`), not a camera-only field.

**Slice 2 — ConversationService + DisplayChannel — DONE and merged to `main` (2026-06-09).**
`ConversationService` extracted from `PlayAIdes.chat` (`backend/services/conversation.py`);
`DisplayChannel` push port introduced (`backend/ports/display.py` + `WebSocketDisplayChannel`)
breaking the circular `incarnation_server ⇄ PlayAIdes` dependency; WS live channel + REST
`POST /api/v1/personas/{id}/messages` both wired to the same service; `LLMInterface.chat_stream`
added. 42 tests green (33 plain-container + 9 harness); live-verified (Silver replied via
the new REST endpoint). Viewer subtitle flow unchanged. The final holistic review caught an
8-test turn-path regression in pre-existing fixtures (Task 6's gate was too narrow); fixed.

*(Background context: the UI theme work — p5-basic/fate-basic/manga-basic chrome for the
Fire TV viewer — was completed on `feat/ui-theme-camera-split` and is merged. Those themes
remain the live look; see Decisions for the full theme history.)*

## TODO

- [x] Build `fate-basic` theme (navy/indigo + gold filigree). Done 2026-06-07, full game-UI.
- [x] Build `manga-basic` theme (B&W halftone / ink / torn paper, no JP). Done 2026-06-07.
- [x] Wire fate/manga into the live viewer (`viewer.css` @imports + `index.html` fx layers +
      `#ink-edge` filter). Done 2026-06-07 — all three themes selectable live via `?theme=`.
- [x] **Integrations console v1** — generic provider seam + HA provider + config/secrets
      stores + `/api/v1/integrations` router + React `/console` page. Done + merged 2026-06-09.
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
- [x] **Slice 2 (next): DONE —** extract `ConversationService` from `PlayAIdes.chat`; implement
      `run_turn` turn-event stream (`reply_started→delta*→done`); introduce `DisplayChannel`
      push port to break the circular `incarnation_server ⇄ PlayAIdes` dependency; wire WS
      live channel + REST `POST /api/v1/personas/{id}/messages` to the same service; add LLM
      streaming (`chat_stream`). See the architecture spec for the full slice definition.
- [ ] **Wire `/api/launch` in `incarnation_server.py` to the config store.** The inline route
      still hardcodes `{"bedroom","box8","living"}` — now out of sync with the store-driven
      `silver-launch.py`. Should call `load_launch_targets()` from `backend/stores/`.
- [ ] **PiP url-source rendering in the kiosk overlay** — `incarnation/src/pipOverlay.js`
      only handles `kind:"camera"` sources; the new `kind:"url"` source type (operator-entered
      site/doc) needs an `<iframe>` render path. Deferred pending Slice 2.
- [ ] **Say-target rewire** — deferred (TTS-adjacent; pending the voicebox concurrent session
      landing its `docs/VOICEBOX_HTTP_API.md` consumer migration).
- [ ] **Fix the test image** to install/stub the private `voicebox` SSH dep so the full
      `bin/test` suite collects without errors. Until then run targeted paths (see *Known issues*).
- [ ] **Integrations console — v2/v3 roadmap** (v1 done). **v2:** a Web-API provider (calendar,
      weather; REST via the existing http-skill seam). **v3:** an Agent provider (Hermes-style
      agents that *act* — e.g. write a web service). Both plug into the v1 provider seam.
- [ ] **PARKED — Console → unified trigger-binding manager.** Brainstormed 2026-06-09, deferred
      behind the `PlayAIdes` god-object decomposition (needs a clean persona/trigger API first).
      Reframe: the console becomes CRUD over `persona.triggers` (`phrase|event → skill → params`),
      one **unified row** per binding + a `+` to add; rows editable/deletable. Folds the old
      capability→entity "mapping" into the row's *target*. Open Qs: "any persona" scope, LLM vs
      deterministic phrase-parse, HA-intents overlap. Full notes:
      `docs/superpowers/specs/2026-06-09-console-trigger-redesign-PARKED.md`. **Resume after** the
      persona/trigger backend slice (PersonaService + triggers store + `/api/v1` triggers API) lands.
- [x] Refresh the stale README (Incarnation pages / Viewer / Running + HA endpoint count).
      Done 2026-06-07 via a living-docs sweep (full rewrite adopted from `LivDoc-README.md`).

## Known issues

- **[minor, infra/test] Full `bin/test` Python suite is pre-existingly RED** — the
  `playaides-tests` Docker image lacks the private `voicebox` SSH dep, so any `import
  PlayAIdes` test errors at collection-time. Run targeted test paths instead (e.g.
  `pytest tests/test_backend_*.py tests/test_console*.py`); the `backend/` + console tests
  pass and the JS suite is green. Fix: update the test image to install or stub `voicebox`.
  Surfaced: 2026-06-09. Workaround: use targeted pytest paths.
- **[minor, ops/config] Stray root-owned `config/integrations.json` (mode 600) at repo
  root** — left by a containerized server seed. Host-side store loaders now degrade
  gracefully to defaults (hardening added in `af4551f`, catches `OSError`/`ValueError`) but
  the file prevents the host from ever reading the real store. Fix: `sudo rm -rf config/` at
  the repo root (or run a root container to delete it). Surfaced: 2026-06-09. Workaround:
  loader degradation is live; host tools continue functioning with hardcoded defaults.
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

- [2026-06-09] **Slice 2 (ConversationService + DisplayChannel) shipped.** Extracted the
  conversation turn from PlayAIdes.chat into `backend/services/conversation.py` (yields a
  reply_started→delta*→done turn-event stream); introduced the `DisplayChannel` push port
  (`backend/ports/display.py` + `WebSocketDisplayChannel`) — the domain no longer references
  the concrete server for push, breaking the incarnation_server⇄PlayAIdes circular dependency.
  Added `LLMInterface.chat_stream`; WS forwards turn events, REST `POST /api/v1/personas/{id}/messages`
  drains them. Viewer unchanged (subtitle still via `assistant_message`). TTS-consumer migration
  to `/v1/audio/speech` + the RED full-suite fix remain their own next slice.
- [2026-06-09] **Backend/frontend re-architecture** — layered backend
  (`api → services → clients/stores`, + `ports/` for the one inversion) behind a stable
  versioned contract (`/api/v1` REST + narrow WebSocket for the live avatar loop), strangler-fig
  migration alongside the existing code (POC behavior ported, not redesigned away).
  `DisplayChannel` push port breaks the circular `incarnation_server ⇄ PlayAIdes` dependency.
  Rejected: big-bang rewrite (risk to working POC + no live users to fund the disruption);
  feature-first vertical slices (bigger reorg than incremental migration warrants); full
  hexagonal ports-for-everything (over-engineered for a single-operator app).
- [2026-06-09] **PiP = generic display slot** (`{kind:"camera",...}` or `{kind:"url",...}`),
  not a camera-only field. Camera is one typed source; operators can also point the PiP at an
  arbitrary website or document URL. Reflected in `backend/` stores + the console UI.
  Rejected: keeping PiP as a camera-only field (constrains future operator use cases with no
  upside).
- [2026-06-09] **Store loaders degrade to defaults on unreadable/malformed config** —
  `load_launch_targets`, `config_store.load`, and `secrets_store._load` now catch `OSError`
  and `ValueError` in addition to `FileNotFoundError`, and fall back to hardcoded defaults
  with a warning. Rationale: a root-owned `config/integrations.json` (mode 600, left by a
  containerized server seed) was crashing `bin/silver-launch.py` at startup. Fix in `af4551f`.
  Rejected: letting the caller crash (bad UX; operators shouldn't need to know about
  container-vs-host ownership conflicts to run the launcher).
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
