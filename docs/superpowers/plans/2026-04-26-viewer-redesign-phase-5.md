# Viewer Redesign — Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish + desktop story. Two subsystems: (Part A) tiered background loader that auto-detects flat-image vs HDRI vs 3D scene by file extension and applies optional `spawn_point` / `camera_target` from persona config, and (Part B) a collapsible right-edge chat panel with a real transcript view + typed input — rehydrated from `history_loaded`, wired to `user_input` WS so typed messages skip the STT round-trip.

**Architecture:** Part A keeps a single dispatcher in `scene.js` that delegates to one of three loaders by extension; pure-string extension classification lives in a separate `sceneBackgrounds.js` module so it's unit-testable without three.js. HDRI uses `RGBELoader` + `PMREMGenerator` to derive both `scene.background` and `scene.environment`; 3D scenes use the existing `GLTFLoader` and add the loaded scene next to the VRM, sharing the existing lighting rig. Part B splits the chat panel into a pure `transcriptModel.js` (Discord/Slack auto-scroll-vs-freeze semantics, fully Vitest-tested) and a DOM-coupled `ChatPanel` class that owns the right-edge handle, slide-in panel, transcript rendering, and text input. The orchestrator wires `history_loaded` → rehydrate, `user_input` / `assistant_message` → append, and disables the input during SPEAKING.

**Tech Stack:** Vanilla JS (ES modules + Vitest), Three.js + `three/addons/loaders/RGBELoader.js` and `three/addons/loaders/GLTFLoader.js` (already used by VRM), Pydantic v2, FastAPI WebSocket, pytest.

**Branch:** create a fresh `phase_5_polish` from `main` (no worktrees per project preference).

**Reference spec:** `docs/superpowers/specs/2026-04-24-viewer-redesign-design.md` — read §4 (UI layout, especially the chat panel position vs subtitle band), §4b (Backgrounds — three tiers, dispatcher pseudocode, optional Avatar fields, lifecycle, failure fallback, out of scope), §5 (Chat panel + typed input — visibility model, layout, transcript items, text input, persistence, subtitle interaction, out of scope), §7 (URL params, especially `?chat=`).

## Conventions for this plan

- **Backend (Python)** uses TDD via `make test`. Whisper-touching tests use `respx`; no live STT in Phase 5.
- **Frontend pure modules** (extension detection, transcript model) use Vitest in Docker (`make test-js`). DOM-coupled wiring uses manual browser verification.
- Each task ends with a commit. Conventional Commits prefixes.
- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.

## Phase 5 simplifications (deferred)

- **No in-page settings UI.** URL params remain the only configuration surface in v1; an in-panel tray is out of scope.
- **No conversation export, no message editing/deletion, no re-rolling a reply.** Plain transcript only.
- **No markdown rendering.** Plain text with `\n` → line break only. No code blocks, no bold, no links.
- **No persona switcher inside the panel.** Wake-word swap (Phase 4) remains the only switching mechanism.
- **No animated backgrounds** (video / sprite sheets / particle systems independent of the persona).
- **No "set the scene" via voice** ("Silver, take us to a beach") — that's a future natural-language tool.
- **No editor UI for picking backgrounds** — the Persona Forge owns that, separate spec.

---

## Part A — Backgrounds

### Task 1: Avatar `spawn_point` + `camera_target` schema (TDD)

**Files:**
- Modify: `persona.py` (`Avatar` BaseModel)
- Test: `tests/unit/test_persona.py` (extend with new test class)

- [ ] **Step 1: Write the failing tests**

Append a new class to `tests/unit/test_persona.py`:

```python
class TestAvatarSpawnAndCamera:
    def test_spawn_point_optional(self):
        """Avatar without spawn_point parses fine (backwards compat)."""
        a = Avatar(model_url="m.vrm")
        assert a.spawn_point is None

    def test_camera_target_optional(self):
        """Avatar without camera_target parses fine."""
        a = Avatar(model_url="m.vrm")
        assert a.camera_target is None

    def test_spawn_point_three_floats(self):
        a = Avatar(model_url="m.vrm", spawn_point=[0.0, 0.0, 0.0])
        assert a.spawn_point == [0.0, 0.0, 0.0]

    def test_camera_target_three_floats(self):
        a = Avatar(model_url="m.vrm", camera_target=[0.0, 1.1, 0.0])
        assert a.camera_target == [0.0, 1.1, 0.0]

    def test_spawn_point_accepts_ints(self):
        """Persona JSON often has integer literals; ensure they coerce to float-friendly."""
        a = Avatar(model_url="m.vrm", spawn_point=[0, 1, 2])
        # Pydantic v2 will coerce int → float when the field type allows it.
        assert list(a.spawn_point) == [0, 1, 2]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|TestAvatarSpawnAndCamera)" | head
```

Expected: 5 failures (`spawn_point`/`camera_target` don't exist yet).

- [ ] **Step 3: Add the fields to `Avatar`**

In `persona.py`, locate the `Avatar` class. Add two fields directly after `background_url` (or wherever feels natural in the field block):

```python
class Avatar(BaseModel):
    # … existing fields …
    spawn_point: Optional[List[float]] = None
    camera_target: Optional[List[float]] = None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `136 passed, 4 deselected` (was 131; +5 new tests).

- [ ] **Step 5: Commit**

```bash
git add persona.py tests/unit/test_persona.py
git commit -m "feat(persona): add Avatar.spawn_point and Avatar.camera_target"
```

---

### Task 2: Pure `detectBackgroundType` module (Vitest)

**Files:**
- Create: `incarnation/src/sceneBackgrounds.js`
- Test: `incarnation/src/sceneBackgrounds.test.js`

Pure module — one function `detectBackgroundType(url)` returns one of `'flat'`, `'hdri'`, `'glb'`, `'unknown'`. No DOM, no three.js. The dispatcher in `scene.js` (Task 5) calls this to decide which loader to invoke.

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/sceneBackgrounds.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { detectBackgroundType } from './sceneBackgrounds.js';

describe('detectBackgroundType', () => {
    it('returns "flat" for .jpg / .jpeg / .png / .webp', () => {
        expect(detectBackgroundType('foo.jpg')).toBe('flat');
        expect(detectBackgroundType('foo.JPEG')).toBe('flat');
        expect(detectBackgroundType('scene/castle.png')).toBe('flat');
        expect(detectBackgroundType('https://x.test/y.webp')).toBe('flat');
    });

    it('returns "hdri" for .hdr / .exr', () => {
        expect(detectBackgroundType('panorama.hdr')).toBe('hdri');
        expect(detectBackgroundType('PANORAMA.EXR')).toBe('hdri');
    });

    it('returns "glb" for .glb / .gltf', () => {
        expect(detectBackgroundType('scene.glb')).toBe('glb');
        expect(detectBackgroundType('scene/diorama.gltf')).toBe('glb');
    });

    it('returns "unknown" for unrecognized or empty input', () => {
        expect(detectBackgroundType('foo.txt')).toBe('unknown');
        expect(detectBackgroundType('')).toBe('unknown');
        expect(detectBackgroundType(null)).toBe('unknown');
        expect(detectBackgroundType(undefined)).toBe('unknown');
    });

    it('strips query strings and fragments before extension match', () => {
        expect(detectBackgroundType('foo.jpg?v=2')).toBe('flat');
        expect(detectBackgroundType('foo.glb#model')).toBe('glb');
    });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -10
```

Expected: 5 failures with module-not-found.

- [ ] **Step 3: Create `incarnation/src/sceneBackgrounds.js`**

```js
/**
 * sceneBackgrounds.js — pure helpers for the tiered background loader.
 *
 * The actual scene mutation (texture / env-map / glTF instance) lives in
 * scene.js where three.js objects are constructed. This module is pure so
 * the extension classification can be unit-tested in node without DOM.
 */

const FLAT_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];
const HDRI_EXTS = ['.hdr', '.exr'];
const GLB_EXTS  = ['.glb', '.gltf'];

/**
 * Classify a background URL by extension.
 *
 * @param {string|null|undefined} url
 * @returns {'flat' | 'hdri' | 'glb' | 'unknown'}
 */
export function detectBackgroundType(url) {
    if (!url || typeof url !== 'string') return 'unknown';
    // Strip query strings (`?v=2`) and fragments (`#x`) so the extension
    // match isn't fooled by cache-busters.
    const stripped = url.split('?')[0].split('#')[0].toLowerCase();
    if (FLAT_EXTS.some((e) => stripped.endsWith(e))) return 'flat';
    if (HDRI_EXTS.some((e) => stripped.endsWith(e))) return 'hdri';
    if (GLB_EXTS.some((e) => stripped.endsWith(e))) return 'glb';
    return 'unknown';
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 7 passed (7) / Tests 76 passed (76)` (was 71; +5 new).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/sceneBackgrounds.js incarnation/src/sceneBackgrounds.test.js
git commit -m "feat(viewer): pure detectBackgroundType for tiered loader"
```

---

### Task 3: HDRI loader (`loadHDRIBackground`)

**Files:**
- Modify: `incarnation/src/scene.js`

Adds a `loadHDRIBackground(url)` helper that uses `RGBELoader` (for `.hdr`) and `EXRLoader` (for `.exr`) to load equirectangular textures, runs them through `PMREMGenerator` to produce an environment map, and assigns BOTH `scene.background` and `scene.environment`. The orchestrator dispatches to this in Task 5.

Manual smoke only — three.js loaders aren't easily unit-testable without browser.

- [ ] **Step 1: Add HDRI loader imports + helper to `scene.js`**

In `incarnation/src/scene.js`, find the existing imports at the top of the file. Add:

```js
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { EXRLoader } from 'three/addons/loaders/EXRLoader.js';
```

Then, near the existing `setBackground` function (around line 83), add a new helper:

```js
/**
 * Load an HDRI panorama (.hdr or .exr) and assign it as both the scene
 * background AND the environment map (image-based lighting). Spec §4b.
 */
function loadHDRIBackground(url) {
    const isExr = url.toLowerCase().split('?')[0].endsWith('.exr');
    const Loader = isExr ? EXRLoader : RGBELoader;
    const loader = new Loader();
    loader.load(url, (hdrTexture) => {
        const pmrem = new THREE.PMREMGenerator(renderer);
        pmrem.compileEquirectangularShader();
        const envMap = pmrem.fromEquirectangular(hdrTexture).texture;
        scene.background = envMap;
        scene.environment = envMap;
        hdrTexture.dispose();
        pmrem.dispose();
    }, undefined, (err) => {
        console.error('[scene] HDRI load failed:', err);
        scene.background = new THREE.Color(0x1a1a2e);
    });
}
```

- [ ] **Step 2: Manual verification deferred to Task 5**

The dispatcher in Task 5 wires this helper. Until then, no behavioral change. Confirm tests still pass:

```bash
make test-js 2>&1 | tail -5
```

Expected: still 76 passed.

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/scene.js
git commit -m "feat(viewer): HDRI background loader (PMREMGenerator)"
```

---

### Task 4: 3D scene loader (`load3DBackground`)

**Files:**
- Modify: `incarnation/src/scene.js`

Adds a `load3DBackground(url)` helper that uses `GLTFLoader` to load a `.glb`/`.gltf`, adds the loaded scene to the main `THREE.Scene` alongside the VRM, and tracks it for cleanup on unload. Failure fallback: flat-grey color + `console.warn`.

- [ ] **Step 1: Add the loader + helper to `scene.js`**

In `incarnation/src/scene.js`, alongside the imports added in Task 3, add:

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
```

Just below the existing `setBackground` (or grouped with `loadHDRIBackground`), add:

```js
// Track the currently-loaded 3D background so we can remove it on swap.
let _bg3DScene = null;

/**
 * Load a 3D background scene (.glb / .gltf). The loaded scene is added
 * to the main THREE.Scene next to the VRM. Existing rim/key lights still
 * apply; any lights packed into the .glb are added on top. Spec §4b.
 *
 * On failure: falls back to a flat grey color and warns.
 */
function load3DBackground(url) {
    if (_bg3DScene) {
        scene.remove(_bg3DScene);
        _bg3DScene = null;
    }
    const loader = new GLTFLoader();
    loader.load(url, (gltf) => {
        _bg3DScene = gltf.scene;
        scene.add(_bg3DScene);
        // Clear any HDRI env map / texture left over from a prior swap.
        scene.background = null;
    }, undefined, (err) => {
        console.warn('[scene] 3D background load failed; falling back to grey:', err);
        scene.background = new THREE.Color(0x1a1a2e);
    });
}
```

- [ ] **Step 2: Verify**

```bash
make test-js 2>&1 | tail -5
```

Expected: still 76 passed.

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/scene.js
git commit -m "feat(viewer): 3D scene background loader (GLTFLoader)"
```

---

### Task 5: Dispatcher + extend `setBackground`

**Files:**
- Modify: `incarnation/src/scene.js`

The dispatcher routes by extension. Existing flat-image path keeps its current implementation. The exported `setBackground` is the single entry point both `incarnation.js` and the WS `set_background` handler already call — just upgraded to the tiered behavior.

- [ ] **Step 1: Replace `setBackground` body with the dispatcher**

In `incarnation/src/scene.js`, alongside the imports add:

```js
import { detectBackgroundType } from './sceneBackgrounds.js';
```

Find the existing `function setBackground(url) { ... }` (around line 83). Replace its body with:

```js
function setBackground(url) {
    if (!url) {
        console.log('[scene] No background URL provided');
        scene.background = new THREE.Color(0x1a1a2e);
        scene.environment = null;
        if (_bg3DScene) { scene.remove(_bg3DScene); _bg3DScene = null; }
        return;
    }

    // Dispatch by extension. Spec §4b "auto-detected by file extension."
    const kind = detectBackgroundType(url);
    // Always tear down any previous 3D background; HDRI's environment map
    // is replaced inline by loadHDRIBackground.
    if (_bg3DScene) { scene.remove(_bg3DScene); _bg3DScene = null; }

    if (kind === 'flat') {
        scene.environment = null;   // flat images aren't IBL sources
        const loader = new THREE.TextureLoader();
        loader.load(url, (texture) => {
            texture.colorSpace = THREE.SRGBColorSpace;
            scene.background = texture;
        }, undefined, (err) => {
            console.error('[scene] Failed to load flat background:', err);
        });
        return;
    }
    if (kind === 'hdri') {
        loadHDRIBackground(url);
        return;
    }
    if (kind === 'glb') {
        load3DBackground(url);
        return;
    }
    console.warn('[scene] unknown background extension:', url);
}
```

- [ ] **Step 2: Manual smoke**

Restart Vite (`npm --prefix incarnation run dev`) and reload the viewer. Existing flat-image backgrounds (e.g. Silver's `castle_interior.jpg`) should continue to work — no visual regression. You don't need an HDRI or `.glb` available yet; Task 6 + the smoke at Task 16 will exercise those when configured.

- [ ] **Step 3: Verify Vitest still passes**

```bash
make test-js 2>&1 | tail -5
```

Expected: still 76 passed.

- [ ] **Step 4: Commit**

```bash
git add incarnation/src/scene.js
git commit -m "feat(viewer): tiered setBackground dispatcher (flat/hdri/glb)"
```

---

### Task 6: Apply `spawn_point` + `camera_target` on model load

**Files:**
- Modify: `incarnation/src/incarnation.js`

When the avatar's `spawn_point` is set, the loaded VRM root is positioned there. When `camera_target` is set, the OrbitControls target shifts (so the camera frames the new position). Defaults match today's behavior (origin / head height) when omitted.

- [ ] **Step 1: Locate the post-load model placement**

In `incarnation/src/incarnation.js`, find `loadPersona` (around line 67). After the line `this.vrm = vrm;` and before any animationManager construction, the VRM is added to the scene. Look for where `model.position` or `vrm.scene.position` is set (or wherever the model is currently placed). If there's no explicit positioning, the VRM lands at world origin.

The current code assumes default placement. Phase 5 adds optional overrides from `config.spawn_point` and `config.camera_target` (the persona's `avatar` block, which is what the server sends in the `load_model` payload).

- [ ] **Step 2: Plumb spawn_point + camera_target through `load_model`**

In `playAIdes.py`, find the `set_active_persona` handler's `load_model` emit. Currently:

```python
                if persona.avatar and persona.avatar.model_url:
                    self.incarnation_server.broadcast_to_persona(
                        requested_id, "load_model",
                        {"url": persona.avatar.model_url},
                    )
```

Update the payload to include the optional positioning fields:

```python
                if persona.avatar and persona.avatar.model_url:
                    self.incarnation_server.broadcast_to_persona(
                        requested_id, "load_model",
                        {
                            "url": persona.avatar.model_url,
                            "spawn_point": list(persona.avatar.spawn_point or []),
                            "camera_target": list(persona.avatar.camera_target or []),
                        },
                    )
```

Also update the avatar setup path that fires on initial boot (the existing `_setup_avatar` method, where `load_model` is sent for the CLI-loaded persona — find it via `grep -n "load_model" playAIdes.py`). Apply the same payload extension.

- [ ] **Step 3: Apply spawn_point + camera_target in `Incarnation.handleCommand` 'load_model' branch**

In `incarnation/src/incarnation.js`, find the `case 'load_model':` in `handleCommand`. After the `await this.loadPersona(...)` call, post-process:

```js
            case 'load_model':
                {
                    const result = await this.loadPersona({ url: payload.url });
                    // Apply optional spawn_point and camera_target from the
                    // persona's avatar config (Phase 5). Defaults match today's
                    // behavior when omitted.
                    if (Array.isArray(payload.spawn_point) && payload.spawn_point.length === 3 && this.vrm) {
                        const [x, y, z] = payload.spawn_point;
                        this.vrm.scene.position.set(x, y, z);
                    }
                    if (Array.isArray(payload.camera_target) && payload.camera_target.length === 3) {
                        const [x, y, z] = payload.camera_target;
                        // controls is imported at the top of incarnation.js from scene.js.
                        controls.target.set(x, y, z);
                        controls.update();
                    }
                    return result;
                }
```

If `controls` isn't already imported in `incarnation.js`, add it to the import line at the top: `import { scene, controls, setBackground, focusOnHead } from './scene.js';` (controls is already exported from scene.js).

- [ ] **Step 4: Manual smoke (deferred to Task 16)**

`make test-js 2>&1 | tail -5` should still show 76 passed. Live verification waits until a persona has `spawn_point` set in `personas/<id>/persona.json`.

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py incarnation/src/incarnation.js
git commit -m "feat(viewer): apply spawn_point + camera_target on model load"
```

---

## Part B — Collapsible chat panel

### Task 7: Pure `transcriptModel.js` — Discord/Slack auto-scroll semantics (Vitest)

**Files:**
- Create: `incarnation/src/transcriptModel.js`
- Test: `incarnation/src/transcriptModel.test.js`

Pure module owning the transcript list + the auto-scroll-vs-freeze decision. No DOM. The DOM-coupled `ChatPanel` (Task 9) consumes the model's state.

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/transcriptModel.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { TranscriptModel } from './transcriptModel.js';

describe('TranscriptModel', () => {
    it('starts empty', () => {
        const t = new TranscriptModel();
        expect(t.messages).toEqual([]);
    });

    it('append adds a message and emits a change event', () => {
        const t = new TranscriptModel();
        const events = [];
        t.addEventListener('change', (e) => events.push(e.detail));
        t.append({ role: 'user', content: 'hi' });
        expect(t.messages).toEqual([{ role: 'user', content: 'hi' }]);
        expect(events).toHaveLength(1);
        expect(events[0].kind).toBe('append');
        expect(events[0].message).toEqual({ role: 'user', content: 'hi' });
    });

    it('replaceAll swaps the list and emits a change event', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'old' });
        const events = [];
        t.addEventListener('change', (e) => events.push(e.detail));
        t.replaceAll([
            { role: 'user', content: 'a' },
            { role: 'assistant', content: 'b' },
        ]);
        expect(t.messages).toEqual([
            { role: 'user', content: 'a' },
            { role: 'assistant', content: 'b' },
        ]);
        expect(events[0].kind).toBe('replaceAll');
    });

    it('clear empties the list and emits change', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'x' });
        const events = [];
        t.addEventListener('change', (e) => events.push(e.detail));
        t.clear();
        expect(t.messages).toEqual([]);
        expect(events[0].kind).toBe('clear');
    });

    it('shouldAutoScrollToBottom is true at construction (user hasn\'t scrolled up)', () => {
        const t = new TranscriptModel();
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });

    it('shouldAutoScrollToBottom flips to false after setUserScrolledUp(true)', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        expect(t.shouldAutoScrollToBottom()).toBe(false);
    });

    it('shouldAutoScrollToBottom flips back to true after setUserScrolledUp(false)', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        t.setUserScrolledUp(false);
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });

    it('append while frozen does NOT change the auto-scroll flag', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        t.append({ role: 'assistant', content: 'new line' });
        expect(t.shouldAutoScrollToBottom()).toBe(false);
    });

    it('replaceAll resets to auto-scroll (e.g. after persona swap rehydrate)', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        t.replaceAll([{ role: 'user', content: 'a' }]);
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });

    it('messages getter returns a defensive copy', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'a' });
        const msgs = t.messages;
        msgs.push({ role: 'assistant', content: 'b' });
        // Internal list is unchanged; getter returned a copy.
        expect(t.messages).toEqual([{ role: 'user', content: 'a' }]);
    });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -10
```

Expected: 10 failures with module-not-found.

- [ ] **Step 3: Create `incarnation/src/transcriptModel.js`**

```js
/**
 * transcriptModel.js — pure transcript state + Discord/Slack-style
 * auto-scroll heuristic.
 *
 * Owns the list of messages displayed in the chat panel and a single
 * "user has scrolled up" flag. The DOM layer (ChatPanel) calls
 * setUserScrolledUp(true) when the user scrolls away from the bottom
 * and false when they return; it consults shouldAutoScrollToBottom()
 * before each render to decide whether to snap to bottom.
 *
 * No DOM references — fully Vitest-testable.
 */
export class TranscriptModel extends EventTarget {
    constructor() {
        super();
        this._messages = [];
        this._userScrolledUp = false;
    }

    /** Defensive copy of the message list. */
    get messages() {
        return this._messages.slice();
    }

    /** Append a single message and emit `change`. */
    append(message) {
        this._messages.push(message);
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'append', message },
        }));
    }

    /** Replace the entire list (e.g. after history_loaded) and reset
     *  the user-scrolled-up flag (a fresh persona's transcript should
     *  always start at the bottom). Emits `change`. */
    replaceAll(messages) {
        this._messages = (messages || []).slice();
        this._userScrolledUp = false;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'replaceAll', messages: this.messages },
        }));
    }

    /** Empty the list (e.g. on persona dismiss). Emits `change`. */
    clear() {
        this._messages = [];
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'clear' },
        }));
    }

    /** DOM layer reports whether the user has scrolled up away from
     *  the bottom. Append while flagged stays put (Slack/Discord). */
    setUserScrolledUp(flag) {
        this._userScrolledUp = !!flag;
    }

    /** Whether the next render should snap to bottom. */
    shouldAutoScrollToBottom() {
        return !this._userScrolledUp;
    }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 8 passed (8) / Tests 86 passed (86)` (was 76; +10 new).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/transcriptModel.js incarnation/src/transcriptModel.test.js
git commit -m "feat(viewer): TranscriptModel with Discord/Slack auto-scroll semantics"
```

---

### Task 8: Chat panel HTML + CSS (collapsed handle + slide-out)

**Files:**
- Modify: `incarnation/index.html`
- Modify: `incarnation/styles/viewer.css`

Pure markup + styling. The right-edge handle is always visible (when chat overlay is enabled); clicking it expands the panel. No JS yet — Task 9 hooks the click.

- [ ] **Step 1: Add the chat-panel markup to `index.html`**

In `incarnation/index.html`, between the existing `<div id="nameplate">…</div>` block and the `<script type="module">…</script>` line, add:

```html
    <!-- Phase 5: collapsible chat panel — right-edge handle + 440px slide-in -->
    <div id="chat-panel" class="chat-panel" aria-hidden="true">
      <button id="chat-panel-handle" class="chat-panel-handle"
              type="button" aria-label="Open chat panel">‹</button>
      <div class="chat-panel-body">
        <header class="chat-panel-header">
          <span id="chat-panel-name" class="chat-panel-name">—</span>
          <span id="chat-panel-wake" class="chat-panel-wake"></span>
        </header>
        <div id="chat-panel-transcript" class="chat-panel-transcript" aria-live="polite"></div>
        <form id="chat-panel-input-row" class="chat-panel-input-row">
          <input id="chat-panel-input" class="chat-panel-input"
                 type="text" autocomplete="off"
                 placeholder="type to speak…" />
          <button id="chat-panel-send" class="chat-panel-send"
                  type="submit" aria-label="Send">▶</button>
        </form>
      </div>
    </div>
```

- [ ] **Step 2: Add chat-panel styles to `viewer.css`**

In `incarnation/styles/viewer.css`, append at the end:

```css
/* ── Chat panel (Phase 5) ─────────────────────────────────── */
.chat-panel {
    position: fixed;
    top: 0;
    right: 0;
    height: 100vh;
    width: 440px;
    z-index: 90;
    pointer-events: none;
    transform: translateX(440px);
    transition: transform .35s var(--ease-snap);
}

.chat-panel.open {
    transform: translateX(0);
}

/* The handle sticks out from the panel's left edge. Always pointer-
   active so the user can click it even when the panel is closed. */
.chat-panel-handle {
    position: absolute;
    top: 50%;
    left: -28px;
    transform: translateY(-50%);
    width: 28px;
    height: 80px;
    background: var(--panel);
    border: var(--hair) solid var(--gold);
    border-right: none;
    color: var(--gold);
    font-family: 'Cinzel', serif;
    font-size: 22px;
    cursor: pointer;
    pointer-events: auto;
    clip-path: polygon(8px 0, 100% 0, 100% 100%, 0 100%);
    z-index: 91;
}

.chat-panel-handle:hover {
    background: var(--panel-hi);
    color: var(--gold-hi);
}

.chat-panel.open .chat-panel-handle {
    /* Flip glyph to indicate "click again to close." */
    transform: translateY(-50%) scaleX(-1);
}

/* Panel body: header + transcript + input row */
.chat-panel-body {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: linear-gradient(180deg, rgba(10, 8, 18, .92), rgba(10, 8, 18, .98));
    border-left: var(--hair) solid var(--gold);
    backdrop-filter: blur(12px);
    pointer-events: auto;
}

.chat-panel-header {
    padding: 18px 24px 12px;
    border-bottom: var(--hair) solid var(--gold-dim);
    font-family: 'Chakra Petch', sans-serif;
    font-size: 13px;
    letter-spacing: .2em;
    text-transform: uppercase;
    color: var(--cream-dim);
    display: flex;
    align-items: baseline;
    gap: 12px;
}

.chat-panel-name {
    color: var(--gold);
    font-weight: 600;
}

.chat-panel-wake {
    font-style: italic;
    font-size: 11px;
}

.chat-panel-transcript {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 16px 24px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    color: var(--cream);
    scrollbar-width: thin;
    scrollbar-color: var(--gold-dim) transparent;
}

.transcript-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.transcript-item .label {
    font-family: 'Chakra Petch', sans-serif;
    font-size: 11px;
    letter-spacing: .15em;
    text-transform: uppercase;
}

.transcript-item.user .label { color: var(--gold); }
.transcript-item.assistant .label { color: var(--red); }

.transcript-item .body {
    white-space: pre-wrap;
    word-break: break-word;
}

.chat-panel-input-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-top: var(--hair) solid var(--gold-dim);
}

.chat-panel-input {
    flex: 1 1 auto;
    background: var(--ink-2);
    border: var(--hair) solid var(--gold-dim);
    color: var(--cream);
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 14px;
    padding: 8px 12px;
    outline: none;
}

.chat-panel-input:focus {
    border-color: var(--gold);
}

.chat-panel-input:disabled {
    opacity: .4;
    cursor: not-allowed;
}

.chat-panel-send {
    background: var(--gold);
    color: var(--ink);
    border: none;
    font-family: 'Cinzel', serif;
    font-size: 14px;
    padding: 8px 14px;
    cursor: pointer;
    clip-path: polygon(6px 0, 100% 0, calc(100% - 6px) 100%, 0 100%);
}

.chat-panel-send:disabled {
    background: var(--gold-dim);
    color: var(--ink-3);
    cursor: not-allowed;
}

.chat-panel-send:hover:not(:disabled) {
    background: var(--gold-hi);
}

/* When the panel is open, suppress the subtitle band — spec §5
   "Chat panel open: subtitle band is suppressed to avoid duplicating text." */
body[data-chat-open="true"] .subtitle-band {
    display: none;
}
```

- [ ] **Step 3: Manual verification**

`make test-js 2>&1 | tail -5` should still show 86 passed (no JS changes here).

Reload the viewer in the browser. The right edge should show a small gold-rimmed handle with `‹`. Clicking it does nothing yet (Task 9 wires the click). The panel itself is hidden off-screen.

- [ ] **Step 4: Commit**

```bash
git add incarnation/index.html incarnation/styles/viewer.css
git commit -m "feat(viewer): chat panel HTML + CSS (collapsed handle, slide-in)"
```

---

### Task 9: ChatPanel JS class — DOM rendering + handle toggle

**Files:**
- Create: `incarnation/src/chatPanel.js`

DOM-coupled class wrapping the `TranscriptModel`. Renders messages, attaches the handle click, manages open/closed state, sets `body[data-chat-open]` so CSS can suppress the subtitle band.

- [ ] **Step 1: Create `incarnation/src/chatPanel.js`**

```js
/**
 * chatPanel.js — DOM rendering for the right-edge collapsible chat panel.
 *
 * Subscribes to a TranscriptModel for message updates, renders user /
 * assistant transcript items, manages the open/closed state, and exposes
 * a typed-input event the orchestrator listens to so it can forward the
 * text as a `user_input` WS frame (skipping STT).
 *
 * State pip rendering during LISTENING / THINKING / SPEAKING is the
 * orchestrator's job — it calls setLiveState(state) which classifies the
 * tail item.
 */
export class ChatPanel extends EventTarget {
    /**
     * @param {object} root         DOM root containing the panel elements
     * @param {TranscriptModel} model
     * @param {object} options      { initialOpen?: boolean }
     */
    constructor(root, model, options = {}) {
        super();
        this.root = root;
        this.model = model;

        this.elPanel       = root.querySelector('#chat-panel');
        this.elHandle      = root.querySelector('#chat-panel-handle');
        this.elName        = root.querySelector('#chat-panel-name');
        this.elWake        = root.querySelector('#chat-panel-wake');
        this.elTranscript  = root.querySelector('#chat-panel-transcript');
        this.elForm        = root.querySelector('#chat-panel-input-row');
        this.elInput       = root.querySelector('#chat-panel-input');
        this.elSend        = root.querySelector('#chat-panel-send');

        this._open = false;
        if (options.initialOpen) this.open();

        this.elHandle?.addEventListener('click', () => this.toggle());
        this.elForm?.addEventListener('submit', (e) => this._onSubmit(e));
        this.elTranscript?.addEventListener('scroll', () => this._onScroll());

        this.model.addEventListener('change', () => this._render());
        this._render();
    }

    open() {
        this._open = true;
        this.elPanel?.classList.add('open');
        this.elPanel?.setAttribute('aria-hidden', 'false');
        if (document?.body) document.body.dataset.chatOpen = 'true';
        // Snap to bottom on first open so the latest line is visible.
        requestAnimationFrame(() => {
            if (this.elTranscript) {
                this.elTranscript.scrollTop = this.elTranscript.scrollHeight;
            }
        });
    }

    close() {
        this._open = false;
        this.elPanel?.classList.remove('open');
        this.elPanel?.setAttribute('aria-hidden', 'true');
        if (document?.body) document.body.dataset.chatOpen = 'false';
    }

    toggle() {
        if (this._open) this.close(); else this.open();
    }

    isOpen() { return this._open; }

    /** Update header (called when persona_active / persona_changed arrives). */
    setPersona(name, primaryWakeWord = '') {
        if (this.elName) this.elName.textContent = name || '—';
        if (this.elWake) this.elWake.textContent = primaryWakeWord ? `· "${primaryWakeWord}"` : '';
    }

    /** Disable the input — e.g. during SPEAKING. */
    setInputEnabled(enabled) {
        if (this.elInput) this.elInput.disabled = !enabled;
        if (this.elSend) this.elSend.disabled = !enabled;
    }

    _onSubmit(e) {
        e.preventDefault();
        const text = (this.elInput?.value || '').trim();
        if (!text) return;
        this.elInput.value = '';
        this.dispatchEvent(new CustomEvent('submit', { detail: { text } }));
    }

    _onScroll() {
        if (!this.elTranscript) return;
        const distanceFromBottom = this.elTranscript.scrollHeight
            - this.elTranscript.scrollTop
            - this.elTranscript.clientHeight;
        // Tolerate a few px of jitter from sub-pixel layout.
        this.model.setUserScrolledUp(distanceFromBottom > 24);
    }

    _render() {
        if (!this.elTranscript) return;
        // Re-render full transcript on every change. Cheap for v1's expected
        // sizes (capped by CHAT_HISTORY_CAP=80 turns); revisit if profiling
        // shows scroll thrash.
        this.elTranscript.innerHTML = '';
        for (const msg of this.model.messages) {
            const item = document.createElement('div');
            item.className = `transcript-item ${msg.role}`;
            const label = document.createElement('div');
            label.className = 'label';
            label.textContent = msg.role === 'user' ? 'You' : (msg.persona_name || 'Persona');
            const body = document.createElement('div');
            body.className = 'body';
            body.textContent = msg.content;
            item.append(label, body);
            this.elTranscript.appendChild(item);
        }
        if (this.model.shouldAutoScrollToBottom()) {
            requestAnimationFrame(() => {
                this.elTranscript.scrollTop = this.elTranscript.scrollHeight;
            });
        }
    }
}
```

- [ ] **Step 2: Manual verification (deferred to Task 10+ wiring)**

`make test-js 2>&1 | tail -5` should still show 86 passed.

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/chatPanel.js
git commit -m "feat(viewer): ChatPanel class — handle toggle + transcript render"
```

---

### Task 10: Wire ChatPanel into the orchestrator

**Files:**
- Modify: `incarnation/src/viewer.js`

Instantiate `TranscriptModel` + `ChatPanel`. Wire:
- `persona_active` and `persona_changed` → `setPersona`
- `history_loaded` → `transcriptModel.replaceAll(history)`
- Locally-emitted `user_input` (typed) → `transcriptModel.append({role:'user', content})`
- `assistant_message` → `transcriptModel.append({role:'assistant', content, persona_name})`
- ChatPanel's `submit` event → `connection.send('user_input', { text, persona_id })`
- URL `?chat=open` → `chatPanel.open()` at boot

- [ ] **Step 1: Add imports near the top of `viewer.js`**

In `incarnation/src/viewer.js`, alongside the existing imports, add:

```js
import { TranscriptModel } from './transcriptModel.js';
import { ChatPanel } from './chatPanel.js';
```

- [ ] **Step 2: Construct the model + panel at boot**

Just below the existing `const wipeOverlay = ...` line (Phase 4), add:

```js
const transcriptModel = new TranscriptModel();
const chatPanel = new ChatPanel(document, transcriptModel, {
    initialOpen: config.chat === 'open',
});

// When the panel form is submitted, treat it like a voice transcription:
// send user_input and append the user line locally so it shows up
// immediately (assistant_message will append the reply).
chatPanel.addEventListener('submit', (e) => {
    const text = e.detail.text;
    transcriptModel.append({ role: 'user', content: text });
    // Tag the user_input with the active persona's id so multi-TV routing
    // delivers the reply to the right clients.
    const activeId = personasRegistry.all()
        .find((p) => p.name === activePersona.name)?.id || null;
    connection.send('user_input', activeId
        ? { text, persona_id: activeId }
        : { text });
});
```

- [ ] **Step 3: Wire `persona_active` / `persona_changed` to update the panel header**

In the existing `connection.addEventListener('persona_active', ...)` block, after `overlays.setPersonaName(activePersona.name);`, add:

```js
    chatPanel.setPersona(
        activePersona.name,
        (activePersona.wake_words && activePersona.wake_words[0]) || '',
    );
```

In the existing `connection.addEventListener('persona_changed', ...)` block, just after the early returns and before `wipeOverlay.play()`, add (note that `persona_changed` carries the full persona dict):

```js
    if (persona) {
        chatPanel.setPersona(
            persona.name,
            (Array.isArray(persona.wake_words) && persona.wake_words[0]) || '',
        );
        // Persona swap → fresh transcript (history_loaded will rehydrate).
        transcriptModel.clear();
    }
```

- [ ] **Step 4: Wire `history_loaded` → rehydrate transcript**

Add a new connection listener block (near the other Phase-4 server-event listeners):

```js
connection.addEventListener('history_loaded', (e) => {
    const history = Array.isArray(e.detail?.history) ? e.detail.history : [];
    // Tag assistant items with the persona name for the panel's label;
    // the on-disk format is { role, content } only.
    const tagged = history.map((m) => ({
        ...m,
        persona_name: activePersona.name,
    }));
    transcriptModel.replaceAll(tagged);
    console.log('[viewer] transcript rehydrated, n=', tagged.length);
});
```

- [ ] **Step 5: Wire `assistant_message` → append**

In the existing `connection.addEventListener('assistant_message', ...)` block (added in Phase 1, currently just stashes the text into `pendingAssistantText`), append to the transcript model too:

```js
connection.addEventListener('assistant_message', (e) => {
    pendingAssistantText = e.detail?.text || '';
    if (pendingAssistantText) {
        transcriptModel.append({
            role: 'assistant',
            content: pendingAssistantText,
            persona_name: activePersona.name,
        });
    }
});
```

- [ ] **Step 6: Wire user_input from voice → append to transcript**

Currently the voiceend handler calls `connection.send('user_input', { text: userInput })`. Right after that send, append to the transcript model:

```js
        lastUserUtterance = userInput;
        transcriptModel.append({ role: 'user', content: userInput });
        connection.send('user_input', { text: userInput });
        console.log('[viewer] user_input sent:', userInput);
```

(Apply this in BOTH `connection.send('user_input', { text: userInput })` call sites in the voiceend handler — the cross-persona-swap branch and the normal-route branch.)

- [ ] **Step 7: Disable input during SPEAKING; re-enable on AMBIENT**

Add a state-machine listener that toggles the input:

```js
stateMachine.addEventListener('change', (e) => {
    const next = e.detail.next;
    if (next === State.SPEAKING) {
        chatPanel.setInputEnabled(false);
    } else if (next === State.AMBIENT || next === State.EMPTY) {
        chatPanel.setInputEnabled(true);
    }
});
```

- [ ] **Step 8: Manual verification (deferred to Task 11)**

`make test-js 2>&1 | tail -5` should still show 86 passed.

- [ ] **Step 9: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "feat(viewer): wire ChatPanel — transcript, history rehydrate, typed input"
```

---

### Task 11: End-to-end smoke + final review

**Files:**
- None — verification only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `136 passed, 4 deselected` (was 131; +5 new schema tests from Task 1).

- [ ] **Step 2: JS tests still green**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 8 passed (8) / Tests 86 passed (86)` (was 71; +5 sceneBackgrounds + +10 transcriptModel).

- [ ] **Step 3: Live smoke**

Start the stack as before:

```bash
# Terminal 1
make whisper

# Terminal 2
python main.py --persona personas/silver/persona.json --use_avatar

# Terminal 3
npm --prefix incarnation run dev
```

Open `http://localhost:5173/` in Chrome.

**Backgrounds smoke:**

3a. **Flat image** — Silver's `castle_interior.jpg` should render as today (no regression). Confirm in DevTools Network tab that the .jpg URL was fetched.

3b. **HDRI** — temporarily swap Silver's `background_url` to a `.hdr` file (find any HDRI panorama; e.g. download a free one from Poly Haven and drop it in `incarnation/public/scene/`). Restart the Python backend, reload the viewer. Expect Silver to be lit by the panorama (notice rim lighting changes) AND the panorama to render as the background. If the load fails, console logs `[scene] HDRI load failed:` and the background falls back to the dark blue color.

3c. **3D scene (.glb)** — same trick with a `.glb` file. The Silver VRM should appear "inside" the loaded scene; the existing rim/key lights still apply. Failure path falls back to flat grey with a `console.warn`.

3d. **Spawn point + camera target** — temporarily add `"spawn_point": [1.0, 0, 0]` and `"camera_target": [1.0, 1.1, 0]` to Silver's `avatar` block. Restart backend, reload. Expect Silver shifted 1 m to the right, with the camera framing her at the new position.

**Chat panel smoke:**

3e. **Right-edge handle** — visible at the right edge with a `‹` glyph. Click → panel slides in from the right. Click handle again (now `›`-style flipped) → slides out.

3f. **`?chat=open`** — visit `http://localhost:5173/?chat=open`. Panel is pre-expanded.

3g. **Typed input** — type *"Hello Silver, what time is it?"* in the input, hit Enter. The user line appears immediately ("You" caret in gold), then Silver's reply appears (her name caret in crimson). Confirm DevTools Network → WS frames: a `user_input` frame goes out (no STT round-trip; no `/api/stt/proxy` request).

3h. **Auto-scroll** — fill the panel with several messages until it scrolls. Scroll up manually. Send a new message — the panel should NOT snap to bottom (Slack/Discord semantics). Scroll back to the bottom — next new message snaps as expected.

3i. **Subtitle suppression** — close the panel. Speak to Silver via voice; the subtitle band shows the reply. Reopen the panel. Speak again — the subtitle band is hidden; reply text appears in the panel only.

3j. **Input disabled during SPEAKING** — while Silver is mid-reply, the input + send button are greyed out. Once the audio ends, both re-enable.

3k. **Persona swap rehydrates transcript** — say *"Hey Rin, are you there?"*. After the wipe, the transcript clears and (if Rin has prior on-disk history) rehydrates with Rin's earlier turns; her reply appends.

- [ ] **Step 4: Self-review against spec §10 Phase 5 row**

| Spec bullet | Where |
|---|---|
| Three-tier background loader (flat/HDRI/3D) | Tasks 2, 3, 4, 5 |
| `spawn_point` + `camera_target` schema | Task 1 |
| spawn_point/camera_target applied on model load | Task 6 |
| Right-edge handle | Task 8, 9 |
| Transcript rehydrated from history_loaded | Task 10 |
| Text input (typed → user_input WS) | Task 9, 10 |
| URL `?chat=open` toggle | Task 10 |
| Subtitle suppression when panel open | Task 8 (CSS), `body[data-chat-open]` written by Task 9 |

- [ ] **Step 5: Final consistency check**

- `detectBackgroundType` exports → imported in `scene.js`.
- `loadHDRIBackground` and `load3DBackground` defined in `scene.js`, only used by `setBackground`.
- `_bg3DScene` module-level in `scene.js`, cleared by `setBackground` and `load3DBackground`.
- `spawn_point` / `camera_target` payload keys match between Python emit (`playAIdes.py`'s `load_model`) and JS reception (`incarnation.js` `case 'load_model'`).
- `TranscriptModel` exported from `transcriptModel.js`, imported in `viewer.js` and tested in `transcriptModel.test.js`.
- `ChatPanel` exported from `chatPanel.js`, imported in `viewer.js`.
- `body[data-chat-open]` value is the literal string `"true"` / `"false"` (JS sets these via `dataset.chatOpen`), and CSS selector matches with `[data-chat-open="true"]`.
- `config.chat === 'open'` matches the value `viewerConfig.loadConfig` already returns for `?chat=open` (Phase 1).

- [ ] **Step 6: No commit (process marker)**

---

## Self-review checklist (run before marking phase 5 done)

- [ ] **Spec coverage** — every bullet in spec §10 Phase 5 row maps to a task. Checked above.
- [ ] **No placeholders** — search the plan for `TBD`, `TODO`, `FIXME`. None.
- [ ] **Type / name consistency** — `detectBackgroundType`, `loadHDRIBackground`, `load3DBackground`, `setBackground`, `TranscriptModel`, `ChatPanel`, `transcriptModel`, `chatPanel`, `spawn_point`, `camera_target`, `body[data-chat-open]`. Verified above.
- [ ] **Phase boundaries respected** — no settings UI, no markdown, no message editing, no animated backgrounds, no voice scene control. All explicitly out of scope.
- [ ] **Failure fallbacks present** — HDRI load failure → dark blue color; 3D scene load failure → flat grey + warn. Spec §4b.
- [ ] **Backwards compat preserved** — `Avatar.spawn_point` / `Avatar.camera_target` are `Optional` with `None` defaults; `chat=closed` remains the default URL state.
