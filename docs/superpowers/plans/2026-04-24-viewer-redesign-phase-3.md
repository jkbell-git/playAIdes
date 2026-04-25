# Viewer Redesign — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hands-free start + dismiss for the active persona. Add `wake_words`, `dismiss_words`, and `is_default` fields to the persona schema; push the active persona's matching config to the browser; check each STT transcript against dismiss-then-wake; handle the EMPTY state visually (canvas fade-out + nameplate hidden) with re-summon via wake word.

**Architecture:** Browser-side matching, deliberately. A new pure JS module `transcriptMatcher.js` exposes one function `matchPhrase(transcript, phrases) → {matched, phrase, residual}` with full Vitest coverage (case-insensitive, longest-first, EN+JP friendly via raw substring). The orchestrator's existing `voiceend` handler gains a dismiss→wake gate before forwarding `user_input`. The server pushes a new `persona_active` WS message at avatar-ready time so the browser knows what to match. Phase 3 deliberately limits matching to the **currently-active** persona's wake words — cross-persona swap is Phase 4.

**Tech Stack:** Vanilla JS (ES modules + Vitest), Pydantic v2 (already in use), FastAPI WebSocket (already in use), pytest.

**Branch:** continue on `viewer_redesign` after Phase 2 lands.

**Reference spec:** `docs/superpowers/specs/2026-04-24-viewer-redesign-design.md` — read §2 (state machine, especially the `EMPTY` and `Dismiss` sub-sections), §3 (Wake-word and dismiss matching, Voice activation modes), §6 (Backend additions: assistant_message persona_id deferred, but persona_data shape applies), §7 (URL params + Persona schema additions). Phase 3 wires `wake_words`, `dismiss_words`, `is_default` plus the EMPTY visuals; INTRO animation replay on re-summon is intentionally deferred to Phase 4 (it requires a new server-side trigger and is more naturally bundled with `set_active_persona`).

## Conventions for this plan

- **Backend (Python)** uses TDD via `make test`. Whisper-touching tests use `respx`; no live STT in Phase 3.
- **Frontend (JS)** pure modules use Vitest in Docker (`make test-js`). DOM-coupled wiring uses manual browser verification.
- Each task ends with a commit. Conventional Commits prefixes.
- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.

## Phase 3 simplifications (deferred)

- **Cross-persona swap is Phase 4.** In Phase 3, only the currently-active persona's `wake_words` are checked. Saying another persona's wake word is a no-op (dropped in `wake` mode, treated as plain user input in `continuous`).
- **Re-summon doesn't replay the intro animation.** Wake-word match while in EMPTY transitions `EMPTY → INTRO → AMBIENT` for state correctness, but no `play_animation` is sent. The model just fades back in via CSS. Phase 4 wires the server-side replay alongside `set_active_persona`.
- **`is_default` is parsed and validated but not yet used for boot persona selection.** That's `set_active_persona` territory — Phase 4. We add the schema field now so personas can carry it forward.
- **`persona_id` field on `user_input` and `assistant_message` is still deferred.** Phase 4.

---

## Task 1: Persona schema — `wake_words`, `dismiss_words`, `is_default` (TDD)

**Files:**
- Modify: `persona.py` (Persona BaseModel)
- Test: `tests/unit/test_persona.py` (extend existing test class)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_persona.py`:

```python
class TestPersonaWakeAndDismiss:
    def test_wake_words_optional(self):
        """Persona without wake_words parses fine (backwards compat)."""
        p = Persona(
            name="X", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.wake_words is None

    def test_dismiss_words_optional(self):
        """Persona without dismiss_words parses fine (backwards compat)."""
        p = Persona(
            name="X", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.dismiss_words is None

    def test_is_default_defaults_to_false(self):
        """Missing is_default defaults to False, not None."""
        p = Persona(
            name="X", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.is_default is False

    def test_wake_and_dismiss_set(self):
        """List values pass through unchanged."""
        p = Persona(
            name="Silver", back_ground="bg", psyche=Psyche(traits=[]),
            gender="Female", language="English",
            wake_words=["hey silver", "silver", "シルバー"],
            dismiss_words=["goodnight silver", "おやすみ"],
            is_default=True,
        )
        assert p.wake_words == ["hey silver", "silver", "シルバー"]
        assert p.dismiss_words == ["goodnight silver", "おやすみ"]
        assert p.is_default is True
```

The test imports `Persona` and `Psyche` from `persona`. Verify both are already imported at the top of `test_persona.py` before adding (they should be — other test classes use them).

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|TestPersonaWakeAndDismiss)" | head
```

Expected: 3-4 failures with `pydantic.ValidationError: ... Object has no attribute 'wake_words' ...`.

- [ ] **Step 3: Add the fields to the Persona model**

In `persona.py`, locate the `Persona` class. Add three fields directly above `memories: Optional[Dict[str, ...]]` (or wherever `memories` lives — append at the end of the field list otherwise):

```python
class Persona(BaseModel):
    # … existing fields …
    wake_words: Optional[List[str]] = None
    dismiss_words: Optional[List[str]] = None
    is_default: Optional[bool] = False
    # … memories etc. last …
```

The exact placement matters less than the fact that they're all `Optional` with safe defaults so existing personas don't break.

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `96 passed, 4 deselected` (was 92; +4 new tests).

- [ ] **Step 5: Commit**

```bash
git add persona.py tests/unit/test_persona.py
git commit -m "feat(persona): add wake_words, dismiss_words, is_default fields"
```

---

## Task 2: Server pushes `persona_active` to the browser

**Files:**
- Modify: `playAIdes.py` (`_handle_incarnation_message`, the `state == "model_loaded"` branch)
- Test: `tests/integration/test_persona_active_emit.py` (new)

When the frontend reports `state == "model_loaded"`, the server already triggers `load_default_animations`. Phase 3 also broadcasts a new `persona_active` WS message so the browser can cache the active persona's matching config (name + wake_words + dismiss_words) for client-side matching.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_persona_active_emit.py`:

```python
"""Integration test: server emits `persona_active` to the browser when the
avatar reports model_loaded, carrying name + wake_words + dismiss_words."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _persona_dict(wake=None, dismiss=None):
    return {
        "name": "Silver",
        "back_ground": "test",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {"model_url": "m.vrm"},
        **({"wake_words": wake} if wake is not None else {}),
        **({"dismiss_words": dismiss} if dismiss is not None else {}),
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


class TestPersonaActiveEmit:
    def test_emits_persona_active_on_model_loaded(self, tmp_personas_dir, args_factory):
        """A model_loaded status triggers a persona_active broadcast carrying
        the matching config."""
        f = _seed(tmp_personas_dir, _persona_dict(
            wake=["hey silver", "シルバー"],
            dismiss=["goodnight silver"],
        ))
        play = PlayAIdes(args_factory(f))
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "model_loaded", "name": "Silver.vrm"},
        })
        cmds = play.incarnation_server.commands
        active = [(c, p) for c, p in cmds if c == "persona_active"]
        assert len(active) == 1
        _, payload = active[0]
        assert payload["name"] == "Silver"
        assert payload["wake_words"] == ["hey silver", "シルバー"]
        assert payload["dismiss_words"] == ["goodnight silver"]

    def test_persona_active_handles_unset_fields(self, tmp_personas_dir, args_factory):
        """Persona without wake/dismiss config still emits persona_active —
        with empty lists. Browser will simply never match anything."""
        f = _seed(tmp_personas_dir, _persona_dict(wake=None, dismiss=None))
        play = PlayAIdes(args_factory(f))
        play._handle_incarnation_message({
            "type": "status",
            "payload": {"state": "model_loaded", "name": "Silver.vrm"},
        })
        cmds = play.incarnation_server.commands
        active = [(c, p) for c, p in cmds if c == "persona_active"]
        assert len(active) == 1
        _, payload = active[0]
        assert payload["wake_words"] == []
        assert payload["dismiss_words"] == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_emits_persona_active|test_persona_active_handles)" | head
```

Expected: 2 failures (no `persona_active` ever gets sent today).

- [ ] **Step 3: Add the broadcast in `_handle_incarnation_message`**

In `playAIdes.py`, find the `state == "model_loaded"` branch (currently the last `if` inside the `state == ...` chain — invokes `self.load_default_animations()`). Replace just that branch:

```python
            if state == "model_loaded":
                # Push the active persona's matching config to the browser
                # so it can dismiss/wake-gate STT transcripts client-side.
                if self.current_persona:
                    self.incarnation_server.send_command("persona_active", {
                        "name": self.current_persona.name,
                        "wake_words": list(self.current_persona.wake_words or []),
                        "dismiss_words": list(self.current_persona.dismiss_words or []),
                    })
                self.load_default_animations()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `98 passed, 4 deselected` (was 96; +2 new tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_persona_active_emit.py
git commit -m "feat: emit persona_active WS message after model load"
```

---

## Task 3: Pure `transcriptMatcher.js` module + Vitest tests

**Files:**
- Create: `incarnation/src/transcriptMatcher.js`
- Test: `incarnation/src/transcriptMatcher.test.js`

Pure module. One exported function: `matchPhrase(transcript, phrases) → {matched, phrase, residual}`. Case-insensitive substring; longest-first to prevent shorter aliases winning over longer ones; whitespace-normalised residual.

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/transcriptMatcher.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { matchPhrase } from './transcriptMatcher.js';

describe('matchPhrase', () => {
    it('returns no match for empty transcript', () => {
        const r = matchPhrase('', ['hey silver']);
        expect(r.matched).toBe(false);
        expect(r.phrase).toBe(null);
        expect(r.residual).toBe('');
    });

    it('returns no match for null/empty phrases', () => {
        expect(matchPhrase('hello', null).matched).toBe(false);
        expect(matchPhrase('hello', []).matched).toBe(false);
        expect(matchPhrase('hello', null).residual).toBe('hello');
    });

    it('matches case-insensitively and reports the matched phrase lowercased', () => {
        const r = matchPhrase('Hey Silver, what time is it?', ['hey silver']);
        expect(r.matched).toBe(true);
        expect(r.phrase).toBe('hey silver');
    });

    it('strips the matched phrase from residual and trims whitespace', () => {
        const r = matchPhrase('Hey Silver, what time is it?', ['hey silver']);
        expect(r.residual).toBe(', what time is it?');
    });

    it('returns empty residual when transcript IS the wake word', () => {
        const r = matchPhrase('Silver', ['silver']);
        expect(r.matched).toBe(true);
        expect(r.residual).toBe('');
    });

    it('matches the LONGEST phrase first to avoid shorter alias winning', () => {
        // If "silver" matched first, residual would be "hey , how are you"; we want
        // "hey silver" to win and residual to be "how are you" (with trailing comma stripped).
        const r = matchPhrase('Hey Silver, how are you', ['silver', 'hey silver']);
        expect(r.matched).toBe(true);
        expect(r.phrase).toBe('hey silver');
        expect(r.residual).toBe(', how are you');
    });

    it('matches Japanese substrings without tokenization', () => {
        const r = matchPhrase('こんにちはシルバー、今何時ですか', ['シルバー']);
        expect(r.matched).toBe(true);
        expect(r.phrase).toBe('シルバー');
        expect(r.residual).toBe('こんにちは、今何時ですか');
    });

    it('returns no match when no phrase appears in transcript', () => {
        const r = matchPhrase('hello there', ['hey silver', 'goodnight']);
        expect(r.matched).toBe(false);
        expect(r.phrase).toBe(null);
        expect(r.residual).toBe('hello there');
    });

    it('collapses internal whitespace runs in residual', () => {
        const r = matchPhrase('Hey   Silver   what  time', ['silver']);
        expect(r.matched).toBe(true);
        expect(r.residual).toBe('Hey what time');
    });

    it('treats undefined phrases array safely', () => {
        const r = matchPhrase('hello', undefined);
        expect(r.matched).toBe(false);
        expect(r.residual).toBe('hello');
    });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -10
```

Expected: 10 failures with module-not-found.

- [ ] **Step 3: Create `incarnation/src/transcriptMatcher.js`**

```js
/**
 * transcriptMatcher.js — case-insensitive substring matcher for
 * wake-word and dismiss-word detection.
 *
 * No tokenization, no language-aware splitting — Whisper produces
 * mixed EN/JP transcripts that work fine as raw substrings since
 * we lowercase them and the wake/dismiss config is also case-insensitive.
 *
 * Longest-first ordering ensures that e.g. ["silver", "hey silver"]
 * matches "Hey Silver" against "hey silver" (the longer alias) rather
 * than "silver" — preserving more of the residual.
 */

/**
 * Test whether a transcript contains any of the given phrases.
 *
 * @param {string} transcript
 * @param {string[]|null|undefined} phrases
 * @returns {{matched: boolean, phrase: string|null, residual: string}}
 *   matched  — true if any phrase appears in transcript
 *   phrase   — the matched phrase (lowercased), or null
 *   residual — transcript with the matched phrase removed and internal
 *              whitespace collapsed; equals the input transcript when
 *              no phrase matched
 */
export function matchPhrase(transcript, phrases) {
    const safeTranscript = transcript || '';
    if (!phrases || !Array.isArray(phrases) || phrases.length === 0) {
        return { matched: false, phrase: null, residual: safeTranscript };
    }
    if (!safeTranscript) {
        return { matched: false, phrase: null, residual: '' };
    }
    const lower = safeTranscript.toLowerCase();
    // Longest-first: avoids "silver" winning when "hey silver" is also configured.
    const sorted = phrases
        .filter((p) => typeof p === 'string' && p.length > 0)
        .map((p) => p.toLowerCase())
        .sort((a, b) => b.length - a.length);

    for (const phrase of sorted) {
        const idx = lower.indexOf(phrase);
        if (idx !== -1) {
            const residual = (
                safeTranscript.slice(0, idx) +
                safeTranscript.slice(idx + phrase.length)
            )
                .replace(/\s+/g, ' ')
                .trim();
            return { matched: true, phrase, residual };
        }
    }
    return { matched: false, phrase: null, residual: safeTranscript };
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 5 passed (5) / Tests 60 passed (60)` (was 50, +10 matcher tests).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/transcriptMatcher.js incarnation/src/transcriptMatcher.test.js
git commit -m "feat(viewer): transcriptMatcher for wake/dismiss substring matching"
```

---

## Task 4: Wire `persona_active` into the orchestrator

**Files:**
- Modify: `incarnation/src/viewer.js`

The browser now caches the active persona's matching config when the server pushes `persona_active`. Also wire the persona name into the nameplate.

- [ ] **Step 1: Add the active-persona state holder + listener**

In `incarnation/src/viewer.js`, just below the existing `let lastUserUtterance = '';` line (added in Phase 2), add:

```js
// Active persona's matching config — populated by the server-pushed
// `persona_active` WS message after the avatar finishes loading.
let activePersona = { name: '', wake_words: [], dismiss_words: [] };
```

Then, alongside the other `connection.addEventListener(...)` calls (after `'stop_lip_sync'`, before the voice handlers), add:

```js
connection.addEventListener('persona_active', (e) => {
    activePersona = {
        name: e.detail?.name || '',
        wake_words: Array.isArray(e.detail?.wake_words) ? e.detail.wake_words : [],
        dismiss_words: Array.isArray(e.detail?.dismiss_words) ? e.detail.dismiss_words : [],
    };
    overlays.setPersonaName(activePersona.name);
    console.log('[viewer] persona_active:', activePersona);
});
```

- [ ] **Step 2: Manual verification**

After Task 5 lands the orchestrator gets the matching wired in. For now, just confirm:

- `make test-js 2>&1 | tail -10` still shows `60 passed (60)`.
- `node --check incarnation/src/viewer.js` reports no syntax errors. (If `node` isn't on host, use `make js-shell` and run inside the container.)

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "feat(viewer): receive persona_active and bind to nameplate"
```

---

## Task 5: Wire dismiss + wake matching into the `voiceend` handler

**Files:**
- Modify: `incarnation/src/viewer.js`

The voiceend handler currently sends every transcript as `user_input`. Phase 3 adds the dismiss-then-wake gate.

- [ ] **Step 1: Add the matchPhrase import**

In `incarnation/src/viewer.js`, alongside the existing imports (after `import { SttClient } from './sttClient.js';`), add:

```js
import { matchPhrase } from './transcriptMatcher.js';
```

- [ ] **Step 2: Replace the `voiceend` handler**

In `incarnation/src/viewer.js`, find the existing `audioCapture.addEventListener('voiceend', async (e) => { ... });` block. Replace its body with:

```js
audioCapture.addEventListener('voiceend', async (e) => {
    const wasListening = stateMachine.current === State.LISTENING;
    if (wasListening) {
        safeTransition(State.THINKING, { lastUtterance: '…' });
    }
    try {
        const { text } = await stt.transcribe(e.detail.blob);
        const transcript = (text || '').trim();
        if (!transcript) {
            if (wasListening) safeTransition(State.AMBIENT);
            return;
        }

        // 1. Dismiss check — always runs, regardless of activation mode.
        if (activePersona.dismiss_words.length) {
            const dismiss = matchPhrase(transcript, activePersona.dismiss_words);
            if (dismiss.matched) {
                console.log('[viewer] dismiss matched:', dismiss.phrase);
                // Already-EMPTY → safeTransition will warn and no-op (allowed).
                safeTransition(State.EMPTY);
                return;
            }
        }

        // 2. Wake-word gate — applied in `wake` mode OR when in EMPTY.
        let userInput = transcript;
        const inEmpty = stateMachine.current === State.EMPTY;
        const needsWake = config.activation === 'wake' || inEmpty;

        if (needsWake) {
            const wake = matchPhrase(transcript, activePersona.wake_words);
            if (!wake.matched) {
                console.log('[viewer] wake-mode drop, no wake-word in:', transcript);
                if (wasListening || stateMachine.current === State.THINKING) {
                    safeTransition(State.AMBIENT);
                }
                return;
            }
            userInput = wake.residual;
            console.log('[viewer] wake matched:', wake.phrase, '→ residual:', userInput);
        }

        // 3. Re-summon from EMPTY: state-only transition; intro-anim replay
        // is Phase 4 work.
        if (inEmpty) {
            safeTransition(State.INTRO);
            safeTransition(State.AMBIENT);
        }

        // 4. If wake-only utterance (no residual), just acknowledge — stay AMBIENT.
        if (!userInput) {
            return;
        }

        // 5. Update THINKING meta with the actual user message and forward.
        if (stateMachine.current === State.THINKING) {
            stateMachine.dispatchEvent(new CustomEvent('change', {
                detail: {
                    prev: State.THINKING, next: State.THINKING,
                    prevMeta: { lastUtterance: '…' },
                    meta: { lastUtterance: userInput },
                },
            }));
        }
        lastUserUtterance = userInput;
        connection.send('user_input', { text: userInput });
    } catch (err) {
        console.error('[viewer] STT failed:', err);
        if (stateMachine.current === State.LISTENING || stateMachine.current === State.THINKING) {
            safeTransition(State.AMBIENT);
        }
    }
});
```

- [ ] **Step 3: Manual verification (deferred to Task 9 smoke)**

```bash
make test-js 2>&1 | tail -10
```

Expected: still `60 passed`. The orchestrator isn't unit-tested.

- [ ] **Step 4: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "feat(viewer): dismiss-then-wake gate in voiceend handler"
```

---

## Task 6: EMPTY state visuals — canvas fade-out, nameplate hidden

**Files:**
- Modify: `incarnation/src/viewerOverlays.js`
- Modify: `incarnation/styles/viewer.css`

The state machine already supports EMPTY transitions; the overlay layer needs to mark it on the body so CSS can fade the canvas + hide the nameplate.

- [ ] **Step 1: Add body-level state attribute in `_onStateChange`**

In `incarnation/src/viewerOverlays.js`, find the existing `_onStateChange({ next, meta })` method. Add a single line at the top of the method body, before the existing mic/subtitle logic:

```js
    _onStateChange({ next, meta }) {
        // Body-level state attribute drives canvas + nameplate visuals via CSS.
        document.body.dataset.viewerState = next;

        // Mic indicator: color/animation per state. CSS owns the actual
        // styling — we just attach a class.
        // … existing logic unchanged …
```

(Keep all existing code below it intact.)

- [ ] **Step 2: Add the EMPTY-state CSS rules**

In `incarnation/styles/viewer.css`, find the existing `.viewer-strip { ... }` block (or any anchor near the canvas styling). Below the existing `#viewer { ... }` rule, add:

```css
/* ── EMPTY state visuals (dismiss / no persona) ──────────── */
/* Smooth opacity transition for both fade-out (dismiss) and
   fade-in (re-summon via wake word). */
#viewer { transition: opacity 250ms ease; }

body[data-viewer-state="EMPTY"] #viewer {
    opacity: 0;
}

body[data-viewer-state="EMPTY"] .nameplate {
    opacity: 0;
    transition: opacity 200ms ease;
}
```

- [ ] **Step 3: Manual verification (deferred to Task 9 smoke)**

`make test-js 2>&1 | tail -10` should still show `60 passed`. No JS test changes.

- [ ] **Step 4: Commit**

```bash
git add incarnation/src/viewerOverlays.js incarnation/styles/viewer.css
git commit -m "feat(viewer): EMPTY state fades canvas + hides nameplate"
```

---

## Task 7: Allow voicestart from EMPTY (audio-only, no UI transition)

**Files:**
- Modify: `incarnation/src/viewer.js`

In Phase 2 the voicestart handler tries to transition AMBIENT/EMPTY → LISTENING. But `viewerState.js` only allows `EMPTY → INTRO`, so when the user speaks while dismissed, the safeTransition warns + drops the utterance. We want to keep recording audio in EMPTY (so the wake word can be detected) but NOT change UI state until the wake word is matched.

- [ ] **Step 1: Replace the `voicestart` listener**

In `incarnation/src/viewer.js`, find:

```js
audioCapture.addEventListener('voicestart', () => {
    if (stateMachine.current === State.AMBIENT || stateMachine.current === State.EMPTY) {
        safeTransition(State.LISTENING);
    }
});
```

Replace with:

```js
audioCapture.addEventListener('voicestart', () => {
    // AMBIENT → LISTENING: normal active-conversation flow.
    // EMPTY: no UI transition (state machine forbids EMPTY → LISTENING by
    // design); the audio is still being recorded and will be sent to STT
    // on voiceend. The voiceend handler then checks for the wake word
    // before re-summoning the persona.
    if (stateMachine.current === State.AMBIENT) {
        safeTransition(State.LISTENING);
    }
});
```

- [ ] **Step 2: Manual verification**

`make test-js 2>&1 | tail -10` should still show `60 passed`.

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "fix(viewer): voicestart in EMPTY records audio without state change"
```

---

## Task 8: Add wake/dismiss config to Silver's persona

**Files:**
- Modify: `personas/silver/persona.json` (untracked — local edit only)

Silver is the canonical test persona. Give her real wake/dismiss words so the user can smoke-test the new flow.

- [ ] **Step 1: Edit `personas/silver/persona.json`**

In Silver's persona.json, alongside the existing top-level fields (`name`, `back_ground`, `psyche`, `gender`, `language`, `avatar`, `persona_voice`, `memories`), add three new fields. Result should look like:

```json
{
  "name": "Silver",
  "back_ground": "...",
  "psyche": { "..." : "..." },
  "gender": "Female",
  "language": "English",
  "avatar": { "..." : "..." },
  "persona_voice": { "..." : "..." },
  "memories": null,
  "wake_words": ["hey silver", "silver"],
  "dismiss_words": ["goodnight silver", "good night silver", "bye silver"],
  "is_default": true
}
```

(Don't edit the existing fields — just append the three new ones before or after `memories`.)

- [ ] **Step 2: Smoke-verify the JSON parses**

```bash
python3 -c "import json; p = json.load(open('personas/silver/persona.json')); print(p['wake_words'], p['dismiss_words'])"
```

Expected output: `['hey silver', 'silver'] ['goodnight silver', 'good night silver', 'bye silver']`.

- [ ] **Step 3: No commit**

Silver's persona.json is untracked (local-only file). Nothing to commit.

---

## Task 9: End-to-end smoke + final review

**Files:**
- None — verification only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `98 passed, 4 deselected`.

- [ ] **Step 2: JS tests still green**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 5 passed (5) / Tests 60 passed (60)`.

- [ ] **Step 3: Live voice round-trip**

In separate terminals:

```bash
# Terminal 1 — Whisper container exposed to the host:
make whisper
```

```bash
# Terminal 2 — Python backend:
python main.py --persona personas/silver/persona.json --use_avatar
```

```bash
# Terminal 3 — Vite dev server:
npm --prefix incarnation run dev
```

Open `http://localhost:5173/?activation=wake` (note: **wake** mode is the Phase 3 default — explicit here for clarity). Click anywhere, grant mic permission, then test the four scenarios:

**Scenario A — wake-gated conversation:**

1. **AMBIENT** — say something casual: *"What time is it?"* → mic dot pulses through LISTENING/THINKING, then drops back to AMBIENT (no reply). Console logs `[viewer] wake-mode drop, no wake-word in: …`.
2. **AMBIENT** — say: *"Hey Silver, what's the weather?"* → mic dot to LISTENING (crimson), then THINKING (gold spin) showing "what's the weather?" in greyed italic, then SPEAKING with Silver's reply. Console logs `[viewer] wake matched: hey silver → residual: what's the weather?`.

**Scenario B — wake-only acknowledgement:**

3. After AMBIENT — say just *"Silver"* → console logs match, residual is empty, mic dot stays at AMBIENT. No assistant reply.

**Scenario C — dismiss + re-summon:**

4. After a chat — say *"Goodnight Silver"* → canvas fades to black over ~250ms, nameplate hides, mic dot goes to state-empty (dim-gold pulse). Subtitle band fades out. Console logs `[viewer] dismiss matched: goodnight silver`.
5. Say *"Hey Silver"* while dismissed → canvas fades back in, model reappears (still in same pose since intro-replay is Phase 4), mic dot returns to dim-gold pulse (AMBIENT).

**Scenario D — continuous mode (sanity):**

6. Reload at `http://localhost:5173/?activation=continuous`. Say *"What time is it?"* without a wake word → goes through to user_input + reply. Dismiss still works: *"Goodnight Silver"* fades the canvas. Wake still required from EMPTY: re-summon via *"Hey Silver"*.

If any step fails, check the DevTools Console for `[viewer] →` state-transition logs and the WS Network tab for `persona_active` payload + `user_input` frames.

- [ ] **Step 4: Self-review against spec §10 Phase 3 row**

Confirm each Phase 3 bullet maps to a task above:

- "`wake_words` and `dismiss_words` fields on personas" → Task 1
- "Browser switches activation modes (`wake` vs `continuous`) per `?activation=`" → Existing Phase 1 config + Task 5 conditional logic
- "In wake-word mode, only the **currently-active** persona's wake words are checked" → Task 5 (uses `activePersona.wake_words` only)
- "Dismiss words always work and transition to `EMPTY`" → Task 5 (dismiss runs before mode check) + Task 6 (visuals)
- "Cross-persona swap deferred to phase 4" → confirmed by what's NOT here

- [ ] **Step 5: Final consistency check**

- `matchPhrase` exported from `transcriptMatcher.js`, imported by `viewer.js`. Same name, same shape across files.
- `activePersona.wake_words` / `dismiss_words` shapes match the server's `persona_active` payload (lists of strings).
- `is_default` field present on the schema; not yet wired (deferred to Phase 4 per the simplifications block).
- `body[data-viewer-state="EMPTY"]` selector matches the value `viewerOverlays` writes (`document.body.dataset.viewerState = next` with `next` being the State enum string `"EMPTY"`, `"AMBIENT"`, etc. — verify the casing matches).

- [ ] **Step 6: No commit (process marker)**

---

## Self-review checklist (run before marking phase 3 done)

- [ ] **Spec coverage** — every bullet in spec §10 Phase 3 row maps to a task. Checked.
- [ ] **No placeholders** — search the plan for `TBD`, `TODO`, `FIXME`. None.
- [ ] **Type / name consistency**:
  - `wake_words`, `dismiss_words` — exact snake_case across `persona.py`, server payload, `persona_active` event, `activePersona` object in `viewer.js`.
  - `matchPhrase` — same import name in `viewer.js` as exported from `transcriptMatcher.js`.
  - `data-viewer-state` — written by `viewerOverlays.js`, read by selectors in `viewer.css` (`body[data-viewer-state="EMPTY"]`).
  - `persona_active` — type literal on both sides of the WS.
- [ ] **Phase boundaries respected** — no `set_active_persona`, no cross-persona wake-word matching, no `persona_id` on `user_input`, no intro-animation replay on re-summon. All deferred to Phase 4.
- [ ] **Whisper-down behavior** — same as Phase 2 (catch + bounce to AMBIENT). No new behavior here.
