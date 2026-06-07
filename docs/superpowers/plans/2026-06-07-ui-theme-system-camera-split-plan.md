# UI Theme System + Camera Split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the `incarnation/` viewer a 3-layer CSS theme system (color + font swappable via tokens) and ship the first new shape feature — a camera "split" where Silver renders on one side and a live feed on the other, divided by an organic ink-brush divider.

**Architecture:** Pure CSS custom properties in three layers (palette → semantic roles → `[data-theme]` recipes); no new dependencies. The camera split mirrors the repo's existing `pipOverlay.js` pattern — a unit-tested pure decision function plus a thin DOM-glue class — driven by the existing `show_pip`/`dismiss_pip` WebSocket messages. The one imperative change is in `scene.js`: drive the Three.js renderer size from the canvas's own box (via `ResizeObserver`) instead of the window, so a CSS-driven split doesn't distort the avatar.

**Tech Stack:** Vite 7, Vitest 4, vanilla ES modules, Three.js + `@pixiv/three-vrm`, CSS custom properties. Target browser includes Fire TV Silk (older Chromium) — so: precomputed alpha tokens (no `color-mix()`), `ResizeObserver` + `clip-path` + inline SVG only.

**Spec:** `docs/superpowers/specs/2026-06-07-ui-theme-system-camera-split-design.md`
**Architecture note:** `docs/frontend-architecture.md`

---

## File structure

All paths under `/home/bell/repo/ai_life/playAIdes/incarnation/`.

**Create:**
- `src/stageLayout.js` — pure `stageLayoutFromMessage()` (full vs split-camera decision) + `StageLayout` DOM-glue class.
- `src/stageLayout.test.js` — vitest unit tests for the pure function (mirrors `viewerConfig.test.js` style; no DOM).

**Modify:**
- `styles/tokens.css` — add Layer-1 palette tokens (alpha/shadow/font) + Layer-2 roles + Layer-3 theme blocks.
- `styles/viewer.css` — consume `--font-*` and ink-alpha tokens; add the split-layout + divider rules.
- `src/viewerConfig.js` — parse `?theme=` and `?split=`.
- `src/viewerConfig.test.js` — cover the new fields (and fix the exhaustive defaults assertion).
- `src/viewer.js` — set `data-theme` at boot, hook persona-carried theme, route camera events through `stageLayout`.
- `src/scene.js` — size the renderer to the canvas box via `ResizeObserver`.
- `index.html` — add the split DOM (`#stage-split`, `#split-feed-image`, `#split-divider`).

**Conventions to follow (from the existing code):**
- Only **pure functions** get unit tests; DOM-glue classes are untested (no jsdom harness) — see the header of `src/pipOverlay.js`.
- Run tests from the `incarnation/` directory: `npx vitest run <file>`.
- Commit after each task.

---

## PHASE A — Theme token foundation

### Task 1: Add Layer-1 palette tokens (alpha, shadow, fonts)

**Files:**
- Modify: `styles/tokens.css` (inside the existing `:root` block, after line 37 `--ease-slash`)

- [ ] **Step 1: Add the new raw tokens**

In `styles/tokens.css`, immediately before the closing `}` of the `:root` block (after the `--ease-slash:` line), add:

```css
    /* ── Precomputed alpha variants (no color-mix(): old Silk) ───────── */
    --ink-a50:    rgba(10, 8, 18, .50);
    --ink-a70:    rgba(10, 8, 18, .70);
    --ink-a78:    rgba(10, 8, 18, .78);
    --ink-a80:    rgba(10, 8, 18, .80);
    --ink-a82:    rgba(10, 8, 18, .82);
    --ink-a90:    rgba(10, 8, 18, .90);
    --ink-a92:    rgba(10, 8, 18, .92);
    --ink-a95:    rgba(10, 8, 18, .95);
    --ink-a98:    rgba(10, 8, 18, .98);
    --shadow-1:   rgba(0, 0, 0, .5);

    /* ── Font stacks ─────────────────────────────────────────────────── */
    --font-cinzel: 'Cinzel', serif;
    --font-chakra: 'Chakra Petch', sans-serif;
    --font-inter:  'Inter', system-ui, sans-serif;
```

- [ ] **Step 2: Verify the dev build still parses**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: build completes with no CSS errors (exit 0).

- [ ] **Step 3: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/styles/tokens.css
git commit -m "feat(theme): add layer-1 alpha/shadow/font palette tokens"
```

---

### Task 2: Add Layer-2 semantic roles + Layer-3 theme recipes

**Files:**
- Modify: `styles/tokens.css` (append after the `:root` block)

- [ ] **Step 1: Append the role + theme layers**

At the END of `styles/tokens.css` (after the existing scrollbar rules), add:

```css
/* =============================================================
   Theme layers. Components reference the SEMANTIC roles below,
   never the raw palette. A theme just re-points the roles.
   Default (no [data-theme]) == manga.
   ============================================================= */
:root, [data-theme="manga"] {
    --bg:            var(--ink);
    --text:          var(--cream);
    --accent:        var(--gold);
    --accent-2:      var(--red);
    --font-display:  var(--font-cinzel);
    --font-accent:   var(--font-chakra);
    --font-body:     var(--font-inter);
    --divider-display: block;          /* camera split shows the ink divider */
    --divider-fill:    var(--ink);
}

[data-theme="classic"] {
    /* Same palette/fonts as today; differs only in shape: no split divider,
       so a camera shows as the floating PiP instead. */
    --divider-display: none;
}
```

- [ ] **Step 2: Verify the build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0, no errors.

- [ ] **Step 3: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/styles/tokens.css
git commit -m "feat(theme): add layer-2 semantic roles + manga/classic theme blocks"
```

---

### Task 3: Refactor viewer.css fonts to `--font-*` tokens

This retires every inlined font string so a theme can swap typefaces.

**Files:**
- Modify: `styles/viewer.css`

- [ ] **Step 1: Replace the font declarations**

Apply these exact replacements in `styles/viewer.css` (each `font-family` line → the token). They are safe to do with find/replace:

| Find | Replace with |
|------|--------------|
| `font-family: 'Inter', system-ui, sans-serif;` (lines 14, 329, 371) | `font-family: var(--font-body);` |
| `font-family: 'Cinzel', serif;` (lines 129, 270, 390, 488) | `font-family: var(--font-display);` |
| `font-family: 'Chakra Petch', sans-serif;` (lines 168, 188, 302, 344, 498, 520) | `font-family: var(--font-accent);` |

(Use `replace_all` per distinct string — there are no other uses of these exact strings.)

- [ ] **Step 2: Verify nothing renders unstyled**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0. (Fonts still resolve — the tokens point at the same families.)

- [ ] **Step 3: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/styles/viewer.css
git commit -m "refactor(theme): viewer.css fonts → --font-* tokens"
```

---

### Task 4: Refactor viewer.css colors (body bg, ink alphas, shadow) to tokens

**Files:**
- Modify: `styles/viewer.css`

- [ ] **Step 1: Replace the body background**

Line 15: change `background: #000;` → `background: var(--bg);`

- [ ] **Step 2: Replace the ink-alpha and shadow literals**

Apply these exact replacements:

| Location | Find | Replace with |
|----------|------|--------------|
| `.subtitle-band` (line 126) | `linear-gradient(180deg, rgba(10, 8, 18, .82), rgba(10, 8, 18, .95))` | `linear-gradient(180deg, var(--ink-a82), var(--ink-a95))` |
| `.nameplate` (line 185) | `background: rgba(10, 8, 18, .7);` | `background: var(--ink-a70);` |
| `.chat-panel-body` (line 293) | `linear-gradient(180deg, rgba(10, 8, 18, .92), rgba(10, 8, 18, .98))` | `linear-gradient(180deg, var(--ink-a92), var(--ink-a98))` |
| `.pip-overlay` (line 434) | `background: rgba(10, 8, 18, .9);` | `background: var(--ink-a90);` |
| `.pip-overlay` (line 435) | `box-shadow: 0 8px 32px rgba(0, 0, 0, .5);` | `box-shadow: 0 8px 32px var(--shadow-1);` |
| `.console-log` (line 481) | `linear-gradient(180deg, rgba(10, 8, 18, 0), rgba(10, 8, 18, .5) 40%, rgba(10, 8, 18, .8))` | `linear-gradient(180deg, transparent, var(--ink-a50) 40%, var(--ink-a80))` |
| `.console-input` (line 517) | `background: rgba(10, 8, 18, .78);` | `background: var(--ink-a78);` |
| `.console-send` (line 532) | `color: rgba(10, 8, 18, 1);` | `color: var(--ink);` |

- [ ] **Step 3: Verify build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/styles/viewer.css
git commit -m "refactor(theme): viewer.css colors → ink-alpha/shadow tokens"
```

---

### Task 5: Parse `?theme=` and `?split=` in viewerConfig (TDD)

**Files:**
- Modify: `src/viewerConfig.js`
- Test: `src/viewerConfig.test.js`

- [ ] **Step 1: Update the exhaustive defaults test to expect the new fields (this will fail first)**

In `src/viewerConfig.test.js`, in the `'returns documented defaults when search string is empty'` test, add two lines inside the `toEqual({...})` object (after `pixelRatio: null,` and before `wsUrl:`):

```js
            theme: 'manga',
            split: true,
```

- [ ] **Step 2: Add new test cases**

Append to `src/viewerConfig.test.js`:

```js
describe('loadConfig — theme', () => {
    it('defaults to "manga"', () => {
        expect(loadConfig('').theme).toBe('manga');
    });
    it('?theme=classic parses to "classic"', () => {
        expect(loadConfig('?theme=classic').theme).toBe('classic');
    });
    it('?theme=manga parses to "manga"', () => {
        expect(loadConfig('?theme=manga').theme).toBe('manga');
    });
    it('unknown theme falls back to "manga"', () => {
        expect(loadConfig('?theme=neon').theme).toBe('manga');
    });
});

describe('loadConfig — split', () => {
    it('defaults to true', () => {
        expect(loadConfig('').split).toBe(true);
    });
    it('?split=0 parses to false', () => {
        expect(loadConfig('?split=0').split).toBe(false);
    });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run src/viewerConfig.test.js`
Expected: FAIL — defaults `toEqual` mismatch + `theme`/`split` undefined.

- [ ] **Step 4: Implement the parsing**

In `src/viewerConfig.js`:

(a) In the `DEFAULTS` object (after `pixelRatio: null,`, line 33), add:
```js
    theme: 'manga',
    split: true,
```

(b) In the `config` object inside `loadConfig` (after the `pixelRatio:` line, line 85), add:
```js
        theme:       (p.get('theme') === 'classic') ? 'classic' : DEFAULTS.theme,
        split:       parseBool(p.get('split'), DEFAULTS.split),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run src/viewerConfig.test.js`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/viewerConfig.js incarnation/src/viewerConfig.test.js
git commit -m "feat(theme): parse ?theme= and ?split= URL params"
```

---

### Task 6: Apply `data-theme` at boot + persona-carried theme hook

**Files:**
- Modify: `src/viewer.js`

- [ ] **Step 1: Set the theme attribute at boot**

In `src/viewer.js`, after the kiosk block that ends at line 44 (`}` of `if (config.kiosk) { ... }`), add:

```js
// Theme: drive the CSS [data-theme] layer. Defaults to 'manga'; ?theme=classic
// switches to today's chrome (and the floating PiP instead of the camera split).
document.body.dataset.theme = config.theme;
```

- [ ] **Step 2: Hook a persona-carried theme (forward-compat; no-op until the server sends one)**

In the `persona_active` handler, after `activePersona = {...}` is assigned (after line 320), add:

```js
    // A persona may carry its own look; apply it if present (server payload
    // extension — absent today, so this is a no-op until wired server-side).
    if (e.detail?.theme) document.body.dataset.theme = e.detail.theme;
```

- [ ] **Step 3: Verify build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/viewer.js
git commit -m "feat(theme): apply data-theme at boot + persona-theme hook"
```

---

## PHASE B — Camera split feature

### Task 7: Create the `stageLayout` module (TDD)

**Files:**
- Create: `src/stageLayout.js`
- Test: `src/stageLayout.test.js`

- [ ] **Step 1: Write the failing test**

Create `src/stageLayout.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { stageLayoutFromMessage } from './stageLayout.js';

describe('stageLayoutFromMessage', () => {
    it('show_pip with a url and split enabled → split-camera', () => {
        const v = stageLayoutFromMessage('show_pip', { url: 'http://x/cam', kind: 'live' }, { splitEnabled: true });
        expect(v).toEqual({ layout: 'split-camera', feedUrl: 'http://x/cam', feedKind: 'live' });
    });

    it('defaults kind to snapshot', () => {
        const v = stageLayoutFromMessage('show_pip', { url: 'http://x/cam' }, { splitEnabled: true });
        expect(v.feedKind).toBe('snapshot');
    });

    it('split disabled → full (let the floating PiP handle it)', () => {
        const v = stageLayoutFromMessage('show_pip', { url: 'http://x/cam' }, { splitEnabled: false });
        expect(v).toEqual({ layout: 'full', feedUrl: '', feedKind: null });
    });

    it('show_pip with no url → full', () => {
        const v = stageLayoutFromMessage('show_pip', {}, { splitEnabled: true });
        expect(v.layout).toBe('full');
    });

    it('dismiss_pip → full', () => {
        const v = stageLayoutFromMessage('dismiss_pip', {}, { splitEnabled: true });
        expect(v).toEqual({ layout: 'full', feedUrl: '', feedKind: null });
    });

    it('unknown type → full', () => {
        expect(stageLayoutFromMessage('whatever', { url: 'x' }, { splitEnabled: true }).layout).toBe('full');
    });

    it('splitEnabled defaults to true when opts omitted', () => {
        expect(stageLayoutFromMessage('show_pip', { url: 'x' }).layout).toBe('split-camera');
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run src/stageLayout.test.js`
Expected: FAIL with "Failed to resolve import './stageLayout.js'" (module not created yet).

- [ ] **Step 3: Write the implementation**

Create `src/stageLayout.js`:

```js
/**
 * stageLayout.js — chooses between the normal full-screen avatar and the
 * camera "split" (Silver left, live feed right, ink divider between).
 *
 * `stageLayoutFromMessage` is the pure decision function (unit-tested);
 * `StageLayout` is the thin DOM glue (untested, per repo convention — no
 * jsdom harness). Driven by the existing `show_pip` / `dismiss_pip` WS
 * messages, the same source the floating PiP listens to.
 */

/**
 * Pure: decide the stage layout from an inbound WS message.
 * @param {string} type                  'show_pip' | 'dismiss_pip' | other
 * @param {{url?:string,kind?:string}} payload
 * @param {{splitEnabled?:boolean}} opts  splitEnabled defaults to true
 * @returns {{layout:'full'|'split-camera',feedUrl:string,feedKind:string|null}}
 */
export function stageLayoutFromMessage(type, payload = {}, opts = {}) {
    const splitEnabled = opts.splitEnabled !== false; // default true
    if (type === 'show_pip' && payload.url && splitEnabled) {
        return {
            layout: 'split-camera',
            feedUrl: payload.url,
            feedKind: payload.kind === 'live' ? 'live' : 'snapshot',
        };
    }
    // dismiss_pip, no url, split disabled, or anything else → full screen.
    return { layout: 'full', feedUrl: '', feedKind: null };
}

export class StageLayout {
    /** @param {Document} root */
    constructor(root) {
        this.body = root.body || document.body;
        this.img = root.querySelector('#split-feed-image');
        if (!this.img) {
            console.warn('[StageLayout] #split-feed-image not found — split disabled');
        }
        // If the feed fails to load (dead camera URL / dropped MJPEG), collapse
        // back to the full-screen avatar rather than leaving a broken panel up.
        if (this.img) {
            this.img.addEventListener('error', () => { this.body.dataset.layout = 'full'; });
        }
    }

    /** @param {{layout:string,feedUrl:string,feedKind:string|null}} view */
    apply(view) {
        if (view.layout === 'split-camera' && view.feedUrl) {
            if (this.img) this.img.src = view.feedUrl;
            this.body.dataset.layout = 'split-camera';
        } else {
            this.body.dataset.layout = 'full';
            // Drop the src so an MJPEG stream stops fetching when hidden.
            if (this.img) this.img.removeAttribute('src');
        }
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run src/stageLayout.test.js`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/stageLayout.js incarnation/src/stageLayout.test.js
git commit -m "feat(split): stageLayout pure decision fn + DOM glue (TDD)"
```

---

### Task 8: Add the split DOM to index.html

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Insert the split layer**

In `index.html`, immediately AFTER the `#wipe-overlay` div (line 17) and before the `#mic-indicator` (line 21), add:

```html
    <!-- Camera split layout (manga theme): Silver's canvas shrinks to the left,
         the live feed fills the right, an organic ink divider sits on the seam.
         Toggled by body[data-layout="split-camera"] (see stageLayout.js). -->
    <div id="stage-split" class="stage-split" aria-hidden="true">
      <div id="split-feed" class="split-feed">
        <img id="split-feed-image" class="split-feed-image" alt="" />
      </div>
      <svg id="split-divider" class="split-divider" viewBox="0 0 60 300"
           preserveAspectRatio="none" aria-hidden="true">
        <path d="M26,0 C18,38 36,72 24,108 C14,144 32,186 22,224 C16,258 30,286 24,300
                 L40,300 C46,262 30,222 42,184 C52,146 34,106 44,70 C50,40 34,14 36,0 Z" />
      </svg>
    </div>
```

- [ ] **Step 2: Verify build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/index.html
git commit -m "feat(split): add camera-split DOM (feed panel + ink divider)"
```

---

### Task 9: Add the split-layout CSS

**Files:**
- Modify: `styles/viewer.css`

- [ ] **Step 1: Append the split rules**

At the END of `styles/viewer.css`, add:

```css
/* ── Camera split layout (body[data-layout="split-camera"]) ──────────────
   Silver's canvas shrinks to the left; the feed fills the right; an organic
   ink divider (theme-controlled via --divider-display) leans on the seam.
   The renderer is resized to the canvas box by scene.js (ResizeObserver). */
.stage-split {
    position: fixed;
    inset: 0;
    z-index: 2;                 /* above #viewer (z1), below mic/subtitle (z70+) */
    pointer-events: none;
    opacity: 0;
    transition: opacity .35s var(--ease-snap);
}
body[data-layout="split-camera"] .stage-split { opacity: 1; }

/* Avatar canvas → left panel. right:auto so width wins over inset:0. */
body[data-layout="split-camera"] #viewer { width: 52%; right: auto; }

.split-feed {
    position: fixed;
    top: 0; bottom: 0;
    left: 52%; right: 0;
    overflow: hidden;
    background: var(--bg);
}
.split-feed-image { width: 100%; height: 100%; object-fit: cover; display: block; }

.split-divider {
    position: fixed;
    top: -4%; height: 108%;
    left: calc(52% - 28px);
    width: 60px;
    z-index: 3;
    display: var(--divider-display, none);   /* 'none' in classic theme */
    transform: rotate(4deg);
    pointer-events: none;
}
.split-divider path { fill: var(--divider-fill, #000); }

@media (prefers-reduced-motion: reduce) {
    .stage-split { transition: none; }
}
```

- [ ] **Step 2: Verify build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/styles/viewer.css
git commit -m "feat(split): camera-split layout + ink divider CSS"
```

---

### Task 10: Wire `stageLayout` into viewer.js camera events

**Files:**
- Modify: `src/viewer.js`

- [ ] **Step 1: Import the module**

Change line 26 from:
```js
import { PipOverlay, pipViewFromMessage } from './pipOverlay.js';
```
to:
```js
import { PipOverlay, pipViewFromMessage } from './pipOverlay.js';
import { StageLayout, stageLayoutFromMessage } from './stageLayout.js';
```

- [ ] **Step 2: Construct the StageLayout and resolve splitEnabled**

After line 58 (`const pip = new PipOverlay(document);`), add:
```js
const stage = new StageLayout(document);
// Split the screen for a camera only in the manga theme (classic uses the
// floating PiP); ?split=0 forces the floating PiP everywhere.
const splitEnabled = config.split && config.theme === 'manga';
```

- [ ] **Step 3: Replace the show_pip / dismiss_pip handlers**

Replace lines 308–313 (the two existing handlers) with:
```js
connection.addEventListener('show_pip', (e) => {
    const payload = withResolvedUrl(e.detail || {});
    const view = stageLayoutFromMessage('show_pip', payload, { splitEnabled });
    stage.apply(view);
    // Keep the floating PiP and the split mutually exclusive — only one shows.
    pip.apply(view.layout === 'split-camera'
        ? pipViewFromMessage('dismiss_pip', {})
        : pipViewFromMessage('show_pip', payload));
});
connection.addEventListener('dismiss_pip', () => {
    stage.apply(stageLayoutFromMessage('dismiss_pip', {}, { splitEnabled }));
    pip.apply(pipViewFromMessage('dismiss_pip', {}));
});
```

- [ ] **Step 4: Verify the full suite + build still pass**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run && npx vite build`
Expected: all tests PASS, build exit 0.

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/viewer.js
git commit -m "feat(split): route camera events through stageLayout"
```

---

### Task 11: Size the renderer to the canvas box (scene.js)

A CSS width change does NOT fire `window.resize`, so the renderer must observe the canvas. Also pass `updateStyle=false` so the renderer never writes an inline `style="width:…px"` that would override the CSS-driven split width.

**Files:**
- Modify: `src/scene.js`

- [ ] **Step 1: Stop the initial setSize from writing inline canvas styles**

Change line 31 from:
```js
renderer.setSize(window.innerWidth, window.innerHeight);
```
to:
```js
renderer.setSize(window.innerWidth, window.innerHeight, false); // false: let CSS own the canvas box (needed for the split)
```

- [ ] **Step 2: Replace the resize handler with a canvas-box ResizeObserver**

Replace lines 91–97 (the `// ── Resize handler ──` comment, `onResize`, and the `window.addEventListener('resize', onResize)` line) with:
```js
// ── Resize handler ──────────────────────────────────────────────────────────
// Drive size from the CANVAS box, not the window: the camera split changes the
// canvas width via CSS (which never fires window 'resize'), and we must keep the
// drawing buffer + camera aspect matched to the element to avoid distorting Silver.
function resizeRendererToCanvas() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    if (w === 0 || h === 0) return;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false); // false: don't override the CSS-controlled size
}
resizeRendererToCanvas();
const _canvasResizeObserver = new ResizeObserver(() => resizeRendererToCanvas());
_canvasResizeObserver.observe(canvas);
```

- [ ] **Step 3: Verify build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/scene.js
git commit -m "feat(split): size renderer to canvas box via ResizeObserver"
```

---

## PHASE C — Verify end-to-end

### Task 12: Full verification (automated + manual)

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run`
Expected: all tests PASS, including `viewerConfig.test.js` and `stageLayout.test.js`.

- [ ] **Step 2: Production build**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite build`
Expected: exit 0, `dist/` updated.

- [ ] **Step 3: Manual check in a desktop browser (dev server)**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vite` then open the printed URL.
Check:
- Viewer loads with the avatar; chrome (nameplate/console) looks unchanged (token refactor is visually neutral). `document.body.dataset.theme === 'manga'`.
- Trigger a camera via the dev control page (`http://<host>:8765/data/control.html` → "Show camera on TV", with a viewer bound) **or** in the console: dispatch a `show_pip` (e.g. set `#split-feed-image` by simulating the WS event). Expected: the canvas shrinks to the left, the feed fills the right, the ink divider leans on the seam, **and Silver is not horizontally squished** (aspect correct).
- Dismiss → returns to full-screen avatar; the feed `src` is cleared.
- Append `?theme=classic` to the URL → camera shows as the **floating PiP** (top-left), no divider.
- Append `?split=0` → camera shows as the floating PiP even in manga.

- [ ] **Step 4: On-device tuning note (Fire TV)**

Load `http://192.168.0.7:8765/?kiosk=1` on the Fire TV and trigger a camera. Confirm the split renders and the divider lean/thickness reads well at TV distance. If Silver sits too tight in her half, tune framing in `scene.js` (`camera.position` / `controls.target` in `focusOnHead`, lines 234–235) — out of scope to finalize here; just record the values that look right.

- [ ] **Step 5: Final commit (if any tuning values changed)**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/scene.js
git commit -m "chore(split): on-device framing tweaks"
```
(Use specific paths — never `git add -A`: this repo has intentionally-untracked prior-session files.)

---

## Out of scope (deferred — see spec §3)

- New palette / fonts (the tokens enable it; choosing them is a separate pass).
- Restyling the persona-swap wipe into an ink sweep (reuses the divider asset later).
- Multi-persona "cast" split.
- Re-skinning `data/mic.html` / `data/control.html` (outside the Vite build).
- Per-persona theme *content* (only the boot/persona hook ships here).
- Three.js `setScissor`/`setViewport` precise split (CSS approach is v1).
