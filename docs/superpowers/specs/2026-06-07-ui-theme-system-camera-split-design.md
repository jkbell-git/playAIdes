# UI Theme System + Camera Split — Design

- **Date:** 2026-06-07
- **Status:** Draft for review
- **Area:** `incarnation/` (Vite + vanilla-JS + Three.js/@pixiv/three-vrm viewer)
- **Related:** `docs/superpowers/specs/2026-06-04-persona-skill-trigger-framework-design.md`, `docs/superpowers/plans/2026-06-06-skill-framework-plan-2-events-declarative-skills-camera.md`
- **Visual references (brainstorm mockups):** `.superpowers/brainstorm/156959-1780856170/content/` — `split-screen.html` (the agreed direction), `apply-scenes.html` (camera split chosen as first target), `frames-v2.html`/`direction.html` (rejected directions, kept for contrast).

## 1. Context & goal

The viewer's look is hardcoded and the user wants to evolve it toward an **anime "split-screen" aesthetic** — the screen divided into panels by **organic, leaning ink-brush dividers** (reference: a multi-character anime split-screen the user shared). Two things block that today:

1. There is no theme system. `viewer.css` `@import`s `tokens.css` (`viewer.css:7`) but uses tokens inconsistently — the body background is hardcoded `#000` (`viewer.css:15`), many surfaces use literal `rgba(10,8,18,.x)` ink-with-alpha values (e.g. `viewer.css:126, 185, 293, 434, 481, 517`), and **fonts are inlined per-component** (`Cinzel`/`Chakra Petch`/`Inter` at `viewer.css:14, 129, 168, 188`) with no `--font-*` tokens. You cannot "swap colors and fonts" while components hardcode them.
2. There is no split-screen capability. Cameras show as a small floating PiP (`pipOverlay.js`, `.pip-overlay` at `viewer.css:427`).

**Goal of this work:** build a theme system where **color, font, and shape are swappable tokens**, then use it to ship the first piece of the new shape language — a **camera split** (Silver on one side, the live feed on the other, an ink-brush divider between).

> *Line references come from a code survey and should be re-confirmed during implementation; they may drift.*

## 2. Visual direction (settled)

- **Composition:** split-screen panels divided by an **organic ink divider** — a blend of "ink brush" (bold, flowing, variable thickness) and "soft tear" (fine, gentle wobble). Smooth and painterly; **not** mechanical sawtooth (the Persona-5 jagged look was explicitly rejected).
- **Refined, not cartoony.** No comic fonts, no bright cartoon palettes.
- **Color & fonts are parked as theme tokens.** v1 does **not** pick a new palette or typeface — it keeps the current refined set (tokenized so it can change later). The visible change in v1 is **structural/shape**: the split layout, ink dividers, and inked panel edges.
- The divider's "wobble amount" should be expressible as a theme choice (different SVG path per theme), not a one-off.

## 3. Scope

**In scope (v1):**

1. **3-layer token system** (§5.1) covering color, font, and shape; refactor `viewer.css` to consume semantic roles and pay down the font/color/shape debt.
2. **Shape primitives:** the ink-brush **divider** (themeable inline SVG) and the **split-panel** layout, as reusable pieces.
3. **Camera split feature** (§5.2): a `show_pip`/camera event can render as a split (Silver | feed) instead of a floating PiP.
4. **Theme switch:** `<body data-theme>` with two themes — `manga` (new shape language, **default**) and `classic` (today's existing chamfered frames + floating PiP, no split/divider — proves switching toggles *shape*, not just color). Plus a `?theme=` URL param and a no-op hook for persona-carried themes.

**Out of scope (explicit follow-ups):**

- Choosing a *new* palette or fonts (the system enables it; design is a separate pass).
- Restyling the persona-swap wipe (`wipeOverlay.js`) into an ink sweep — reuses this primitive later.
- Multi-persona "cast" split (needs multiple avatars rendered at once).
- Re-skinning the standalone `data/mic.html` and `data/control.html` (they live outside the Vite build and hardcode a *drifted* copy of the palette; tokenizing them is a separate, optional task).
- Full per-persona theme *content* (only the wiring hook ships in v1).
- Three.js `setScissor`/`setViewport` precise split (v1 uses the CSS approach; see §5.2 alternative).

## 4. Browser constraints (Fire TV Silk)

The primary target is the Fire TV Cube's Silk browser (an older Chromium). Implications:

- **Use:** CSS custom properties, `clip-path` (polygon + path), inline SVG, `ResizeObserver`, `prefers-reduced-motion` — all safe.
- **Avoid in v1:** `color-mix()` and `@property` (too new for older Silk). **Precompute alpha/tint variants as explicit tokens** instead of computing them at runtime.
- **Progressive only:** `backdrop-filter` (frosted glass) — never required for legibility; provide a solid-color fallback.

## 5. Architecture

### 5.1 Theme system — 3 layers of CSS custom properties

All in CSS; **no new dependencies, no build changes.**

**Layer 1 — Palette (raw ingredients).** Literal values, theme-independent. Extends today's `tokens.css:9-37`:
- Colors: existing `--ink`, `--gold`, `--red`, `--cream`, … plus the missing **alpha variants** as explicit tokens (e.g. `--ink-a70: rgba(10,8,18,.7)`, `--ink-a90`, `--gold-a25`) to retire the hardcoded `rgba()`s, and a `--shadow-1` token for the repeated `rgba(0,0,0,.5)` shadows.
- Fonts: `--font-cinzel: 'Cinzel', serif;` `--font-chakra: 'Chakra Petch', sans-serif;` `--font-inter: 'Inter', system-ui, sans-serif;`
- Shapes: `--clip-chamfer` (today's angled panel edges, from `viewer.css:59,135,193`), `--clip-ink` (the new ink-cut edge), raw radii, and the divider SVG path assets.

**Layer 2 — Semantic roles (the contract).** **Components reference only these.** Examples:
- Color: `--bg`, `--surface`, `--surface-scrim`, `--text`, `--text-dim`, `--accent`, `--accent-2`, `--ok`.
- Type: `--font-display`, `--font-accent`, `--font-body`.
- Shape: `--frame-clip` (a clip-path *value* applied to panel edges), `--frame-radius`, `--divider-display` (`block`/`none`), `--hairline`. (Roles hold concrete values, not keywords — plain CSS can't branch on a keyword on older Silk.)

**Layer 3 — Theme recipes.** Each theme re-points the roles:
```css
:root, [data-theme="manga"] { /* DEFAULT */
  --bg: var(--ink);  --surface: var(--ink-a90);  --text: var(--cream);
  --accent: var(--gold);  --accent-2: var(--red);
  --font-display: var(--font-cinzel); --font-body: var(--font-inter);
  --frame-clip: var(--clip-ink);   /* panels get the ink-cut edge */
  --divider-display: block;        /* split shows the ink divider */
}
[data-theme="classic"] {           /* today's look — same palette/fonts */
  --frame-clip: var(--clip-chamfer);  /* existing angled chamfers */
  --divider-display: none;            /* camera falls back to floating PiP */
}
```
Switching = `document.body.dataset.theme = 'manga' | 'classic'`. Default resolves from (in order) `?theme=` URL param → persona-carried theme (future) → `manga`. The divider's *path geometry* (brush vs. other) is set in JS from the theme name (see §5.2), since a CSS var can't swap an inline SVG `<path d>` on older Silk.

**Where it lives:**
- `tokens.css` → split/grow into the Layer-1 palette (+ optionally a `themes.css` for Layers 2–3, `@import`ed by `viewer.css`).
- `viewer.css` → refactored so every color/font/shape reads a Layer-2 role. This is the bulk of the effort.

### 5.2 Camera split — CSS-driven layout, mirroring the PiP pattern

The existing camera path is clean and testable: `show_pip`/`dismiss_pip` WS messages (`viewer.js:308-313`) → pure `pipViewFromMessage()` (`pipOverlay.js:10-20`) → `apply()` toggles `.visible` and sets `#pip-image.src` (`pipOverlay.js:35-45`). We extend this rather than replace it.

**New pure module `stageLayout.js`** (mirrors `pipOverlay.js`, unit-tested like it):
- `stageLayoutFromMessage(type, payload, config)` → `{ layout: 'full' | 'split-camera', feedUrl, feedKind }`.
- A camera event renders as `split-camera` when the active theme/config wants it (default in `manga`); a `layout: 'pip'` payload or the `classic` theme falls back to the existing floating PiP.
- An `apply(view)` sets `document.body.dataset.layout` and the feed `src`; clearing it `removeAttribute('src')` to stop the MJPEG stream (same lifecycle as `pipOverlay.js:42`).

**CSS does the visual split** (driven by `body[data-layout="split-camera"]`):
- `#viewer` (Silver's canvas, `viewer.css:22-31`, currently `position:fixed; inset:0`) → constrained to the left panel.
- The **feed panel** occupies the right; it reuses the `#pip-image` element (or a sibling) sized to fill its panel, `object-fit: cover`.
- The **ink divider** (`#split-divider`, an inline SVG whose `fill` is a color role; shown when `--divider-display: block`, and whose **path geometry is set by `splitDivider.js` from `data-theme`** — an inline SVG `<path d>` can't be swapped by a CSS var on older Silk) sits over the seam, leaning.
- Transition respects `prefers-reduced-motion`.

**The one real Three.js change — resize to the canvas box, not the window.** Today `onResize()` (`scene.js:92-97`) reads `window.innerWidth/innerHeight`. A CSS-driven width change **does not fire `window.resize`**, and would otherwise squish Silver. Fix:
- Drive sizing from the canvas's own box via a **`ResizeObserver` on `#viewer`**: `renderer.setSize(w, h, false)`, `camera.aspect = w/h`, `camera.updateProjectionMatrix()`.
- Re-check framing for the narrower (taller) aspect — the close bust framing (45° FOV, target neck-level, `scene.js:48-64`) may need a small dolly-back or FOV nudge when split so Silver isn't cropped. Final values tuned on-device.
- Keep `focusOnHead()` (`scene.js:225-256`) so Silver stays centered within her panel.

**Alternative (deferred):** keep one full-screen canvas, render Silver into the left rectangle via `renderer.setScissor()`/`setViewport()`. Pixel-perfect density, but more 3D code and a second resize path. Adopt only if the CSS approach looks soft/letterboxed on the actual TV.

## 6. Files

**New:**
- `incarnation/src/stageLayout.js` — pure decide + apply for full vs split-camera.
- `incarnation/src/stageLayout.test.js` — vitest, mirroring `pipOverlay`/`viewerState` test style.
- `incarnation/styles/themes.css` — Layer-2 roles + Layer-3 theme recipes (or fold into `tokens.css`).
- `incarnation/src/splitDivider.js` *(or inline SVG in `index.html`)* — the themeable ink divider element.

**Changed:**
- `incarnation/styles/tokens.css` — add alpha/shadow/font/shape Layer-1 tokens.
- `incarnation/styles/viewer.css` — refactor to consume Layer-2 roles; add `body[data-layout="split-camera"]` rules + divider styling; retire hardcoded colors/fonts.
- `incarnation/src/scene.js` — `ResizeObserver` on `#viewer`; split-aware framing.
- `incarnation/src/viewer.js` — route camera events through `stageLayout`; set initial `data-theme` from config; (hook) read `theme` from `persona_active` (`viewer.js:315-328`).
- `incarnation/src/viewerConfig.js` — parse `?theme=` (`loadConfig`, `viewerConfig.js:62-98`).
- `incarnation/index.html` — add `#split-divider` SVG and the feed-panel container if not reusing `#pip-overlay`.

## 7. Data flow

```
camera/show_pip WS  ─▶ viewer.js  ─▶ stageLayoutFromMessage(type, payload, config)
                                          │
                                          ├─ layout 'split-camera' ─▶ body[data-layout]=split-camera
                                          │     #viewer→left, feed→right, #split-divider shown
                                          │     ResizeObserver re-sizes renderer to canvas box
                                          └─ layout 'pip' (classic/fallback) ─▶ existing floating PiP

boot/config ─▶ loadConfig() ─▶ data-theme from ?theme= → (future) persona theme → 'manga'
persona_active WS ─▶ (hook) theme field → body.dataset.theme   [wiring only in v1]
```

## 8. Error handling & edge cases

- **Feed fails to load / empty URL:** `stageLayoutFromMessage` returns `full` when `url` is missing (same guard as `pipOverlay.js:11`); on `<img>` error, fall back to `full` and surface nothing jarring. Always `removeAttribute('src')` on dismiss to stop MJPEG.
- **Dismiss while split:** return to `full`; renderer re-sizes back via the observer.
- **Kiosk/cinematic interaction:** `?cinematic=1` force-hides overlays (`viewerConfig.js`, `viewerOverlays.js:40-43`); the split is a *layout*, not an overlay, so it stays — but confirm the divider/feed don't fight the cinematic kill-switch.
- **Unknown/missing theme:** fall back to `manga`. Unknown `--divider` value → no divider (safe).
- **Reduced motion:** skip the split-in transition; snap instead.
- **Resize storms:** debounce/guard the observer; `renderer.setSize(w,h,false)` avoids touching CSS.
- **Older Silk:** no `color-mix`/`@property` (alpha is precomputed tokens); `backdrop-filter` degrades to solid surface.

## 9. Testing

- **Unit (vitest):** `stageLayout.test.js` — full vs split decision across event types, missing URL, theme/config influence, dismiss. Mirror the existing pure-function tests (`pipOverlay`, `viewerState`).
- **Token/theme sanity:** a small test/asserting both `[data-theme]` blocks define every Layer-2 role (no undefined role leaks).
- **Manual on-device (Fire TV):** trigger a camera via `data/control.html` → confirm the split renders, Silver isn't squished/cropped, the divider leans correctly, dismiss returns to full, and `?theme=classic` shows straight frames + floating PiP.

## 10. Build order (within v1)

1. Token Layer-1 additions (alpha/shadow/font/shape) — no visual change.
2. Introduce Layer-2 roles + the two Layer-3 theme blocks; refactor `viewer.css` to roles (still no visual change under `manga` defaults).
3. `stageLayout.js` + tests (pure logic, no UI yet).
4. CSS split layout + `#split-divider` + feed panel.
5. `scene.js` ResizeObserver + split framing; wire `viewer.js` to `stageLayout`.
6. `?theme=` param + persona-theme hook.
7. On-device tuning of camera framing and divider lean/thickness.

## 11. Open questions

- Reuse `#pip-image` for the split feed, or a dedicated feed element? (Leaning reuse, to keep one MJPEG lifecycle.)
- Should `manga` ever fall back to the floating PiP for *snapshot* (still-image) cameras, reserving the split for *live* feeds? (Default: split for both; revisit if stills look odd in a tall panel.)
