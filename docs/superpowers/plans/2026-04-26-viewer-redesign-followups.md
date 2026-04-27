# Viewer Redesign — Post-Phase-5 Polish & Follow-ups

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address the deferred minor items from the Phase 4 and Phase 5 final-review code reviewers — small polish + correctness improvements that didn't block merge but are worth landing before the codebase grows further.

**Architecture:** No new subsystems. Each task is a focused fix to existing code (transcriptModel, viewer.js, scene.js, playAIdes.py). All but the asyncio.Lock task are <20 lines of code.

**Tech Stack:** Same as Phases 1–5 (Pydantic v2, FastAPI, Vanilla JS + Vitest, Three.js).

**Branch:** create `polish_followups` from `main` (no worktrees per project preference). Current `main` tip is the commit immediately after this plan lands.

**Reference reviews:** Phase 4 final review (in session history; key items: I-1 asyncio.Lock, I-2 set_persona voice config, I-3 tempfile leak). Phase 5 final review (key items: #5–#11 below).

## Conventions for this plan

- **Backend (Python)** uses TDD via `make test`.
- **Frontend pure modules** use Vitest in Docker (`make test-js`); DOM-coupled wiring uses manual smoke.
- Each task ends with a commit. Conventional Commits prefixes (`fix:`, `refactor:`, `test:`).
- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.

## Baseline going in

- Branch: `main` at HEAD = `639b901` (Phase 5 polish fix) — verify with `git log --oneline -1`.
- Tests: `make test` → 136 passed, 4 deselected. `make test-js` → 86 passed.
- All 5 phases (1–5) shipped and merged to `origin/main`.

---

## Task 1: tempfile leak on `os.replace` failure (Phase 4 I-3)

**Files:**
- Modify: `playAIdes.py` (`_save_history`)
- Test: `tests/unit/test_chat_history.py` (extend existing test class)

If `os.replace` raises mid-write (disk full, EXDEV across filesystems, etc.), the `.chat_history.*.json.tmp` sibling file stays on disk. Repeated failures accumulate orphan tempfiles. Wrap in `try/except`, unlink the tempfile on error, then re-raise.

- [ ] **Step 1: Extend the failing-write test in `tests/unit/test_chat_history.py`**

In `TestChatHistoryPersistence`, find `test_save_history_is_atomic` (which monkeypatches `os.replace` to fail). After the existing assertions inside that test (which verify the original file is intact), add:

```python
        # Tempfile cleanup: no orphan .chat_history.*.json.tmp left behind
        # in the persona dir after the failed write.
        leftovers = list((tmp_personas_dir / pid).glob(".chat_history.*.json.tmp"))
        assert leftovers == [], f"orphan tempfile(s): {leftovers}"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "FAILED|test_save_history_is_atomic" | head
```

Expected: failure with `assert [PosixPath('.../.chat_history.*.json.tmp')] == []` or similar.

- [ ] **Step 3: Add try/except cleanup to `_save_history`**

In `playAIdes.py`, find `_save_history` (around line 320). Replace the body:

```python
    def _save_history(self, persona_id: str):
        """Persist a persona's chat history atomically via tempfile + os.replace.
        If os.replace raises, the original file is left intact AND the
        sibling tempfile is unlinked (no orphan accumulation)."""
        import tempfile
        path = self._history_path(persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        history = self.chat_histories.get(persona_id, [])
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(path.parent), delete=False,
            prefix=".chat_history.", suffix=".json.tmp",
        ) as tf:
            json.dump(history, tf, ensure_ascii=False, indent=2)
            tmp_path = tf.name
        try:
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
make test 2>&1 | tail -3
```

Expected: `136 passed, 4 deselected` (test count unchanged — extended an existing test).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/unit/test_chat_history.py
git commit -m "fix: clean up sibling tempfile when _save_history's os.replace fails"
```

---

## Task 2: `transcriptModel.clear()` resets scroll flag (Phase 5 #5)

**Files:**
- Modify: `incarnation/src/transcriptModel.js`
- Test: `incarnation/src/transcriptModel.test.js` (extend)

`replaceAll` already resets `_userScrolledUp = false`; `clear` doesn't. Asymmetric. Empty list has nothing to scroll past, so the flag should also reset on `clear`.

- [ ] **Step 1: Add the failing test**

In `incarnation/src/transcriptModel.test.js`, append to the existing `describe('TranscriptModel', ...)` block:

```js
    it('clear resets the user-scrolled-up flag (no content to be past)', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'a' });
        t.setUserScrolledUp(true);
        t.clear();
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test-js 2>&1 | tail -10
```

Expected: 1 failure on the new test.

- [ ] **Step 3: Reset the flag inside `clear`**

In `incarnation/src/transcriptModel.js`, find the `clear()` method:

```js
    clear() {
        this._messages = [];
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'clear' },
        }));
    }
```

Replace with:

```js
    clear() {
        this._messages = [];
        // No content to be "scrolled past" — fresh start at bottom.
        this._userScrolledUp = false;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'clear' },
        }));
    }
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 8 passed (8) / Tests 87 passed (87)` (was 86; +1 new).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/transcriptModel.js incarnation/src/transcriptModel.test.js
git commit -m "fix(viewer): TranscriptModel.clear resets userScrolledUp flag"
```

---

## Task 3: Extract `getActivePersonaId()` helper (Phase 5 #6)

**Files:**
- Modify: `incarnation/src/viewer.js`

The active-persona-id-from-name lookup `personasRegistry.all().find((p) => p.name === activePersona.name)?.id || null` is duplicated in two places (the chatPanel.submit handler and the voiceend cross-persona swap branch). Extract to a single helper so a future "store activePersona.id directly" refactor only touches one place.

- [ ] **Step 1: Locate the two duplicated lookups**

```bash
grep -n "personasRegistry.all()" incarnation/src/viewer.js
```

Expected: 2 hits, both with the same `.find((p) => p.name === activePersona.name)?.id` shape.

- [ ] **Step 2: Add the helper near the top of `viewer.js`**

Just below the `safeTransition` function (around line 88), add:

```js
/** Resolve the active persona's id from the registry by name match.
 *  Returns null if the registry isn't populated yet or the active
 *  persona's name doesn't match any known id. */
function getActivePersonaId() {
    return personasRegistry.all()
        .find((p) => p.name === activePersona.name)?.id || null;
}
```

- [ ] **Step 3: Replace both call sites**

Find the chatPanel.submit handler (~line 60). Replace:

```js
    const activeId = personasRegistry.all()
        .find((p) => p.name === activePersona.name)?.id || null;
    connection.send('user_input', activeId
        ? { text, persona_id: activeId }
        : { text });
```

with:

```js
    const activeId = getActivePersonaId();
    connection.send('user_input', activeId
        ? { text, persona_id: activeId }
        : { text });
```

Find the voiceend cross-persona swap branch (~line 377). Replace the analogous block in the same way.

- [ ] **Step 4: Verify**

```bash
make test-js 2>&1 | tail -5
```

Expected: still 87 passed.

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "refactor(viewer): extract getActivePersonaId helper"
```

---

## Task 4: `loadHDRIBackground` reuses extension classifier (Phase 5 #8)

**Files:**
- Modify: `incarnation/src/sceneBackgrounds.js`
- Modify: `incarnation/src/sceneBackgrounds.test.js`
- Modify: `incarnation/src/scene.js`

Currently `loadHDRIBackground` in `scene.js` does its own URL-stripping (`url.toLowerCase().split('?')[0].endsWith('.exr')`) instead of reusing `sceneBackgrounds.js`. Extract a tiny `isExrUrl(url)` helper there so the URL-stripping logic lives in one module.

- [ ] **Step 1: Add the failing tests**

In `incarnation/src/sceneBackgrounds.test.js`, append:

```js
import { isExrUrl } from './sceneBackgrounds.js';

describe('isExrUrl', () => {
    it('returns true for .exr (any case) with optional query/fragment', () => {
        expect(isExrUrl('panorama.exr')).toBe(true);
        expect(isExrUrl('PANO.EXR')).toBe(true);
        expect(isExrUrl('foo.exr?v=2')).toBe(true);
        expect(isExrUrl('foo.exr#bar')).toBe(true);
    });

    it('returns false for .hdr and other extensions', () => {
        expect(isExrUrl('panorama.hdr')).toBe(false);
        expect(isExrUrl('foo.jpg')).toBe(false);
        expect(isExrUrl('')).toBe(false);
        expect(isExrUrl(null)).toBe(false);
    });
});
```

(The existing top-of-file import becomes `import { detectBackgroundType, isExrUrl } from './sceneBackgrounds.js';` if you prefer one import; otherwise leave the existing line alone and add the new line above the new `describe`.)

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -10
```

Expected: 2 failures with module-export error.

- [ ] **Step 3: Export `isExrUrl` from `sceneBackgrounds.js`**

In `incarnation/src/sceneBackgrounds.js`, append below `detectBackgroundType`:

```js
/**
 * True iff the URL points to an OpenEXR file. Used by loadHDRIBackground
 * to pick between RGBELoader and EXRLoader.
 */
export function isExrUrl(url) {
    if (!url || typeof url !== 'string') return false;
    return url.split('?')[0].split('#')[0].toLowerCase().endsWith('.exr');
}
```

- [ ] **Step 4: Use the helper in `scene.js`**

Find the existing import line `import { detectBackgroundType } from './sceneBackgrounds.js';` and update to:

```js
import { detectBackgroundType, isExrUrl } from './sceneBackgrounds.js';
```

Then in `loadHDRIBackground`, replace:

```js
    const isExr = url.toLowerCase().split('?')[0].endsWith('.exr');
```

with:

```js
    const isExr = isExrUrl(url);
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 8 passed (8) / Tests 89 passed (89)` (was 87; +2 new).

- [ ] **Step 6: Commit**

```bash
git add incarnation/src/sceneBackgrounds.js incarnation/src/sceneBackgrounds.test.js incarnation/src/scene.js
git commit -m "refactor(viewer): isExrUrl helper deduplicates HDR/EXR check"
```

---

## Task 5: `history_loaded` rehydrate guards on `activePersona.name` (Phase 5 #9)

**Files:**
- Modify: `incarnation/src/viewer.js`

If `history_loaded` arrives before `persona_active` (server-side broadcast ordering quirk), `activePersona.name` is `''` and assistant transcript lines fall through to the literal label "Persona". Defer the rehydrate when activePersona isn't set yet, then replay the latest pending history once persona_active arrives.

- [ ] **Step 1: Add a pending-history holder + flush helper**

In `incarnation/src/viewer.js`, just below the existing `let pendingAssistantText = '';` declaration, add:

```js
// Holds the most recent history_loaded payload until persona_active has
// landed and we know the persona's name to tag assistant lines with.
let pendingHistory = null;

function _flushPendingHistory() {
    if (!pendingHistory || !activePersona.name) return;
    const tagged = pendingHistory.map((m) => ({
        ...m,
        persona_name: activePersona.name,
    }));
    transcriptModel.replaceAll(tagged);
    console.log('[viewer] transcript rehydrated, n=', tagged.length);
    pendingHistory = null;
}
```

- [ ] **Step 2: Update the `history_loaded` handler to use the buffer**

Find the existing `connection.addEventListener('history_loaded', ...)` block. Replace with:

```js
connection.addEventListener('history_loaded', (e) => {
    const history = Array.isArray(e.detail?.history) ? e.detail.history : [];
    pendingHistory = history;
    _flushPendingHistory();
});
```

- [ ] **Step 3: Flush from the `persona_active` handler too**

In the existing `connection.addEventListener('persona_active', (e) => { ... })` block, after `chatPanel.setPersona(...)`, add:

```js
    _flushPendingHistory();
```

- [ ] **Step 4: Verify**

```bash
make test-js 2>&1 | tail -5
```

Expected: still 89 passed.

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "fix(viewer): defer history rehydrate until persona_active arrives"
```

---

## Task 6: Integration test for spawn_point/camera_target broadcast (Phase 5 #11)

**Files:**
- Test: `tests/integration/test_set_active_persona_ws.py` (extend `TestSetActivePersonaWS`)

The Phase 5 schema fields are tested at the Pydantic layer, but no test verifies the WS payload actually carries them. Adds a single assertion to the existing swap-emits-load_model test.

- [ ] **Step 1: Extend the existing emits test**

In `tests/integration/test_set_active_persona_ws.py`, locate `test_emits_unload_then_load_model_on_swap`. After the existing assertions, add a new test method below it:

```python
    def test_load_model_payload_carries_spawn_and_camera(self, play, tmp_personas_dir):
        """load_model payload includes the persona's spawn_point and
        camera_target so the frontend can position the VRM + camera."""
        import json
        # Seed Rin with explicit spawn + camera_target.
        rin_dir = tmp_personas_dir / "rin"
        rin_dir.mkdir(exist_ok=True)
        (rin_dir / "persona.json").write_text(json.dumps({
            "name": "Rin",
            "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female",
            "language": "English",
            "avatar": {
                "model_url": "rin.vrm",
                "spawn_point": [1.0, 0.0, -2.0],
                "camera_target": [1.0, 1.1, -2.0],
            },
        }))
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        load = [(c, p) for c, p in cmds if c == "load_model"]
        assert len(load) == 1
        _, payload = load[0]
        assert payload["url"] == "rin.vrm"
        assert payload["spawn_point"] == [1.0, 0.0, -2.0]
        assert payload["camera_target"] == [1.0, 1.1, -2.0]
```

- [ ] **Step 2: Run test to confirm it passes (already-implemented behavior)**

```bash
make test 2>&1 | tail -3
```

Expected: `137 passed, 4 deselected` (was 136; +1 new). Note: this test should pass on first run since Phase 5 commit `c3eb33e` already plumbs the fields. It's a regression guard.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_set_active_persona_ws.py
git commit -m "test: assert load_model payload carries spawn_point + camera_target"
```

---

## Task 7: `set_persona` defends against missing voice config (Phase 4 I-2)

**Files:**
- Modify: `playAIdes.py` (`chat()` voice-dispatch branch)
- Test: `tests/integration/test_set_active_persona_ws.py` (extend)

If `set_persona` swaps to a persona without a valid `persona_voice.speaker_uuid` AND `args.use_voice=True`, the existing `start_lip_sync` URL construction in `chat()` will reference `self.current_persona.persona_voice.speaker_uuid` and crash with AttributeError on None. Guard the lip-sync emit on `persona_voice and persona_voice.speaker_uuid`.

- [ ] **Step 1: Add the failing test**

In `tests/integration/test_set_active_persona_ws.py`, append to `TestSetActivePersonaWS`:

```python
    def test_chat_with_no_voice_config_does_not_crash(self, tmp_personas_dir, fake_tts, no_incarnation):
        """A persona without persona_voice should not crash chat() when
        use_voice=True; the lip-sync emit is gracefully skipped."""
        from playAIdes import PlayAIdes, PlayAIdesArgs
        from model_interfaces import MockLLM
        # Seed a persona with no persona_voice block.
        pdir = tmp_personas_dir / "voiceless"
        pdir.mkdir(exist_ok=True)
        (pdir / "persona.json").write_text(json.dumps({
            "name": "Voiceless",
            "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female",
            "language": "English",
            "avatar": {"model_url": "x.vrm"},
            # NB: no persona_voice key
        }))
        args = PlayAIdesArgs(
            persona=[str(pdir / "persona.json")],
            generate_voice=False,
            use_voice=True,            # voice path enabled
            use_avatar=True,
            generate_avatar=False,
            llm=MockLLM(), tts=fake_tts,
        )
        play = PlayAIdes(args)
        # Must not raise.
        play.chat("hi")
        cmds = play.incarnation_server.commands
        # assistant_message still flows; start_lip_sync is gracefully skipped.
        assert any(c == "assistant_message" for c, _ in cmds)
        assert not any(c == "start_lip_sync" for c, _ in cmds)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "FAILED|test_chat_with_no_voice_config" | head
```

Expected: AttributeError on None during `chat()` — `'NoneType' object has no attribute 'speaker_uuid'` or similar.

- [ ] **Step 3: Guard the lip-sync emit**

In `playAIdes.py`, find the `chat()` method's voice-dispatch block (around line 700). The current shape:

```python
        if self.args.use_voice:
            if self.args.use_avatar and self.incarnation_server:
                import urllib.parse
                safe_text = urllib.parse.quote(response)
                proxy_url = f"http://localhost:8765/api/tts/proxy?text={safe_text}&speaker_id={self.current_persona.persona_voice.speaker_uuid}"
                ...
```

Insert a guard right after `if self.args.use_voice:`:

```python
        if self.args.use_voice:
            if not (self.current_persona.persona_voice
                    and self.current_persona.persona_voice.speaker_uuid):
                logger.warning("Persona %s has no voice config; skipping lip_sync",
                               self.current_persona.name)
            elif self.args.use_avatar and self.incarnation_server:
                # … existing avatar+TTS proxy code unchanged …
            else:
                # … existing direct-speak code unchanged …
```

(Be careful to preserve the existing `if self.args.use_avatar and self.incarnation_server:` and `else:` branches inside the `use_voice` block; only the outer guard is new.)

- [ ] **Step 4: Run test to confirm it passes**

```bash
make test 2>&1 | tail -3
```

Expected: `138 passed, 4 deselected` (was 137; +1 new).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_set_active_persona_ws.py
git commit -m "fix: chat() skips lip_sync gracefully when persona has no voice config"
```

---

## Task 8: End-of-pass smoke + final review

**Files:** none — verification only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `138 passed, 4 deselected`.

- [ ] **Step 2: Frontend tests still green**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 8 passed (8) / Tests 89 passed (89)`.

- [ ] **Step 3: Self-review**

- All 7 deferred items from Phase 4 + 5 final reviews now have either tests, fixes, or a documented decision to skip.
- Phase 4 #7 (`_render` perf concern, speculative until profiling shows thrash) — DELIBERATELY SKIPPED. Document as "no action needed at v1 scale" if asked.
- Phase 4 I-1 (`asyncio.Lock` for last-writer-wins) — DELIBERATELY SKIPPED. The synchronous `chat()` + FastAPI single-threaded event loop don't actually race in practice. Revisit if multi-TV concurrent input becomes a real workload.

- [ ] **Step 4: No commit (process marker)**

---

## Self-review checklist (run before marking polish phase done)

- [ ] **Coverage** — every Phase 4/5 final-review item has a Task above (or explicit skip-with-reason).
- [ ] **No placeholders** — search for `TBD`, `TODO`, `FIXME`. None.
- [ ] **Type / name consistency** — `getActivePersonaId`, `_flushPendingHistory`, `pendingHistory`, `isExrUrl`, `_save_history` cleanup pattern consistent.
- [ ] **No new features** — every task is a fix or refactor; no scope creep.
- [ ] **Backwards compat preserved** — all changes are additive guards or pure refactors.
