# Viewer Redesign — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `incarnation/index.html` with a new voice-first viewer page that scaffolds the full five-state UI machine, renders configurable overlays driven by URL params, and plays a configurable intro animation on persona load — while the existing terminal-driven chat continues to drive the SPEAKING state via the existing `start_lip_sync` flow.

**Architecture:** A thin orchestrator (`viewer.js`) owns a pure state machine (`viewerState.js`) and a DOM-rendering overlay layer (`viewerOverlays.js`). It reuses the existing `Incarnation`, `ConnectionManager`, and `LipSyncManager` modules unchanged in spirit — the orchestrator just listens to their events and feeds the state machine. Design tokens are extracted into `tokens.css` so both the new viewer and the existing Persona Forge share one source of truth.

**Tech Stack:** Vanilla JS (ES modules, no framework), Three.js + @pixiv/three-vrm (already in package.json), Vite dev server, FastAPI backend (existing), pytest for backend tests.

**Branch:** `viewer_redesign` (already created, this plan lives there).

**Reference spec:** `docs/superpowers/specs/2026-04-24-viewer-redesign-design.md` — read §1, §2, §4, §10 before starting. Phase 1 implements only states `INTRO`, `AMBIENT`, and `SPEAKING`; states `EMPTY`, `LISTENING`, `THINKING` are scaffolded in `viewerState.js` but not yet reachable.

## Conventions for this plan

- **Frontend (JS/CSS/HTML)** has no automated test framework in this codebase. Tasks that touch only frontend code use **manual verification steps** explicitly. JS testing infrastructure is a separate follow-up.
- **Backend (Python)** uses TDD with pytest. The repo already has 75 tests and uses a Docker-only test runner (`make test`).
- Each task ends with a commit. Use Conventional Commits prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- All file paths in this plan are relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.
- The dev server is started with `npm --prefix incarnation run dev` (Vite picks port 5173). The Python backend runs separately via `python main.py --persona personas/<id>/persona.json --use_avatar`.

---

## Task 1: Extract design tokens into a shared CSS file

**Files:**
- Create: `incarnation/styles/tokens.css`
- Modify: `incarnation/styles/creator.css`

**Why this comes first:** Both creator.css and the upcoming viewer.css will need the same color/font/easing tokens. Extracting them now means we don't have to change creator.css later in the plan to switch import paths.

- [ ] **Step 1: Create `incarnation/styles/tokens.css` with the tokens currently inline at the top of creator.css**

```css
/* =============================================================
   Shared design tokens for PlayAIdes pages.
   Both creator.css and viewer.css @import this so they stay
   visually in sync.
   ============================================================= */

@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Chakra+Petch:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

:root {
    --ink:        #0a0812;
    --ink-2:      #14111d;
    --ink-3:      #1e1a2a;
    --panel:      #181423;
    --panel-hi:   #221c30;

    --gold:       #d4a74b;
    --gold-hi:    #f6d37a;
    --gold-dim:   #87712e;

    --red:        #e11a3a;
    --red-hi:     #ff3a5a;
    --red-dim:    #7a0d20;

    --cream:      #f4ecd8;
    --cream-dim:  #b9b0a0;
    --muted:      #6b6478;

    --ok:         #7ed87a;

    --hair:       1px;
    --pad-lg:     28px;
    --pad-md:     18px;
    --pad-sm:     10px;

    --ease-snap:  cubic-bezier(.2, .8, .2, 1);
    --ease-slash: cubic-bezier(.7, .1, .2, 1);
}

/* Selection color is shared across pages */
::selection { background: var(--red); color: var(--cream); }

/* Webkit scrollbar baseline */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--gold-dim); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--gold); }
```

- [ ] **Step 2: Replace the duplicated block at the top of `incarnation/styles/creator.css` with an `@import` of tokens.css**

In `incarnation/styles/creator.css`, the file currently begins with the `@import url('https://fonts.googleapis.com/...')` line, then the `:root` block of design tokens, then `::selection` and webkit scrollbar rules.

Delete those exact blocks (the `@import` for fonts, the `:root { … }` block, the `::selection` rule, and the four `::-webkit-scrollbar*` rules) and replace them with a single line at the top of the file:

```css
@import url('./tokens.css');
```

Leave everything below that block (the reset, body styling, layout rules, etc.) intact.

- [ ] **Step 3: Verify the Persona Forge still renders identically**

```bash
npm --prefix incarnation run dev
```

Open `http://localhost:5173/creator.html`. Visually confirm: gold/crimson colors, Cinzel header, Chakra Petch buttons, gold scrollbars, the form layout — all unchanged from before. If anything looks broken, check for typos in tokens.css.

- [ ] **Step 4: Commit**

```bash
git add incarnation/styles/tokens.css incarnation/styles/creator.css
git commit -m "refactor: extract shared design tokens into tokens.css"
```

---

## Task 2: Add `intro_animation` field to the Avatar schema (TDD)

**Files:**
- Modify: `persona.py` (Avatar BaseModel)
- Test: `tests/unit/test_persona.py` (extend existing test class)

- [ ] **Step 1: Write the failing test**

Add this test class at the end of `tests/unit/test_persona.py`:

```python
class TestAvatarIntroAnimation:
    def test_intro_animation_optional(self):
        """Avatar without intro_animation parses fine (backwards compat)."""
        a = Avatar(model_url="m.vrm")
        assert a.intro_animation is None

    def test_intro_animation_set(self):
        """Avatar with intro_animation set carries the string through."""
        a = Avatar(model_url="m.vrm", intro_animation="cute_greeting_twirl")
        assert a.intro_animation == "cute_greeting_twirl"

    def test_intro_animation_distinct_from_idle(self):
        """intro_animation and idle_animation can be set independently."""
        a = Avatar(
            model_url="m.vrm",
            intro_animation="wave",
            idle_animation="stand",
        )
        assert a.intro_animation == "wave"
        assert a.idle_animation == "stand"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
make test 2>&1 | grep -E "(FAILED|test_intro)" | head
```

Expected: three failures with `pydantic.ValidationError: Object has no attribute 'intro_animation'` (or similar — the field doesn't exist yet).

- [ ] **Step 3: Add the field to the Avatar model**

In `persona.py`, modify the `Avatar` class. Add the new field directly after `idle_animation`:

```python
class Avatar(BaseModel): #optional
    model_url: str # this can also be a local file path
    animations_url: Optional[str] = None # this can also be a local folder path
    idle_animation: Optional[str] = "idle" # default idle animation name
    intro_animation: Optional[str] = None # plays once on activation, before idle
    animation_list: Optional[List[str]] = None # we need to get the animation list from the model and also
    #add animations we have loaded
    background_url: Optional[str] = None
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
make test 2>&1 | tail -3
```

Expected: `78 passed, 3 deselected` (was 75; we added 3 tests).

- [ ] **Step 5: Commit**

```bash
git add persona.py tests/unit/test_persona.py
git commit -m "feat(persona): add Avatar.intro_animation field"
```

---

## Task 3: Wire `intro_animation` into `playAIdes.load_default_animations`

**Files:**
- Modify: `playAIdes.py` (specifically `load_default_animations` and the `_handle_incarnation_message` "model_loaded" branch)
- Test: `tests/unit/test_playaides_chat.py` (extend) or new `tests/integration/test_intro_animation.py`

The existing code in `playAIdes.py` line ~308 (inside `_handle_incarnation_message` `state == "animation_loaded"` branch, after all expected animations finish loading) sends a hardcoded `play_animation` for `"cute_greeting_twirl"`. Phase 1 makes this configurable via the persona's `avatar.intro_animation`. If unset, fall back to the persona's `idle_animation`.

- [ ] **Step 1: Read the current code so the change is precise**

```bash
grep -n "cute_greeting_twirl\|idle_animation\|expected_animations" playAIdes.py
```

You should see the hardcoded "cute_greeting_twirl" inside the `if not self.expected_animations:` branch, and the `idle_animation` fallback inside the `state == "animation_finished"` branch. Make sure you understand the flow: animations finish loading → server sends `play_animation` for the intro → intro finishes → `animation_finished` event → server sends `play_animation` for idle.

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_intro_animation.py`:

```python
"""Integration tests: intro_animation drives the post-load greeting clip."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _persona_dict(intro=None, idle="idle"):
    return {
        "name": "Test",
        "back_ground": "test",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {
            "model_url": "m.vrm",
            "idle_animation": idle,
            **({"intro_animation": intro} if intro else {}),
        },
    }


def _seed(tmp_personas_dir, persona):
    pdir = tmp_personas_dir / "test"
    pdir.mkdir(exist_ok=True)
    (pdir / "persona.json").write_text(json.dumps(persona))
    return pdir / "persona.json"


@pytest.fixture
def args_factory(tmp_personas_dir, fake_tts, no_incarnation):
    def make(persona_file):
        return PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False, use_voice=False,
            use_avatar=True, generate_avatar=False,
            llm=MockLLM(), tts=fake_tts,
        )
    return make


class TestIntroAnimation:
    def test_intro_animation_used_when_set(self, tmp_personas_dir, args_factory):
        """When intro_animation is set, it's the first thing played after model load."""
        f = _seed(tmp_personas_dir, _persona_dict(intro="wave_hello"))
        play = PlayAIdes(args_factory(f))
        # Simulate the frontend reporting all animations finished loading.
        # (load_default_animations populates expected_animations; we drain it.)
        play.expected_animations.clear()
        # Trigger the post-load greeting path
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "animation_loaded", "name": "wave_hello"},
        })
        # The stub IncarnationServer captures every send_command call
        cmds = play.incarnation_server.commands
        names_played = [
            payload.get("name") for cmd, payload in cmds if cmd == "play_animation"
        ]
        assert "wave_hello" in names_played, f"got: {names_played}"

    def test_falls_back_to_idle_when_intro_unset(self, tmp_personas_dir, args_factory):
        """No intro_animation → first play_animation is the idle clip."""
        f = _seed(tmp_personas_dir, _persona_dict(intro=None, idle="stand"))
        play = PlayAIdes(args_factory(f))
        play.expected_animations.clear()
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "animation_loaded", "name": "stand"},
        })
        cmds = play.incarnation_server.commands
        names = [p.get("name") for c, p in cmds if c == "play_animation"]
        assert "stand" in names
```

- [ ] **Step 3: Run the test to confirm it fails**

```bash
make test 2>&1 | grep -E "(FAILED|test_intro_animation)" | head
```

Expected: at least `test_intro_animation_used_when_set` fails because the code currently always sends `"cute_greeting_twirl"` regardless of the persona config.

- [ ] **Step 4: Implement — replace the hardcoded clip name**

In `playAIdes.py`, find the block inside `_handle_incarnation_message` that fires when `not self.expected_animations:` (around line 306–311). Currently:

```python
if not self.expected_animations:
    logger.info("All auto-loaded animations finished loading. Playing initial animation...")
    self.incarnation_server.send_command("play_animation", {
        "name": "cute_greeting_twirl",
        "loop": False
    })
```

Replace with:

```python
if not self.expected_animations:
    logger.info("All auto-loaded animations finished loading. Playing intro animation...")
    intro = (self.current_persona.avatar.intro_animation
             if (self.current_persona and self.current_persona.avatar)
             else None)
    fallback_idle = (self.current_persona.avatar.idle_animation
                     if (self.current_persona and self.current_persona.avatar)
                     else "idle")
    clip_name = intro or fallback_idle
    self.incarnation_server.send_command("play_animation", {
        "name": clip_name,
        "loop": False if intro else True,
    })
```

The `loop: False` is preserved for the intro (so we transition to idle when it ends). When falling back to idle directly (no intro configured), loop the idle.

- [ ] **Step 5: Run the test to confirm it passes**

```bash
make test 2>&1 | tail -3
```

Expected: `80 passed, 3 deselected` (was 78; we added 2 tests).

- [ ] **Step 6: Commit**

```bash
git add playAIdes.py tests/integration/test_intro_animation.py
git commit -m "feat: replace hardcoded greeting clip with persona.avatar.intro_animation"
```

---

## Task 4: Emit `assistant_message` from `PlayAIdes.chat()` for the subtitle band

**Files:**
- Modify: `playAIdes.py` (`chat()` method)
- Test: `tests/unit/test_playaides_chat.py` (extend)

In phase 2 the browser will send `user_input` over WS, but in phase 1 chat input still arrives via terminal stdin. We still want the new viewer's subtitle band to render the assistant's reply text. The fix is small: when `chat()` produces a reply and `use_avatar` is true (so an incarnation server is running), broadcast an `assistant_message` over WS *before* `start_lip_sync`. Browser-side, the subtitle band reads this.

- [ ] **Step 1: Write the failing test**

Add this to `tests/unit/test_playaides_chat.py`:

```python
class TestAssistantMessageBroadcast:
    """When use_avatar is on, chat() emits an assistant_message WS command
    carrying the reply text, before any audio is dispatched. This drives
    the new viewer's subtitle band even when the terminal is the input."""

    def test_emits_assistant_message_with_reply_text(
        self, persona_file, fake_tts, no_incarnation
    ):
        # use_avatar=True so an IncarnationServer (stub) is wired
        args = PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False,
            use_voice=False,
            use_avatar=True,
            generate_avatar=False,
            llm=MockLLM(),
            tts=fake_tts,
        )
        play = PlayAIdes(args)
        reply = play.chat("hello there")
        cmds = play.incarnation_server.commands
        assistant_messages = [
            (cmd, payload) for cmd, payload in cmds if cmd == "assistant_message"
        ]
        assert len(assistant_messages) == 1
        _, payload = assistant_messages[0]
        assert payload["text"] == reply

    def test_no_message_when_avatar_disabled(
        self, persona_file, fake_tts, no_incarnation
    ):
        # use_avatar=False → no incarnation_server → nothing to emit to
        args = PlayAIdesArgs(
            persona=[str(persona_file)],
            generate_voice=False,
            use_voice=False,
            use_avatar=False,
            generate_avatar=False,
            llm=MockLLM(),
            tts=fake_tts,
        )
        play = PlayAIdes(args)
        # incarnation_server is None when use_avatar=False
        assert play.incarnation_server is None
        # Should not raise
        play.chat("hi")
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
make test 2>&1 | grep -E "(FAILED|assistant_message)" | head
```

Expected: `test_emits_assistant_message_with_reply_text` fails because no such command is emitted today.

- [ ] **Step 3: Implement — emit `assistant_message` after the LLM reply**

In `playAIdes.py`, modify the `chat()` method. After the line `response = self.llm.chat(...)` but before any audio dispatch, broadcast the text. Around line 350 the method currently looks like:

```python
        response = self.llm.chat(self.chat_history, system_prompt=system_prompt)
        if self.args.use_voice:
            if self.args.use_avatar and self.incarnation_server:
                # … existing lip_sync proxy code …
```

Add an emit BEFORE the `if self.args.use_voice:` block:

```python
        response = self.llm.chat(self.chat_history, system_prompt=system_prompt)

        # Broadcast the reply text to any connected viewer so its subtitle
        # band can render before TTS audio arrives. No-op if the
        # incarnation server isn't running (CLI-only mode).
        if self.incarnation_server is not None:
            self.incarnation_server.send_command(
                "assistant_message",
                {"text": response},
            )

        if self.args.use_voice:
            # … existing code unchanged …
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `82 passed, 3 deselected` (was 80; we added 2 tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/unit/test_playaides_chat.py
git commit -m "feat: emit assistant_message WS event for subtitle rendering"
```

---

## Task 5: Add `intro_animation` to the Handy persona fixture

**Files:**
- Modify: `personas/handy.json`

Tiny task — exercise the new field in the existing test fixture so any future regression in JSON loading is caught.

- [ ] **Step 1: Edit `personas/handy.json` — add `avatar` block with intro animation**

Replace the file contents with:

```json
{
    "name": "Handy",
    "back_ground": "A helpful digital assistant.",
    "psyche": {
        "traits": [
            "helpful",
            "concise",
            "witty"
        ]
    },
    "gender": "Female",
    "language": "English",
    "avatar": {
        "model_url": "models/handy/handy.vrm",
        "idle_animation": "idle",
        "intro_animation": "wave_hello"
    }
}
```

- [ ] **Step 2: Verify the existing `test_handy_json_fixture_parses` test still passes**

```bash
make test 2>&1 | grep -E "(handy|PASSED.*test_persona)" | head
```

Expected: `test_handy_json_fixture_parses PASSED`.

- [ ] **Step 3: Commit**

```bash
git add personas/handy.json
git commit -m "chore(personas): add intro_animation to Handy fixture"
```

---

## Task 6: `viewerConfig.js` — URL-param parser

**Files:**
- Create: `incarnation/src/viewerConfig.js`

Pure module — no DOM, no side effects. Returns a frozen `Config` object the orchestrator passes around. Manual verification only (no JS test framework).

- [ ] **Step 1: Create the file**

```js
/**
 * viewerConfig.js — parse URL params into a frozen Config object.
 *
 * Read ONCE at viewer boot. URL changes after boot require a reload —
 * keeps the surface tiny and the state machine simpler.
 *
 * Schema (matches docs/superpowers/specs/2026-04-24-viewer-redesign-design.md §7):
 *
 *   ?persona=<id>                 // boot persona
 *   ?activation=wake|continuous   // voice activation mode (phase 2+)
 *   ?cinematic=0|1                // master overlay kill-switch
 *   ?mic=0|1                      // show mic indicator
 *   ?subtitles=0|1                // show subtitle band
 *   ?nameplate=0|1                // show persona nameplate
 *   ?chat=closed|open             // chat panel initial (phase 5+)
 *   ?ws=<url>                     // websocket URL override
 *   ?api=<url>                    // REST base URL override
 */

const DEFAULTS = Object.freeze({
    persona: null,
    activation: 'wake',
    cinematic: false,
    mic: true,
    subtitles: true,
    nameplate: false,
    chat: 'closed',
    wsUrl: 'ws://localhost:8765/ws',
    apiBase: 'http://localhost:8765',
});

/** Parse a URLSearchParams flag like "0" / "1" / "true" / "false" / undefined. */
function parseBool(value, fallback) {
    if (value === null || value === undefined) return fallback;
    const v = String(value).toLowerCase();
    if (v === '0' || v === 'false' || v === 'off') return false;
    if (v === '1' || v === 'true'  || v === 'on')  return true;
    return fallback;
}

/** Build a frozen Config from `window.location.search` (or any URLSearchParams-like). */
export function loadConfig(search = window.location.search) {
    const p = new URLSearchParams(search);

    const config = {
        persona:     p.get('persona') || DEFAULTS.persona,
        activation:  (p.get('activation') === 'continuous') ? 'continuous' : 'wake',
        cinematic:   parseBool(p.get('cinematic'), DEFAULTS.cinematic),
        mic:         parseBool(p.get('mic'),       DEFAULTS.mic),
        subtitles:   parseBool(p.get('subtitles'), DEFAULTS.subtitles),
        nameplate:   parseBool(p.get('nameplate'), DEFAULTS.nameplate),
        chat:        (p.get('chat') === 'open') ? 'open' : 'closed',
        wsUrl:       p.get('ws')  || DEFAULTS.wsUrl,
        apiBase:     p.get('api') || DEFAULTS.apiBase,
    };

    // Master kill-switch: ?cinematic=1 forces all overlays off regardless
    // of their individual flags.
    if (config.cinematic) {
        config.mic = false;
        config.subtitles = false;
        config.nameplate = false;
    }

    return Object.freeze(config);
}
```

- [ ] **Step 2: Manual verification**

Open the dev server (`npm --prefix incarnation run dev` if not running) and in the browser console at `http://localhost:5173/`:

```js
const m = await import('/src/viewerConfig.js');
console.log(m.loadConfig('?persona=silver&cinematic=1'));
// Expected: { persona: "silver", cinematic: true, mic: false, subtitles: false, nameplate: false, ... }

console.log(m.loadConfig('?subtitles=0'));
// Expected: { ..., subtitles: false, mic: true, nameplate: false, ... }

console.log(m.loadConfig(''));
// Expected: defaults — { persona: null, mic: true, subtitles: true, nameplate: false, ... }
```

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/viewerConfig.js
git commit -m "feat(viewer): URL-param parser (loadConfig)"
```

---

## Task 7: `viewerState.js` — pure state machine

**Files:**
- Create: `incarnation/src/viewerState.js`

Pure module — emits events via `EventTarget`. The orchestrator subscribes; the overlay layer subscribes; the avatar layer subscribes. No DOM here.

- [ ] **Step 1: Create the file**

```js
/**
 * viewerState.js — the viewer's UI state machine.
 *
 * States (per spec §2):
 *   EMPTY      — no persona on screen, mic still listening (phase 4)
 *   INTRO      — persona just loaded, intro animation playing
 *   AMBIENT    — persona idling, waiting for input
 *   LISTENING  — capturing user audio (phase 2)
 *   THINKING   — STT + LLM round-trip in flight (phase 2)
 *   SPEAKING   — TTS audio playing + lip sync
 *
 * Phase 1 only reachable states are INTRO, AMBIENT, SPEAKING. The other
 * three are scaffolded so phases 2–4 can wire them without changing
 * the contract.
 *
 * This module deliberately holds no DOM references. Subscribers
 * (overlays, orchestrator) listen on the EventTarget for `change`.
 */

export const State = Object.freeze({
    EMPTY:     'EMPTY',
    INTRO:     'INTRO',
    AMBIENT:   'AMBIENT',
    LISTENING: 'LISTENING',
    THINKING:  'THINKING',
    SPEAKING:  'SPEAKING',
});

/** Allowed transitions per the state diagram in spec §2. */
const TRANSITIONS = {
    EMPTY:     ['INTRO'],                        // wake-word summon (phase 4)
    INTRO:     ['AMBIENT', 'EMPTY'],             // intro anim ends → AMBIENT
    AMBIENT:   ['LISTENING', 'SPEAKING', 'EMPTY', 'INTRO'],
    LISTENING: ['THINKING', 'AMBIENT', 'EMPTY'],
    THINKING:  ['SPEAKING', 'AMBIENT', 'EMPTY'], // AMBIENT on STT failure
    SPEAKING:  ['AMBIENT', 'EMPTY'],             // audio ends → AMBIENT
};

export class ViewerState extends EventTarget {
    /** @param {string} initial — one of the State constants */
    constructor(initial = State.EMPTY) {
        super();
        if (!Object.values(State).includes(initial)) {
            throw new Error(`ViewerState: invalid initial state "${initial}"`);
        }
        this._state = initial;
        /** @type {object|null} arbitrary metadata attached to the current state */
        this._meta = null;
    }

    /** Current state name. */
    get current() { return this._state; }

    /** Metadata attached to the current state (e.g. last assistant message text). */
    get meta() { return this._meta; }

    /**
     * Attempt to transition to a new state. Throws on illegal transitions.
     * @param {string} next — target state (use the State constants)
     * @param {object} [meta] — optional metadata, available on the next state
     */
    transition(next, meta = null) {
        if (!Object.values(State).includes(next)) {
            throw new Error(`ViewerState: invalid target state "${next}"`);
        }
        const allowed = TRANSITIONS[this._state] || [];
        if (!allowed.includes(next)) {
            // Illegal transitions are a programming error — fail loud rather
            // than silently corrupting state.
            throw new Error(
                `ViewerState: illegal transition ${this._state} → ${next}`
            );
        }
        const prev = this._state;
        const prevMeta = this._meta;
        this._state = next;
        this._meta = meta;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { prev, next, prevMeta, meta },
        }));
    }
}
```

- [ ] **Step 2: Manual verification**

Browser console at `http://localhost:5173/`:

```js
const { ViewerState, State } = await import('/src/viewerState.js');
const sm = new ViewerState(State.EMPTY);
sm.addEventListener('change', e => console.log('→', e.detail.prev, '→', e.detail.next));
sm.transition(State.INTRO);    // logs "→ EMPTY → INTRO"
sm.transition(State.AMBIENT);  // logs "→ INTRO → AMBIENT"
sm.transition(State.SPEAKING, { text: "Hello" });
console.log(sm.current, sm.meta); // "SPEAKING" { text: "Hello" }

// Illegal transition should throw:
try { sm.transition(State.INTRO); } catch (e) { console.log("expected:", e.message); }
// Expected: "ViewerState: illegal transition SPEAKING → INTRO"
```

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/viewerState.js
git commit -m "feat(viewer): pure state machine (EMPTY/INTRO/AMBIENT/LISTENING/THINKING/SPEAKING)"
```

---

## Task 8: `viewerOverlays.js` — mic indicator, subtitle band, name plate

**Files:**
- Create: `incarnation/src/viewerOverlays.js`

DOM-only side. Receives the state machine and the config. Writes to fixed-position elements that `viewer.html` provides. No state of its own beyond a fade-out timer for the subtitle band.

- [ ] **Step 1: Create the file**

```js
/**
 * viewerOverlays.js — the DOM rendering side of the viewer.
 *
 * Owns three independently-toggleable overlay regions described in the
 * spec §4:
 *   • Mic / state indicator   — bottom-left dot whose color tracks state
 *   • Subtitle band           — bottom-center, only visible while SPEAKING
 *   • Name plate              — top-left chip with persona name + conn dot
 *
 * Overlays are toggled at construction time from the URL config; once
 * disabled, their elements stay hidden for the session.
 *
 * The state machine is the only event source we listen to; backend WS
 * events flow through the orchestrator which decides what state the
 * machine should be in.
 */

import { State } from './viewerState.js';

const SUBTITLE_FADE_MS = 2000;   // how long the subtitle stays visible after audio ends

export class ViewerOverlays {
    /**
     * @param {object} root — DOM root containing the overlay elements
     * @param {object} config — frozen Config from viewerConfig.loadConfig()
     * @param {import('./viewerState.js').ViewerState} state
     */
    constructor(root, config, state) {
        this.root = root;
        this.config = config;
        this.state = state;

        this.elMic       = root.querySelector('#mic-indicator');
        this.elSubtitle  = root.querySelector('#subtitle-band');
        this.elSubText   = root.querySelector('#subtitle-text');
        this.elNameplate = root.querySelector('#nameplate');
        this.elPName     = root.querySelector('#nameplate-name');
        this.elConnDot   = root.querySelector('#nameplate-conn');

        // Hide overlays the user opted out of (config.cinematic forces all off).
        if (!config.mic && this.elMic)             this.elMic.hidden       = true;
        if (!config.subtitles && this.elSubtitle)  this.elSubtitle.hidden  = true;
        if (!config.nameplate && this.elNameplate) this.elNameplate.hidden = true;

        this._subtitleTimer = null;

        state.addEventListener('change', (e) => this._onStateChange(e.detail));
    }

    /** Update name + connection status in the nameplate (no-op if hidden). */
    setPersonaName(name) {
        if (this.elPName) this.elPName.textContent = name || '—';
    }

    setConnectionState(kind) {
        // kind: 'connected' | 'disconnected' | 'error'
        if (!this.elConnDot) return;
        this.elConnDot.classList.remove('connected', 'disconnected', 'error');
        this.elConnDot.classList.add(kind);
    }

    // ── State-driven rendering ──────────────────────────────────────────

    _onStateChange({ next, meta }) {
        // Mic indicator: color/animation per state. CSS owns the actual
        // styling — we just attach a class.
        if (this.elMic && !this.elMic.hidden) {
            this.elMic.className = 'mic-indicator state-' + next.toLowerCase();
        }

        // Subtitle band: only the SPEAKING state populates it; it fades
        // out 2s after the state leaves SPEAKING.
        if (this.elSubtitle && !this.elSubtitle.hidden) {
            if (next === State.SPEAKING) {
                clearTimeout(this._subtitleTimer);
                if (this.elSubText) this.elSubText.textContent = (meta && meta.text) || '';
                this.elSubtitle.classList.add('visible');
            } else if (this.state.current !== State.SPEAKING) {
                // Just left SPEAKING — start the fade-out timer.
                clearTimeout(this._subtitleTimer);
                this._subtitleTimer = setTimeout(() => {
                    this.elSubtitle.classList.remove('visible');
                }, SUBTITLE_FADE_MS);
            }
        }
    }
}
```

- [ ] **Step 2: Commit**

We can't render-test this until viewer.html exists — that's task 9. Commit the module now.

```bash
git add incarnation/src/viewerOverlays.js
git commit -m "feat(viewer): overlay rendering layer (mic, subtitle, nameplate)"
```

---

## Task 9: `viewer.css` — overlay styling and state visuals

**Files:**
- Create: `incarnation/styles/viewer.css`

- [ ] **Step 1: Create the file**

```css
/* =============================================================
   viewer.css — voice-driven viewer page.
   Quieter than creator.css: canvas dominates, chrome appears only
   when active. Imports shared tokens from tokens.css.
   ============================================================= */

@import url('./tokens.css');

/* ── Reset ────────────────────────────────────────────────── */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; }

body {
    font-family: 'Inter', system-ui, sans-serif;
    background: #000;
    color: var(--cream);
    overflow: hidden;
    letter-spacing: .01em;
}

/* ── Canvas (full page) ────────────────────────────────────── */
#viewer {
    display: block;
    width: 100%;
    height: 100%;
    position: fixed;
    inset: 0;
    z-index: 1;
}

/* ── Top P5 strip (gold + crimson, decorative) ─────────────── */
.viewer-strip {
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg,
        var(--red) 0 6%,
        transparent 6% 8%,
        var(--red) 8% 14%,
        transparent 14% 50%,
        var(--gold) 50% 54%,
        transparent 54% 56%,
        var(--gold) 56% 62%
    );
    z-index: 100;
    clip-path: polygon(0 0, 100% 0, calc(100% - 24px) 100%, 24px 100%);
    pointer-events: none;
}

/* ── Mic / state indicator (bottom-left) ───────────────────── */
.mic-indicator {
    position: fixed;
    bottom: 24px;
    left: 24px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--gold-dim);
    box-shadow: 0 0 12px rgba(212, 167, 75, .25);
    z-index: 80;
    transition: background .3s var(--ease-snap), box-shadow .3s var(--ease-snap);
}

.mic-indicator.state-empty,
.mic-indicator.state-ambient {
    background: var(--gold-dim);
    box-shadow: 0 0 10px rgba(212, 167, 75, .35);
    animation: micSlowPulse 3s ease-in-out infinite;
}

.mic-indicator.state-intro {
    background: var(--gold-hi);
    box-shadow: 0 0 14px rgba(246, 211, 122, .65);
}

.mic-indicator.state-listening {
    background: var(--red);
    box-shadow:
        0 0 18px rgba(225, 26, 58, .9),
        0 0 36px rgba(225, 26, 58, .35);
    animation: micFastPulse .5s ease-in-out infinite;
}

.mic-indicator.state-thinking {
    background: var(--gold);
    box-shadow: 0 0 14px rgba(212, 167, 75, .55);
    animation: micSpin 1.3s linear infinite;
}

.mic-indicator.state-speaking {
    background: var(--red-dim);
    box-shadow: 0 0 10px rgba(122, 13, 32, .55);
}

@keyframes micSlowPulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes micFastPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.4); } }
@keyframes micSpin     { 0% { transform: rotate(0); } 100% { transform: rotate(360deg); } }

/* ── Subtitle band (bottom centre) ─────────────────────────── */
.subtitle-band {
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    bottom: 80px;
    max-width: min(80vw, 900px);
    padding: 16px 28px;
    background: linear-gradient(180deg, rgba(10, 8, 18, .82), rgba(10, 8, 18, .95));
    border: var(--hair) solid var(--gold);
    color: var(--cream);
    font-family: 'Cinzel', serif;
    font-size: 18px;
    letter-spacing: .04em;
    text-align: center;
    line-height: 1.5;
    backdrop-filter: blur(8px);
    clip-path: polygon(14px 0, 100% 0, calc(100% - 14px) 100%, 0 100%);
    opacity: 0;
    transform-origin: bottom center;
    transition: opacity .35s var(--ease-snap);
    z-index: 70;
    pointer-events: none;
}

.subtitle-band.visible {
    opacity: 1;
}

/* ── Name plate (top-left under strip) ─────────────────────── */
.nameplate {
    position: fixed;
    top: 18px;
    left: 24px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    background: rgba(10, 8, 18, .7);
    border: var(--hair) solid var(--gold);
    backdrop-filter: blur(8px);
    font-family: 'Chakra Petch', sans-serif;
    font-size: 12px;
    letter-spacing: .2em;
    color: var(--cream);
    z-index: 60;
    clip-path: polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%);
}

.nameplate-name {
    color: var(--gold);
    font-weight: 600;
}

.nameplate-conn {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--muted);
    box-shadow: 0 0 6px currentColor;
    transition: background .3s;
}
.nameplate-conn.connected    { background: var(--ok); }
.nameplate-conn.disconnected { background: var(--muted); }
.nameplate-conn.error        { background: var(--red-hi); }
```

- [ ] **Step 2: Commit**

```bash
git add incarnation/styles/viewer.css
git commit -m "feat(viewer): viewer.css with overlay + state visuals"
```

---

## Task 10: `viewer.js` — orchestrator

**Files:**
- Create: `incarnation/src/viewer.js`

The orchestrator wires everything together. It reuses the existing `Incarnation` class (model + animations + lip-sync — no rewrites) and the existing `ConnectionManager` (WebSocket). It owns one `ViewerState` and one `ViewerOverlays`. It listens to:

- WS `load_model` → load avatar via `Incarnation`, then transition `EMPTY → INTRO`.
- WS `play_animation` → forward to `Incarnation`. If the played clip is the persona's intro, when it finishes transition `INTRO → AMBIENT`. (Playback finish events flow back through `Incarnation.onAnimationFinished`.)
- WS `start_lip_sync` → transition to `SPEAKING`. Forward to `Incarnation`. When audio ends, transition back to `AMBIENT`.
- WS `assistant_message` → attach `text` to the next `SPEAKING` transition (subtitle band reads it).

- [ ] **Step 1: Modify `incarnation/src/lipSyncManager.js` to expose an audio-ended callback**

Find the `LipSyncManager` constructor and add an `_onAudioEndCallback` field. Then in the `_onAudioEnded` arrow function (currently lines ~311–317), invoke the callback if set. The change is two lines + one line.

In `lipSyncManager.js`, near the top of the constructor (after `this._smoothVolume = 0;` around line 47), add:

```javascript
        /** @type {(() => void) | null} fired when bound audio finishes */
        this._onAudioEndCallback = null;
```

And add a setter method below `clearVisemes()` (or wherever near other public API):

```javascript
    /** Register a callback fired when bound audio playback ends or pauses. */
    onAudioEnd(callback) {
        this._onAudioEndCallback = callback;
    }
```

Then modify the existing `_onAudioEnded` arrow at the bottom of the class:

```javascript
    /** @private */
    _onAudioEnded = () => {
        console.log('[LipSync] Audio element ended/paused');
        this._active = false;
        if (this.visemeManager) {
            this.visemeManager.clearVisemes();
        }
        if (this._onAudioEndCallback) {
            try { this._onAudioEndCallback(); } catch (e) { console.error(e); }
        }
    };
```

- [ ] **Step 2: Create `incarnation/src/viewer.js`**

```js
/**
 * viewer.js — entry point for the new voice-driven viewer page.
 *
 * Reuses Incarnation + ConnectionManager + LipSyncManager unchanged.
 * Adds: ViewerState (state machine), ViewerOverlays (DOM rendering),
 * ViewerConfig (URL params).
 *
 * Phase 1 wires only INTRO / AMBIENT / SPEAKING — the LISTENING and
 * THINKING states will be reached in phase 2 once mic capture lands.
 */
import { scene, camera, renderer, controls, clock } from './scene.js';
import { Incarnation } from './incarnation.js';
import { ConnectionManager } from './connectionManager.js';
import { ViewerState, State } from './viewerState.js';
import { ViewerOverlays } from './viewerOverlays.js';
import { loadConfig } from './viewerConfig.js';

// ── Boot ────────────────────────────────────────────────────────────────────
const config = loadConfig();
console.log('[viewer] config:', config);

const stateMachine = new ViewerState(State.EMPTY);
const overlays = new ViewerOverlays(document, config, stateMachine);
const incarnation = new Incarnation();
const connection = new ConnectionManager();

// Pending text from the most recent assistant_message event — attached
// to the next SPEAKING transition so the subtitle band can render.
let pendingAssistantText = '';

// ── Connection + overlays ───────────────────────────────────────────────────
connection.addEventListener('connected', () => {
    overlays.setConnectionState('connected');
});
connection.addEventListener('disconnected', () => {
    overlays.setConnectionState('disconnected');
});
connection.addEventListener('error', () => {
    overlays.setConnectionState('error');
});

// ── Wire animation finished back to PlayAIdes (preserves existing flow) ────
incarnation.onAnimationFinished = (clipName) => {
    connection.send('status', { state: 'animation_finished', name: clipName });
};

// ── State transition helpers ────────────────────────────────────────────────
function safeTransition(next, meta) {
    try {
        stateMachine.transition(next, meta);
    } catch (err) {
        // Illegal transitions are warnings here, not crashes — phase 1
        // still has uncovered edges (e.g. SPEAKING → SPEAKING when a
        // user sends two messages back-to-back).
        console.warn('[viewer]', err.message);
    }
}

// ── WebSocket-driven transitions ────────────────────────────────────────────
connection.addEventListener('load_model', async (e) => {
    try {
        const info = await incarnation.handleCommand('load_model', e.detail);
        connection.send('status', { state: 'model_loaded', ...info });
        // We stay in EMPTY here — INTRO begins when the intro animation
        // actually starts playing (via play_animation below).
        if (incarnation.vrm) {
            const personaName =
                (incarnation.vrm.meta && incarnation.vrm.meta.title) ||
                e.detail.url?.split('/').pop()?.replace(/\.vrm$/i, '') ||
                'Persona';
            overlays.setPersonaName(personaName);
        }
    } catch (err) {
        console.error('[viewer] load_model failed:', err);
    }
});

connection.addEventListener('load_animation', async (e) => {
    const info = await incarnation.handleCommand('load_animation', e.detail);
    connection.send('status', { state: 'animation_loaded', ...info });
});
connection.addEventListener('load_mixamo_animation', async (e) => {
    const info = await incarnation.handleCommand('load_mixamo_animation', e.detail);
    connection.send('status', { state: 'animation_loaded', ...info });
});
connection.addEventListener('load_vrma_animation', async (e) => {
    const info = await incarnation.handleCommand('load_vrma_animation', e.detail);
    connection.send('status', { state: 'animation_loaded', ...info });
});

connection.addEventListener('play_animation', (e) => {
    const looped = e.detail?.loop !== false;
    incarnation.handleCommand('play_animation', e.detail);
    // Heuristic: a non-looped clip after EMPTY → INTRO transition.
    // A looped clip → AMBIENT.
    if (stateMachine.current === State.EMPTY) {
        if (looped) {
            // No intro configured; persona went straight to idle.
            safeTransition(State.INTRO);
            safeTransition(State.AMBIENT);
        } else {
            safeTransition(State.INTRO);
        }
    } else if (stateMachine.current === State.INTRO) {
        // The intro just got replaced by another animation — assume
        // it's the idle.
        if (looped) safeTransition(State.AMBIENT);
    }
});

// Existing onAnimationFinished hook → drive INTRO → AMBIENT.
const originalOnFinished = incarnation.onAnimationFinished;
incarnation.onAnimationFinished = (clipName) => {
    if (stateMachine.current === State.INTRO) {
        // Intro clip ended; PlayAIdes will respond with the idle clip,
        // but we eagerly transition so the UI doesn't stay on the
        // intro state visuals.
        safeTransition(State.AMBIENT);
    }
    if (originalOnFinished) originalOnFinished(clipName);
};

// ── assistant_message + start_lip_sync drive SPEAKING ──────────────────────
connection.addEventListener('assistant_message', (e) => {
    pendingAssistantText = e.detail?.text || '';
});

connection.addEventListener('start_lip_sync', (e) => {
    const fromAmbient = stateMachine.current === State.AMBIENT;
    if (!fromAmbient && stateMachine.current !== State.THINKING) {
        // Force-transition to AMBIENT first so the SPEAKING transition
        // is legal. This handles the case where the SPEAKING state
        // arrives while still in INTRO (server sent a chat reply during
        // the intro).
        try { safeTransition(State.AMBIENT); } catch (_) { /* fine */ }
    }
    safeTransition(State.SPEAKING, { text: pendingAssistantText });
    incarnation.handleCommand('start_lip_sync', e.detail);
});

connection.addEventListener('stop_lip_sync', () => {
    incarnation.handleCommand('stop_lip_sync', {});
    safeTransition(State.AMBIENT);
});

// LipSyncManager fires this when the audio element ends or pauses.
incarnation.lipSyncManager.onAudioEnd(() => {
    if (stateMachine.current === State.SPEAKING) {
        safeTransition(State.AMBIENT);
    }
});

// Generic catch-all for non-load_ commands (set_expression, focus_camera,
// set_background, etc.) — preserve existing behavior.
connection.addEventListener('message', (e) => {
    const msg = e.detail;
    if (msg.type
        && !msg.type.startsWith('load_')
        && msg.type !== 'play_animation'
        && msg.type !== 'start_lip_sync'
        && msg.type !== 'stop_lip_sync'
        && msg.type !== 'assistant_message') {
        incarnation.handleCommand(msg.type, msg.payload || {});
    }
});

// ── Audio Unlock ────────────────────────────────────────────────────────────
// First user gesture resumes AudioContext — same pattern as the previous
// main.js. Phase 2 will replace the listener-list with a richer mic flow.
const GESTURES = ['click', 'keydown', 'touchstart', 'pointerdown'];
async function unlockAudio() {
    GESTURES.forEach((t) => window.removeEventListener(t, unlockAudio, true));
    if (incarnation.lipSyncManager) {
        await incarnation.lipSyncManager.resume();
    }
    console.log('[viewer] audio unlocked');
}
GESTURES.forEach((t) => window.addEventListener(t, unlockAudio, true));

// ── Render loop ─────────────────────────────────────────────────────────────
function tick() {
    requestAnimationFrame(tick);
    const dt = clock.getDelta();
    controls.update();
    incarnation.update(dt);
    renderer.render(scene, camera);
}

// ── Connect + start ─────────────────────────────────────────────────────────
connection.connect(config.wsUrl);
tick();
console.log('[viewer] started — ws:', config.wsUrl);
```

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/lipSyncManager.js incarnation/src/viewer.js
git commit -m "feat(viewer): orchestrator + LipSync onAudioEnd callback"
```

---

## Task 11: Replace `incarnation/index.html` with the new viewer markup

**Files:**
- Modify: `incarnation/index.html`

- [ ] **Step 1: Replace the file contents**

Overwrite `incarnation/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Incarnation — PlayAIdes</title>
    <link rel="stylesheet" href="/styles/viewer.css" />
  </head>
  <body>
    <!-- Decorative top strip (always visible regardless of cinematic mode) -->
    <div class="viewer-strip"></div>

    <!-- 3D canvas (full-page, behind everything) -->
    <canvas id="viewer"></canvas>

    <!-- Overlays. Each is hidden by viewerOverlays.js when its config flag
         (or the master cinematic flag) is off. -->
    <div id="mic-indicator" class="mic-indicator state-empty"></div>

    <div id="subtitle-band" class="subtitle-band">
      <span id="subtitle-text"></span>
    </div>

    <div id="nameplate" class="nameplate">
      <span id="nameplate-conn" class="nameplate-conn"></span>
      <span id="nameplate-name" class="nameplate-name">—</span>
    </div>

    <script type="module" src="/src/viewer.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add incarnation/index.html
git commit -m "feat(viewer): replace index.html shell with new viewer markup"
```

---

## Task 12: Delete the now-unused `main.js`

**Files:**
- Delete: `incarnation/src/main.js`

The old entry point is no longer referenced. Removing it prevents future confusion and keeps the build lean.

- [ ] **Step 1: Confirm no references remain**

```bash
grep -rln "main\.js" incarnation/ --include='*.html' --include='*.js'
```

Expected: no matches (or only matches in `node_modules/`).

- [ ] **Step 2: Delete the file**

```bash
git rm incarnation/src/main.js
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(viewer): remove obsolete main.js entry point"
```

---

## Task 13: Trim `incarnation/styles/main.css`

**Files:**
- Decision needed; either modify or delete `incarnation/styles/main.css`

The old `main.css` had reset rules and status-overlay styling for the previous viewer. Nothing else in the codebase imports it now (verify in step 1). Two paths: trim it down, or delete it.

- [ ] **Step 1: Confirm no other files reference `main.css`**

```bash
grep -rln "main\.css" incarnation/ --include='*.html' --include='*.js' --include='*.css'
```

Expected: no matches. If any match exists, do not delete — instead trim main.css to only what those files need.

- [ ] **Step 2: Delete the file (if no references)**

```bash
git rm incarnation/styles/main.css
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore(viewer): remove obsolete main.css"
```

---

## Task 14: End-to-end smoke test

**Files:**
- None — this task is verification only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `82 passed, 3 deselected` (75 baseline + 3 from Task 2 + 2 from Task 3 + 2 from Task 4).

- [ ] **Step 2: Vite dev server still serves both pages**

```bash
npm --prefix incarnation run dev
```

Visit each URL and confirm the page renders (not a 404, not a JS console error):

- `http://localhost:5173/` — new Viewer (canvas + overlays).
- `http://localhost:5173/creator.html` — Persona Forge unchanged.

The Viewer should show the gold/red strip at the top, a small dim-gold mic dot bottom-left (slow pulse), no subtitle visible, no nameplate (off by default).

- [ ] **Step 3: Cinematic mode**

Visit `http://localhost:5173/?cinematic=1`. The mic dot, subtitle, and nameplate are all hidden. Only the strip and canvas are visible.

- [ ] **Step 4: Overlay toggles**

Visit `http://localhost:5173/?nameplate=1&subtitles=1`. Nameplate is visible (top-left chip). Subtitle band is hidden (only appears in SPEAKING state).

- [ ] **Step 5: Live persona test (with backend)**

In a second terminal:

```bash
python main.py --persona personas/silver/persona.json --use_avatar
```

Refresh the Viewer browser tab (`http://localhost:5173/?persona=silver&nameplate=1`). Click anywhere on the page once (audio gesture).

Expected sequence:
1. Connection dot in nameplate goes green.
2. Silver's VRM loads.
3. The mic dot brightens to gold (`state-intro` class) while the intro animation plays.
4. After the intro finishes, mic dot returns to dim-gold pulse (`state-ambient`), idle anim loops.
5. Type into the terminal: "Hello, who are you?" Press enter.
6. Subtitle band fades in showing the reply text. Mic dot is dim-red (`state-speaking`). Audio plays + lip sync drives the mouth.
7. After audio ends, mic dot returns to dim-gold pulse. Subtitle band fades out 2 s later.

If any step fails, open devtools console — the orchestrator logs every state transition (`[viewer] →`).

- [ ] **Step 6: Commit (no changes — just a marker)**

This step exists as a process checkpoint. No file changes; nothing to commit. Move on if everything looks right.

---

## Self-review checklist (run against the spec before marking phase 1 done)

- [ ] **Spec coverage** — go to `docs/superpowers/specs/2026-04-24-viewer-redesign-design.md` §10 phase 1 row. Each bullet maps to a task above:
    - "New HTML/CSS/JS for the viewer page replacing index.html" → Tasks 9, 10, 11
    - "Extracted tokens.css" → Task 1
    - "Configurable overlays via URL params" → Tasks 6, 8, 9
    - "State machine scaffolded" → Task 7
    - "INTRO plays avatar.intro_animation (or skips when missing) → AMBIENT plays avatar.idle_animation" → Tasks 2, 3, 5
    - "Existing terminal-driven chat still works for SPEAKING" → Task 4 + Task 10's wiring + smoke test in Task 14
    - "No mic" → confirmed by what's *not* added
    - "Backgrounds still load via existing set_background command" → confirmed; viewer.js's catch-all in `connection.addEventListener('message', …)` forwards `set_background` to `Incarnation.handleCommand` unchanged.

- [ ] **No placeholders** — search the plan for `TBD`, `TODO`, `FIXME`. None should exist.

- [ ] **Type / name consistency** — verify `intro_animation` (snake-case) is the field name in `persona.py` (Task 2), in `playAIdes.py` access (Task 3), in `personas/handy.json` (Task 5). Verify state names match between `viewerState.js` (`State.EMPTY`, `State.INTRO`, etc.) and CSS classes (`.state-empty`, `.state-intro`, etc.) — they're lowercased one-to-one in `viewerOverlays.js:_onStateChange` via `next.toLowerCase()`. Verify `onAudioEnd` in `LipSyncManager` matches the call site in `viewer.js`.
