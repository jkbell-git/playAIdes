# Viewer Redesign — Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Runtime persona swap + per-persona memory. A persona is summoned by ANY persona's wake word (cross-persona swap), not just the currently-active one. Each persona has its own LLM chat history persisted to `personas/<id>/chat_history.json`, capped at the most recent 80 turns. The server keeps a binding registry so multiple connected viewers (kitchen TV + bedroom TV) showing the same persona share the same conversation in real time. The diagonal-wipe visual covers the model swap. `is_default` finally has meaning: it's how the browser picks a boot persona when `?persona=` is omitted.

**Architecture:** Backend grows three concerns — (1) `PlayAIdes.set_persona(id)` for runtime swaps, (2) `chat_histories: Dict[persona_id, List[Message]]` with atomic JSON persistence, (3) `incarnation_server` upgrades from single-client (`self.connected_client`) to multi-client + a `Dict[WebSocket, persona_id]` binding registry that routes `assistant_message` only to clients bound to the relevant persona. Frontend grows a `personasRegistry.js` pure module (cache of all personas with `findByWakeWord` / `findDefault`), a tiny `wipeOverlay.js` for the 200 ms red-diagonal animation, and orchestrator wiring that turns a cross-persona wake match into `set_active_persona { id }` and an unload→wipe→load sequence.

**Tech Stack:** Pydantic v2, FastAPI WebSocket, asyncio.Lock for per-persona last-writer-wins, atomic JSON via `tempfile.NamedTemporaryFile` + `os.replace`, pytest, Vanilla JS ES modules + Vitest.

**Branch:** continue on `main` (no worktrees per project preference).

**Reference spec:** `docs/superpowers/specs/2026-04-24-viewer-redesign-design.md` — read §2 (state machine, especially the Persona swap and Intro animation subsections), §3 (Wake-word and dismiss matching, Multi-TV memory model), §6 (full WS message tables, `PlayAIdes.set_persona()` contract, chat history persistence), §7 (`is_default` semantics).

## Conventions for this plan

- **Backend (Python)** uses TDD via `make test`. Whisper-touching tests use `respx`; no live STT in Phase 4.
- **Frontend (JS)** pure modules use Vitest in Docker (`make test-js`). DOM-coupled wiring uses manual browser verification.
- Each task ends with a commit. Conventional Commits prefixes.
- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.

## Phase 4 simplifications (deferred to Phase 5)

- **No chat panel UI yet.** History is loaded server-side and broadcast client-side, but the browser doesn't yet show a transcript pane. Phase 5 adds the right-edge handle + collapsible chat panel that rehydrates from `history_loaded`.
- **Backgrounds tier upgrade is Phase 5.** Phase 4 reuses the existing flat-image `set_background` for swaps. HDRI and `.glb` scenes wait.
- **Cross-persona dismiss is *only* the active persona's dismiss words** (matches Phase 3 behavior). A different persona's dismiss words don't dismiss the active persona. Spec §3 says the same.

## Phase 3 reviewer carry-overs addressed here

- `is_default: Optional[bool] = False` → tightened to `bool = False` in Task 1.
- Synthetic `change` event for THINKING-meta refresh in `viewer.js` → cleaned up via `ViewerState.updateMeta()` in Task 8.
- Stale `make js-shell` reference in old plan — N/A (cosmetic; not referenced here).

---

## Task 1: Tighten `is_default` + boot-persona resolution helper (TDD)

**Files:**
- Modify: `persona.py` (Persona BaseModel — `is_default` typing)
- Modify: `playAIdes.py` (new module-level helper `find_default_persona_id`)
- Test: `tests/unit/test_persona.py` (extend `TestPersonaWakeAndDismiss`)
- Test: `tests/unit/test_playaides_default_persona.py` (new)

`is_default` was added in Phase 3 with `Optional[bool] = False` for forward-compat. Phase 4 actually consumes it; tighten the type to `bool = False` so `None` is no longer a valid value, and add a helper that scans the personas directory for the one flagged default.

- [ ] **Step 1: Tighten the schema test in `tests/unit/test_persona.py`**

Find the existing `TestPersonaWakeAndDismiss` class (added in Phase 3 commit f6b856b). Add this test method at the bottom of that class:

```python
    def test_is_default_rejects_none(self):
        """is_default must be a real bool now (Phase 4 boot resolution
        consumes it). None should fail validation."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Persona(
                name="X", back_ground="bg", psyche=Psyche(traits=[]),
                gender="Female", language="English",
                is_default=None,
            )
```

If `pytest` isn't already imported at the top of the file, add `import pytest`.

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "(FAILED|test_is_default_rejects_none)" | head
```

Expected: 1 failure (Pydantic currently accepts None for an Optional field).

- [ ] **Step 3: Tighten the field**

In `persona.py`, find `is_default: Optional[bool] = False` and replace with:

```python
    is_default: bool = False
```

(Single line change — the surrounding fields stay `Optional[...]`.)

- [ ] **Step 4: Run test to confirm it passes**

```bash
make test 2>&1 | tail -3
```

Expected: `99 passed, 4 deselected` (was 98; +1 new test).

- [ ] **Step 5: Write the boot-resolution helper test**

Create `tests/unit/test_playaides_default_persona.py`:

```python
"""Unit tests for find_default_persona_id — picks the boot persona when
the URL/CLI doesn't specify one."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from playAIdes import find_default_persona_id


def _seed(tmp_path: Path, name: str, is_default: bool):
    pdir = tmp_path / name
    pdir.mkdir()
    (pdir / "persona.json").write_text(json.dumps({
        "name": name.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "is_default": is_default,
    }))


def test_returns_id_of_persona_with_is_default_true(tmp_path):
    _seed(tmp_path, "alice", is_default=False)
    _seed(tmp_path, "silver", is_default=True)
    _seed(tmp_path, "zelda", is_default=False)
    assert find_default_persona_id(tmp_path) == "silver"


def test_falls_back_to_first_alphabetical_when_no_default(tmp_path, caplog):
    _seed(tmp_path, "zelda", is_default=False)
    _seed(tmp_path, "alice", is_default=False)
    _seed(tmp_path, "silver", is_default=False)
    assert find_default_persona_id(tmp_path) == "alice"
    # Spec §7: "If none flagged, fall back to the first persona
    # alphabetically and log a warning."
    assert any("no is_default" in r.message.lower() for r in caplog.records)


def test_returns_none_when_no_personas(tmp_path):
    assert find_default_persona_id(tmp_path) is None


def test_skips_invalid_persona_dirs(tmp_path):
    _seed(tmp_path, "alice", is_default=False)
    # A directory with no persona.json — should be skipped silently.
    (tmp_path / "broken").mkdir()
    # A persona.json that's not valid JSON — should be skipped silently.
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "persona.json").write_text("{not json")
    assert find_default_persona_id(tmp_path) == "alice"
```

- [ ] **Step 6: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_.*_default)" | head
```

Expected: 4 failures with `ImportError: cannot import name 'find_default_persona_id'`.

- [ ] **Step 7: Add the helper to `playAIdes.py`**

In `playAIdes.py`, just below the `DEFAULT_IDLE_ANIMATION` constant (around line 16), add:

```python
def find_default_persona_id(personas_dir) -> Optional[str]:
    """Pick the boot persona id from a personas directory.

    Returns:
        - Id of the persona whose `is_default: true`, if any.
        - Else id of the first persona alphabetically (with a warning).
        - Else None when no personas are found.

    Skips directories that don't contain a parseable persona.json.
    """
    from pathlib import Path
    personas_dir = Path(personas_dir)
    if not personas_dir.is_dir():
        return None

    candidates = []
    for entry in sorted(personas_dir.iterdir()):
        if not entry.is_dir():
            continue
        pfile = entry / "persona.json"
        if not pfile.exists():
            continue
        try:
            data = json.loads(pfile.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        candidates.append((entry.name, bool(data.get("is_default", False))))

    if not candidates:
        return None

    for pid, is_default in candidates:
        if is_default:
            return pid

    fallback = candidates[0][0]
    logger.warning(
        "No persona has is_default=true; falling back to first alphabetically: %s",
        fallback,
    )
    return fallback
```

- [ ] **Step 8: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `103 passed, 4 deselected` (was 99; +4 new tests).

- [ ] **Step 9: Commit**

```bash
git add persona.py playAIdes.py tests/unit/test_persona.py tests/unit/test_playaides_default_persona.py
git commit -m "feat: tighten is_default; add find_default_persona_id helper"
```

---

## Task 2: Per-persona `chat_histories` map with atomic JSON persistence (TDD)

**Files:**
- Modify: `playAIdes.py` (`PlayAIdes` class — new attribute + load/save helpers)
- Test: `tests/unit/test_chat_history.py` (new)

Replace the single `self.chat_history: List[...]` with a `chat_histories: Dict[persona_id, List[Message]]` map. Histories are loaded lazily per persona from `personas/<id>/chat_history.json`, capped at N=80 messages on load (older trimmed), and persisted atomically on every turn.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_chat_history.py`:

```python
"""Unit tests for per-persona chat history persistence."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs, CHAT_HISTORY_CAP
from model_interfaces import MockLLM


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    """A PlayAIdes instance with use_avatar=True so the stub server is wired."""
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


class TestChatHistoryPersistence:
    def test_chat_histories_starts_empty(self, play):
        assert play.chat_histories == {}

    def test_load_history_reads_existing_json(self, play, tmp_personas_dir):
        pid = "testbot"
        history_file = tmp_personas_dir / pid / "chat_history.json"
        history_file.write_text(json.dumps([
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]))
        loaded = play._load_history(pid)
        assert loaded == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert play.chat_histories[pid] == loaded

    def test_load_history_returns_empty_list_when_file_missing(self, play):
        assert play._load_history("nobody") == []
        assert play.chat_histories["nobody"] == []

    def test_load_history_caps_at_N_messages(self, play, tmp_personas_dir):
        pid = "testbot"
        history_file = tmp_personas_dir / pid / "chat_history.json"
        # Seed 200 messages — should be trimmed to the most recent N.
        big = [{"role": "user", "content": f"msg-{i}"} for i in range(200)]
        history_file.write_text(json.dumps(big))
        loaded = play._load_history(pid)
        assert len(loaded) == CHAT_HISTORY_CAP
        # Most-recent retention: last message is preserved.
        assert loaded[-1] == {"role": "user", "content": "msg-199"}

    def test_save_history_round_trip(self, play, tmp_personas_dir):
        pid = "testbot"
        play.chat_histories[pid] = [
            {"role": "user", "content": "ping"},
            {"role": "assistant", "content": "pong"},
        ]
        play._save_history(pid)
        history_file = tmp_personas_dir / pid / "chat_history.json"
        assert history_file.exists()
        on_disk = json.loads(history_file.read_text())
        assert on_disk == play.chat_histories[pid]

    def test_save_history_is_atomic(self, play, tmp_personas_dir, monkeypatch):
        """If the write fails partway, the original file is left intact —
        atomic via NamedTemporaryFile + os.replace."""
        pid = "testbot"
        history_file = tmp_personas_dir / pid / "chat_history.json"
        history_file.write_text(json.dumps([{"role": "user", "content": "before"}]))
        play.chat_histories[pid] = [
            {"role": "user", "content": "after"},
        ]

        # Make os.replace fail to simulate a crash mid-write.
        import os as os_mod
        def boom(*a, **kw):
            raise OSError("disk full simulation")
        monkeypatch.setattr(os_mod, "replace", boom)

        with pytest.raises(OSError):
            play._save_history(pid)

        # Original file is untouched (no half-written content).
        on_disk = json.loads(history_file.read_text())
        assert on_disk == [{"role": "user", "content": "before"}]

    def test_delete_history_clears_memory_and_disk(self, play, tmp_personas_dir):
        pid = "testbot"
        play.chat_histories[pid] = [{"role": "user", "content": "x"}]
        play._save_history(pid)
        history_file = tmp_personas_dir / pid / "chat_history.json"
        assert history_file.exists()

        play.delete_history(pid)
        assert pid not in play.chat_histories
        assert not history_file.exists()
```

The test reuses the existing `persona_file`, `fake_tts`, `no_incarnation`, and `tmp_personas_dir` conftest fixtures.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_chat_histor)" | head
```

Expected: 7 failures — `chat_histories`, `_load_history`, `_save_history`, `delete_history`, and `CHAT_HISTORY_CAP` don't exist yet.

- [ ] **Step 3: Add module-level constant + class attribute + helpers in `playAIdes.py`**

Just below `DEFAULT_IDLE_ANIMATION = "model_pose"` (around line 16), add:

```python
# Cap chat_histories at the most recent N messages on load. Older entries
# are trimmed in-place so the LLM context window stays bounded. Configurable
# later via env / persona-level override.
CHAT_HISTORY_CAP = 80
```

In the `PlayAIdes.__init__` method, find `self.chat_history: List[Dict[str, str]] = []` (around line 51) and replace with:

```python
        # chat_histories: persona_id → list of message dicts. Loaded lazily
        # per persona from personas/<id>/chat_history.json on first access.
        # See _load_history / _save_history / delete_history for persistence.
        self.chat_histories: Dict[str, List[Dict[str, str]]] = {}
        # Backwards-compat alias for chat() — points at the active persona's
        # history once a persona is loaded.
        self.chat_history: List[Dict[str, str]] = []
```

Then add three new methods on `PlayAIdes`. Place them just above `_handle_incarnation_message`:

```python
    def _history_path(self, persona_id: str):
        """Path to a persona's chat_history.json. Path-traversal guarded."""
        from pathlib import Path
        if not persona_id or "/" in persona_id or "\\" in persona_id or persona_id in {".", ".."}:
            raise ValueError(f"Suspicious persona_id: {persona_id!r}")
        return Path("personas") / persona_id / "chat_history.json"

    def _load_history(self, persona_id: str) -> List[Dict[str, str]]:
        """Load a persona's chat history from disk, cap at the most recent
        CHAT_HISTORY_CAP messages, store in chat_histories, and return it.
        Missing file → empty list. Idempotent."""
        if persona_id in self.chat_histories:
            return self.chat_histories[persona_id]
        path = self._history_path(persona_id)
        history: List[Dict[str, str]] = []
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read %s: %s — starting empty", path, e)
                history = []
        if len(history) > CHAT_HISTORY_CAP:
            history = history[-CHAT_HISTORY_CAP:]
        self.chat_histories[persona_id] = history
        return history

    def _save_history(self, persona_id: str):
        """Persist a persona's chat history atomically via tempfile + os.replace.
        If os.replace raises, the original file is left intact."""
        import tempfile
        path = self._history_path(persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        history = self.chat_histories.get(persona_id, [])
        # Write to a sibling tempfile, then atomically rename over the target.
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(path.parent), delete=False,
            prefix=".chat_history.", suffix=".json.tmp",
        ) as tf:
            json.dump(history, tf, ensure_ascii=False, indent=2)
            tmp_path = tf.name
        os.replace(tmp_path, str(path))

    def delete_history(self, persona_id: str):
        """Clear a persona's history both in memory and on disk.
        Not exposed to the WS in v1 — callable for future /forget commands."""
        self.chat_histories.pop(persona_id, None)
        path = self._history_path(persona_id)
        if path.exists():
            path.unlink()
```

(`os` is already imported at the top of playAIdes.py. `tempfile` and `Path` are imported lazily inside the methods so we don't need to touch the module-level import block.)

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `110 passed, 4 deselected` (was 103; +7 new tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/unit/test_chat_history.py
git commit -m "feat: per-persona chat_histories with atomic JSON persistence"
```

---

## Task 3: `PlayAIdes.set_persona(id)` + chat() routes to per-persona history (TDD)

**Files:**
- Modify: `playAIdes.py` (new `set_persona`; modify `chat()`)
- Test: `tests/unit/test_set_persona.py` (new)

`set_persona(id)` swaps the active persona at runtime. It validates the id, loads the persona, runs `_validate_persona`, and ensures the per-persona history is loaded into `chat_histories`. The `chat()` method gains an optional `persona_id` arg that routes to that persona's history; default keeps existing CLI behavior.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_set_persona.py`:

```python
"""Unit tests for PlayAIdes.set_persona — runtime persona swap."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs, PersonaLoadError
from model_interfaces import MockLLM


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


def _seed_persona(tmp_personas_dir, pid: str, name: str = None):
    pdir = tmp_personas_dir / pid
    pdir.mkdir(exist_ok=True)
    (pdir / "persona.json").write_text(json.dumps({
        "name": name or pid.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
    }))
    return pid


class TestSetPersona:
    def test_swaps_to_new_persona(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        result = play.set_persona("rin")
        assert result is not None
        assert result.name == "Rin"
        assert play.current_persona is result

    def test_idempotent_when_same_id(self, play):
        # `persona_file` fixture seeds "testbot" — the active persona.
        original = play.current_persona
        result = play.set_persona("testbot")
        assert result is original
        assert play.current_persona is original

    def test_refuses_unknown_id(self, play):
        with pytest.raises(PersonaLoadError):
            play.set_persona("nobody-with-this-name")

    def test_refuses_path_traversal(self, play):
        for bad_id in ["../etc", "..", ".", "foo/bar", "foo\\bar", ""]:
            with pytest.raises((PersonaLoadError, ValueError)):
                play.set_persona(bad_id)

    def test_loads_history_on_swap(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        history_file = tmp_personas_dir / "rin" / "chat_history.json"
        history_file.write_text(json.dumps([
            {"role": "user", "content": "old hello"},
        ]))
        play.set_persona("rin")
        assert "rin" in play.chat_histories
        assert play.chat_histories["rin"] == [
            {"role": "user", "content": "old hello"},
        ]

    def test_does_not_reset_existing_history(self, play, tmp_personas_dir):
        # Existing in-memory history for the active persona must not be cleared.
        play.chat_histories["testbot"] = [
            {"role": "user", "content": "earlier"},
        ]
        _seed_persona(tmp_personas_dir, "rin")
        play.set_persona("rin")  # swap away
        assert play.chat_histories["testbot"] == [
            {"role": "user", "content": "earlier"},
        ]


class TestChatPerPersonaRouting:
    def test_chat_appends_to_active_persona_history(self, play):
        play.chat("hello there")
        active_id = play.current_persona.name.strip().lower().replace(" ", "_")
        assert active_id in play.chat_histories
        history = play.chat_histories[active_id]
        # MockLLM gives a deterministic reply; expect both turns appended.
        roles = [m["role"] for m in history]
        assert "user" in roles
        assert "assistant" in roles

    def test_chat_with_explicit_persona_id_routes_there(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        play.set_persona("rin")
        # MockLLM will respond. The "rin" history should grow.
        play.chat("hi rin", persona_id="rin")
        assert any("rin" == k for k in play.chat_histories.keys())
        rin_history = play.chat_histories["rin"]
        assert len(rin_history) >= 2  # user + assistant

    def test_chat_persists_after_each_turn(self, play, tmp_personas_dir):
        play.chat("first thing")
        active_id = play.current_persona.name.strip().lower().replace(" ", "_")
        history_file = tmp_personas_dir / active_id / "chat_history.json"
        assert history_file.exists()
        on_disk = json.loads(history_file.read_text())
        assert on_disk == play.chat_histories[active_id]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_set_persona|TestChatPerPersonaRouting)" | head
```

Expected: most fail (`set_persona` doesn't exist; `chat()` doesn't accept `persona_id`).

- [ ] **Step 3: Add `set_persona` and modify `chat()`**

In `playAIdes.py`, add this method just below `delete_history` (so all the persona-mgmt methods cluster together):

```python
    def set_persona(self, persona_id: str) -> Optional[Persona]:
        """Reload the active persona at runtime.

        Loads personas/<id>/persona.json, runs _validate_persona, swaps
        current_persona, and ensures the per-persona chat history is
        loaded into chat_histories. Idempotent: no-op if id matches the
        currently-active persona.

        Path-traversal guarded the same way delete_persona is. Raises
        PersonaLoadError on any failure (the WS handler turns this into
        a persona_changed{ok: false, error}).
        """
        if not persona_id or "/" in persona_id or "\\" in persona_id or persona_id in {".", ".."}:
            raise PersonaLoadError(f"Suspicious persona_id: {persona_id!r}")

        # Idempotency: same id as the currently-active persona → no-op.
        if (self.current_persona and
                self.current_persona.name.strip().lower().replace(" ", "_") == persona_id):
            # Still ensure history is loaded.
            self._load_history(persona_id)
            return self.current_persona

        path = os.path.join("personas", persona_id, "persona.json")
        if not os.path.exists(path):
            raise PersonaLoadError(f"Persona not found: {persona_id}")

        # Re-use the existing loader (raises PersonaLoadError on bad input).
        self._load_persona_from_file(path)
        self._load_history(persona_id)
        return self.current_persona
```

Then modify `chat()` to accept an optional `persona_id` and route to that persona's history. Find the existing `def chat(self, user_input: str) -> str:` and replace its signature + body:

```python
    def chat(self, user_input: str, persona_id: Optional[str] = None) -> str:
        if not self.current_persona:
            return "No persona loaded."

        # Resolve the persona to route this turn against. Defaults to active.
        target_id = persona_id or self.current_persona.name.strip().lower().replace(" ", "_")

        # Ensure that persona's history is loaded (lazy from disk).
        history = self._load_history(target_id)

        # Construct system prompt based on the active persona (which may
        # differ from target_id in a multi-persona future; v1 they match).
        system_prompt = (f"You are impersonating a this character named"
        f"{self.current_persona.name}. "
        f"Your background is: {self.current_persona.back_ground}. "
        )
        if self.current_persona.psyche and self.current_persona.psyche.traits:
            system_prompt += f"Your traits are: {', '.join(self.current_persona.psyche.traits)}. "
        if self.current_persona.language:
            system_prompt += f"Always respond in {self.current_persona.language}. "

        history.append({"role": "user", "content": user_input})
        response = self.llm.chat(history, system_prompt=system_prompt)

        # Broadcast the reply text to any connected viewer so its subtitle
        # band can render before TTS audio arrives. No-op if the
        # incarnation server isn't running (CLI-only mode).
        if self.incarnation_server is not None:
            self.incarnation_server.send_command(
                "assistant_message",
                {"text": response, "persona_id": target_id},
            )

        if self.args.use_voice:
            if self.args.use_avatar and self.incarnation_server:
                self._proxy_lip_sync(response)
            else:
                self._direct_speak(response)

        history.append({"role": "assistant", "content": response})

        # Trim to cap and persist atomically.
        if len(history) > CHAT_HISTORY_CAP:
            history[:] = history[-CHAT_HISTORY_CAP:]
        self._save_history(target_id)

        return response
```

(The `_proxy_lip_sync` and `_direct_speak` calls stand in for whatever existing voice-dispatch code lives there. If the existing function calls those differently, preserve them — only the new bits are: routing through `self._load_history(target_id)` instead of `self.chat_history`, including `persona_id` in `assistant_message`, and trimming + saving at the end.)

Also: keep the legacy `self.chat_history` alias up to date for any caller that still reads it:

In `_load_persona_from_file`, just below `self._validate_persona(self.current_persona)`, add:

```python
        # Keep the legacy chat_history alias pointing at the active
        # persona's history (so any caller that reads self.chat_history
        # directly still works during the transition).
        active_id = self.current_persona.name.strip().lower().replace(" ", "_")
        self.chat_history = self._load_history(active_id)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `119 passed, 4 deselected` (was 110; +9 new tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/unit/test_set_persona.py
git commit -m "feat: PlayAIdes.set_persona + chat() per-persona routing"
```

---

## Task 4: Multi-client WS support + binding registry (TDD)

**Files:**
- Modify: `incarnation_server.py` (replace `self.connected_client` with a registry)
- Test: `tests/integration/test_persona_routing.py` (new)

`incarnation_server.py` currently keeps a single `self.connected_client = websocket` reference. Phase 4 needs multiple connected clients (kitchen + bedroom TVs both showing Silver) and per-client persona binding so `assistant_message` only reaches clients bound to that persona.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_persona_routing.py`:

```python
"""Integration test: assistant_message broadcasts only to clients bound
to the matching persona_id.

Uses raw WebSocket clients via FastAPI's TestClient since this exercises
the actual broadcast path."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from incarnation_server import IncarnationServer

pytestmark = pytest.mark.integration


@pytest.fixture
def server():
    """Bare server with a no-op callback so we can drive WS frames directly."""
    msgs_received = []
    s = IncarnationServer(on_message_callback=lambda msg: msgs_received.append(msg))
    s.received = msgs_received
    return s


def test_assistant_message_broadcasts_only_to_bound_clients(server):
    """Two WS clients bind to different personas; assistant_message for
    one persona reaches only that client."""
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as ws_a, \
         client.websocket_connect("/ws") as ws_b:
        # Drain any boot-time frames the server may have queued.
        for ws in (ws_a, ws_b):
            try:
                ws.receive_text()  # opportunistic; may block
            except Exception:
                pass

        # Bind ws_a to "silver", ws_b to "rin".
        ws_a.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "silver"}}))
        ws_b.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "rin"}}))

        # Server-side broadcast targeted at "silver".
        server.broadcast_to_persona("silver", "assistant_message", {
            "text": "for silver only", "persona_id": "silver",
        })

        # ws_a should see assistant_message; ws_b should not.
        msg_a = json.loads(ws_a.receive_text(timeout=1.0))
        assert msg_a["type"] == "assistant_message"
        assert msg_a["payload"]["text"] == "for silver only"

        # ws_b shouldn't have a frame waiting; reading should time out / be empty.
        # TestClient lacks non-blocking reads — we instead send a sentinel from
        # the server and assert ws_b sees the sentinel BEFORE the silver msg.
        # (If the broadcast was incorrectly routed, ws_b would see "for silver only".)
        server.broadcast_to_persona("rin", "ping", {"hello": "rin"})
        msg_b = json.loads(ws_b.receive_text(timeout=1.0))
        assert msg_b["type"] == "ping"


def test_disconnect_clears_binding(server):
    """When a client disconnects, its persona binding is removed and a
    later broadcast doesn't try to send to a closed socket."""
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "silver"}}))
        # Drain the bind acknowledgement.
        try:
            ws.receive_text(timeout=0.5)
        except Exception:
            pass
    # Connection is closed by the time we exit the with-block.
    # Broadcasting should not raise.
    server.broadcast_to_persona("silver", "assistant_message", {"text": "after disconnect"})


def test_dismiss_persona_clears_binding(server):
    """dismiss_persona unbinds the client; subsequent broadcasts don't
    reach it (until it re-binds)."""
    client = TestClient(server.app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "set_active_persona", "payload": {"id": "silver"}}))
        # Drain ack.
        try: ws.receive_text(timeout=0.5)
        except Exception: pass

        ws.send_text(json.dumps({"type": "dismiss_persona", "payload": {"id": "silver"}}))
        # Drain ack.
        try: ws.receive_text(timeout=0.5)
        except Exception: pass

        # Broadcast for "silver" — should NOT reach this client.
        server.broadcast_to_persona("silver", "assistant_message", {"text": "after dismiss"})

        # Use a sentinel for "silver-after-dismiss" — if dismiss worked,
        # we won't see the assistant_message; we can prove this by sending
        # a separately-targeted message and assert the client sees it next.
        # (The client is still connected; just not bound.)
        server.broadcast_to_all("global_ping", {"x": 1})
        msg = json.loads(ws.receive_text(timeout=1.0))
        assert msg["type"] == "global_ping"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_assistant_message_broadcasts|test_disconnect_clears|test_dismiss_persona_clears)" | head
```

Expected: 3 failures (`broadcast_to_persona` and `broadcast_to_all` don't exist; the WS endpoint doesn't handle `set_active_persona` or `dismiss_persona` yet).

- [ ] **Step 3: Replace single-client with multi-client + binding registry**

In `incarnation_server.py`, find the `__init__` block (where `self.connected_client = None` and `self.message_queue = []` are initialized — around line 50). Replace the single `connected_client` field with:

```python
        # Multi-client support (Phase 4): every connected WebSocket lives in
        # `_clients`; bindings map each socket to the persona id it's
        # currently displaying so we can route assistant_message broadcasts.
        self._clients: set = set()
        self._bindings: dict = {}   # WebSocket → persona_id
        self.message_queue: list = []
```

Replace the WS endpoint (around lines 94–118) with the multi-client version:

```python
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            logger.info("Incarnation client connected via WebSocket")
            self._clients.add(websocket)

            # Drain any boot-time queued messages to this fresh client.
            while self.message_queue:
                msg = self.message_queue.pop(0)
                try:
                    await websocket.send_json(msg)
                except Exception:
                    break

            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {raw}")
                        continue

                    msg_type = msg.get("type")
                    payload = msg.get("payload", {})

                    # Bind / unbind happen at the socket level, not via the
                    # PlayAIdes callback (the callback can also see them — it
                    # uses set_active_persona to swap current_persona).
                    if msg_type == "set_active_persona":
                        pid = payload.get("id")
                        if pid:
                            self._bindings[websocket] = pid
                            logger.info(f"WS bound to persona {pid}")
                    elif msg_type == "dismiss_persona":
                        self._bindings.pop(websocket, None)
                        logger.info("WS persona binding cleared")

                    if self.on_message_callback:
                        self.on_message_callback(msg)
            except WebSocketDisconnect:
                logger.info("Incarnation client disconnected")
            finally:
                self._clients.discard(websocket)
                self._bindings.pop(websocket, None)
```

Now add two broadcast helpers below `send_command` (around line 309):

```python
    def broadcast_to_persona(self, persona_id: str, cmd_type: str, payload: dict = None):
        """Send a WS frame to every connected client bound to persona_id.
        No-op if no clients match (e.g. the persona has been dismissed
        on every TV)."""
        targets = [ws for ws, pid in self._bindings.items() if pid == persona_id]
        for ws in targets:
            self._safe_send(ws, {"type": cmd_type, "payload": payload or {}})

    def broadcast_to_all(self, cmd_type: str, payload: dict = None):
        """Send a WS frame to every connected client, regardless of binding."""
        for ws in list(self._clients):
            self._safe_send(ws, {"type": cmd_type, "payload": payload or {}})

    def _safe_send(self, websocket, msg: dict):
        """Best-effort send; drops the client on any send failure (likely
        disconnected mid-broadcast)."""
        try:
            # asyncio.run_coroutine_threadsafe-equivalent: schedule the
            # send on the running loop.
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(websocket.send_json(msg))
            else:
                loop.run_until_complete(websocket.send_json(msg))
        except Exception as e:
            logger.warning(f"Broadcast send failed, dropping client: {e}")
            self._clients.discard(websocket)
            self._bindings.pop(websocket, None)
```

Finally — the existing `send_command` method probably writes to `self.connected_client`. Update it to broadcast to all clients (preserves Phase 1–3 behavior where there was effectively one client). Find `def send_command` and replace its body to use `broadcast_to_all`:

```python
    def send_command(self, cmd_type: str, payload: dict = None):
        """Legacy single-client API. Now broadcasts to ALL connected
        clients — Phase 4 broadcast-to-persona is via broadcast_to_persona."""
        self.broadcast_to_all(cmd_type, payload)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `122 passed, 4 deselected` (was 119; +3 new tests).

- [ ] **Step 5: Commit**

```bash
git add incarnation_server.py tests/integration/test_persona_routing.py
git commit -m "feat(server): multi-client WS + persona binding registry"
```

---

## Task 5: Wire `set_active_persona` and `dismiss_persona` into PlayAIdes (TDD)

**Files:**
- Modify: `playAIdes.py` (`_handle_incarnation_message` adds branches)
- Test: `tests/integration/test_set_active_persona_ws.py` (new)

The WS endpoint already (per Task 4) updates the binding registry on `set_active_persona` / `dismiss_persona`. PlayAIdes also needs to react: on `set_active_persona`, call `set_persona(id)`, broadcast `persona_changed`, and emit `unload_model` / `load_model` / `history_loaded` / `set_background` for the requesting client. On `dismiss_persona` we just clear the persona binding (already done WS-side; nothing for PlayAIdes to do beyond logging).

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_set_active_persona_ws.py`:

```python
"""Integration test: set_active_persona triggers persona swap + emits
persona_changed, history_loaded, unload_model, load_model."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _seed_persona(tmp_personas_dir, pid: str, name: str = None,
                  intro_animation: str = None, model_url: str = "m.vrm"):
    pdir = tmp_personas_dir / pid
    pdir.mkdir(exist_ok=True)
    persona = {
        "name": name or pid.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {"model_url": model_url},
    }
    if intro_animation:
        persona["avatar"]["intro_animation"] = intro_animation
    (pdir / "persona.json").write_text(json.dumps(persona))


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


class TestSetActivePersonaWS:
    def test_emits_persona_changed_ok_on_swap(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin", model_url="rin.vrm")
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        changed = [(c, p) for c, p in cmds if c == "persona_changed"]
        assert len(changed) == 1
        _, payload = changed[0]
        assert payload["ok"] is True
        assert payload["persona"]["name"] == "Rin"

    def test_emits_persona_changed_error_on_unknown_id(self, play):
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "no-such-persona"},
        })
        cmds = play.incarnation_server.commands
        changed = [(c, p) for c, p in cmds if c == "persona_changed"]
        assert len(changed) == 1
        _, payload = changed[0]
        assert payload["ok"] is False
        assert "error" in payload

    def test_emits_unload_then_load_model_on_swap(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin", model_url="rin.vrm")
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        types_in_order = [c for c, _ in cmds]
        assert "unload_model" in types_in_order
        assert "load_model" in types_in_order
        # Order: unload before load.
        assert types_in_order.index("unload_model") < types_in_order.index("load_model")
        # Load carries the new persona's model_url.
        load = [(c, p) for c, p in cmds if c == "load_model"][0][1]
        assert load["url"] == "rin.vrm"

    def test_no_unload_when_same_persona(self, play):
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "testbot"},   # same as initial
        })
        cmds = play.incarnation_server.commands
        # Idempotent same-persona swap: no unload_model emitted.
        assert "unload_model" not in [c for c, _ in cmds]

    def test_emits_history_loaded(self, play, tmp_personas_dir):
        _seed_persona(tmp_personas_dir, "rin")
        history_file = tmp_personas_dir / "rin" / "chat_history.json"
        history_file.write_text(json.dumps([
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "earlier reply"},
        ]))
        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": "rin"},
        })
        cmds = play.incarnation_server.commands
        hist = [(c, p) for c, p in cmds if c == "history_loaded"]
        assert len(hist) == 1
        _, payload = hist[0]
        assert payload["persona_id"] == "rin"
        assert payload["history"] == [
            {"role": "user", "content": "earlier"},
            {"role": "assistant", "content": "earlier reply"},
        ]

    def test_user_input_uses_persona_id_from_payload(self, play, tmp_personas_dir):
        """user_input now carries persona_id; chat() routes to that history."""
        _seed_persona(tmp_personas_dir, "rin")
        play.set_persona("rin")
        play._handle_incarnation_message({
            "type": "user_input",
            "payload": {"text": "hi rin", "persona_id": "rin"},
        })
        # The MockLLM reply should land in rin's history.
        assert "rin" in play.chat_histories
        rin_hist = play.chat_histories["rin"]
        assert any(m.get("content") == "hi rin" for m in rin_hist)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|TestSetActivePersonaWS)" | head
```

Expected: 6 failures (`set_active_persona` handler doesn't exist; user_input doesn't read persona_id).

- [ ] **Step 3: Add the WS handlers in `_handle_incarnation_message`**

In `playAIdes.py`, find `_handle_incarnation_message`. Just below the existing `if msg_type == "user_input":` branch (added in Phase 2 commit cbba1d3), add two new branches:

```python
        if msg_type == "set_active_persona":
            requested_id = (payload.get("id") or "").strip()
            prev_id = (self.current_persona.name.strip().lower().replace(" ", "_")
                       if self.current_persona else None)
            try:
                persona = self.set_persona(requested_id)
            except (PersonaLoadError, ValueError) as e:
                self.incarnation_server.send_command("persona_changed", {
                    "ok": False,
                    "error": str(e),
                })
                return

            self.incarnation_server.send_command("persona_changed", {
                "ok": True,
                "persona": persona.model_dump(),
            })

            # If we actually swapped, tell the browser to unload the old VRM
            # and load the new one. Same persona → skip (model is still loaded).
            if prev_id != requested_id:
                self.incarnation_server.send_command("unload_model", {})
                if persona.avatar and persona.avatar.model_url:
                    self.incarnation_server.send_command("load_model", {
                        "url": persona.avatar.model_url,
                    })
                # Background carries on the existing flat-image path until Phase 5.
                if persona.avatar and persona.avatar.background_url:
                    self.incarnation_server.send_command("set_background", {
                        "url": persona.avatar.background_url,
                    })

            # History rehydration (deferred chat-panel UI lands in Phase 5;
            # frame is sent now so phase-4 clients can stash it).
            self.incarnation_server.send_command("history_loaded", {
                "persona_id": requested_id,
                "history": list(self.chat_histories.get(requested_id, [])),
            })
            return

        if msg_type == "dismiss_persona":
            # The WS endpoint already cleared this client's binding registry
            # entry; PlayAIdes itself has no further action — chat history
            # is preserved on disk per spec §2 dismiss subsection.
            logger.info("Persona dismissed (binding cleared by WS layer)")
            return
```

Also update the existing `user_input` branch to read `persona_id` from the payload:

```python
        if msg_type == "user_input":
            text = (payload.get("text") or "").strip()
            if not text:
                return
            persona_id = (payload.get("persona_id") or "").strip() or None
            try:
                self.chat(text, persona_id=persona_id)
            except Exception as e:
                logger.exception(f"user_input chat() failed: {e}")
            return
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `128 passed, 4 deselected` (was 122; +6 new tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_set_active_persona_ws.py
git commit -m "feat: WS handlers for set_active_persona and dismiss_persona"
```

---

## Task 6: Route `assistant_message` via the persona binding (TDD)

**Files:**
- Modify: `playAIdes.py` (chat() emits via `broadcast_to_persona` instead of `send_command`)
- Test: `tests/integration/test_persona_routing.py` (extend with end-to-end test)

In Task 5 the server already has `broadcast_to_persona`. Now `PlayAIdes.chat()` should emit `assistant_message` via that route so only clients bound to the right persona see the reply, instead of broadcasting to every client.

- [ ] **Step 1: Extend the integration test**

In `tests/integration/test_persona_routing.py`, append at the bottom:

```python
def test_chat_assistant_message_routes_via_persona_binding(persona_file, fake_tts):
    """chat() should call broadcast_to_persona, not broadcast_to_all,
    so only clients bound to the persona see the reply."""
    from playAIdes import PlayAIdes, PlayAIdesArgs
    from model_interfaces import MockLLM
    from unittest.mock import MagicMock

    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    play = PlayAIdes(args)
    # Replace the stub server with a MagicMock so we can spy on the calls.
    spy = MagicMock()
    spy.broadcast_to_persona = MagicMock()
    play.incarnation_server = spy

    play.chat("hello")
    # Find the assistant_message broadcast.
    persona_id = play.current_persona.name.strip().lower().replace(" ", "_")
    spy.broadcast_to_persona.assert_any_call(
        persona_id, "assistant_message",
        {"text": "Mocked response", "persona_id": persona_id},
    )
```

(`MockLLM` returns `"Mocked response"` deterministically. Adjust the expected text to whatever your `MockLLM` actually returns — check `model_interfaces.py:MockLLM.chat`.)

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "(FAILED|test_chat_assistant_message_routes)" | head
```

Expected: failure (`chat()` currently calls `send_command`, not `broadcast_to_persona`).

- [ ] **Step 3: Update `chat()` to use `broadcast_to_persona`**

In `playAIdes.py`, in the `chat()` method, find the assistant_message emit:

```python
        if self.incarnation_server is not None:
            self.incarnation_server.send_command(
                "assistant_message",
                {"text": response, "persona_id": target_id},
            )
```

Replace with:

```python
        if self.incarnation_server is not None:
            # Broadcast only to clients bound to this persona — every TV
            # showing Silver sees Silver's reply; TVs showing other personas
            # are unaffected. (Falls back gracefully when no clients are bound.)
            self.incarnation_server.broadcast_to_persona(
                target_id,
                "assistant_message",
                {"text": response, "persona_id": target_id},
            )
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
make test 2>&1 | tail -3
```

Expected: `129 passed, 4 deselected` (was 128; +1 new test).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_persona_routing.py
git commit -m "feat: route assistant_message via broadcast_to_persona"
```

---

## Task 7: `ViewerState.updateMeta()` for clean THINKING-meta refresh (Vitest)

**Files:**
- Modify: `incarnation/src/viewerState.js`
- Modify: `incarnation/src/viewer.js` (replace synthetic dispatch in `refreshThinkingMeta`)
- Test: `incarnation/src/viewerState.test.js` (extend)

Phase 3's reviewer flagged that `viewer.js` synthesizes a `change` event with `prev === next === THINKING` to update meta without going through the state machine. Cleaner: a public `updateMeta(meta)` method on `ViewerState` that mutates `_meta` and emits `change`, so listeners stay in sync with `stateMachine.meta`.

- [ ] **Step 1: Write the failing test**

In `incarnation/src/viewerState.test.js`, find the existing `describe('ViewerState', ...)` block and append a new test inside it:

```js
    it('updateMeta refreshes meta + emits change without changing state', () => {
        const sm = new ViewerState(State.THINKING);
        const events = [];
        sm.addEventListener('change', (e) => events.push(e.detail));

        sm.updateMeta({ lastUtterance: 'hello world' });

        expect(sm.current).toBe(State.THINKING);
        expect(sm.meta).toEqual({ lastUtterance: 'hello world' });
        expect(events).toHaveLength(1);
        expect(events[0].prev).toBe(State.THINKING);
        expect(events[0].next).toBe(State.THINKING);
        expect(events[0].meta).toEqual({ lastUtterance: 'hello world' });
    });

    it('updateMeta accepts null and clears meta', () => {
        const sm = new ViewerState(State.THINKING);
        sm.updateMeta({ a: 1 });
        sm.updateMeta(null);
        expect(sm.meta).toBe(null);
    });
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test-js 2>&1 | grep -E "(FAIL|updateMeta)" | head
```

Expected: 2 failures with `sm2.updateMeta is not a function`.

- [ ] **Step 3: Add `updateMeta` to `ViewerState`**

In `incarnation/src/viewerState.js`, find the `transition(next, meta)` method. Add a new method just below it:

```js
    /**
     * Refresh the current state's metadata without changing state.
     * Emits `change` with prev === next so listeners (e.g. the overlay
     * subtitle renderer) can re-render. Useful for e.g. populating the
     * THINKING state's `lastUtterance` once STT returns.
     *
     * @param {object|null} meta — replaces _meta wholesale
     */
    updateMeta(meta) {
        const prevMeta = this._meta;
        this._meta = meta;
        this.dispatchEvent(new CustomEvent('change', {
            detail: {
                prev: this._state, next: this._state,
                prevMeta, meta,
            },
        }));
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 5 passed (5) / Tests 62 passed (62)` (was 60; +2 new).

- [ ] **Step 5: Replace synthetic dispatch in `viewer.js`**

In `incarnation/src/viewer.js`, find the `refreshThinkingMeta` helper added in commit edcbe93:

```js
function refreshThinkingMeta(text) {
    if (stateMachine.current !== State.THINKING) return;
    stateMachine.dispatchEvent(new CustomEvent('change', {
        detail: {
            prev: State.THINKING, next: State.THINKING,
            prevMeta: { lastUtterance: '…' },
            meta: { lastUtterance: text },
        },
    }));
}
```

Replace with:

```js
function refreshThinkingMeta(text) {
    if (stateMachine.current !== State.THINKING) return;
    stateMachine.updateMeta({ lastUtterance: text });
}
```

- [ ] **Step 6: Verify**

```bash
make test-js 2>&1 | tail -10
```

Expected: still 62 passed. The viewer.js change is a refactor — no test regression.

- [ ] **Step 7: Commit**

```bash
git add incarnation/src/viewerState.js incarnation/src/viewerState.test.js incarnation/src/viewer.js
git commit -m "refactor(viewer): ViewerState.updateMeta replaces synthetic dispatch"
```

---

## Task 8: `personasRegistry.js` — pure module caching all personas (Vitest)

**Files:**
- Create: `incarnation/src/personasRegistry.js`
- Test: `incarnation/src/personasRegistry.test.js`

Cross-persona wake matching needs all personas' wake/dismiss config in the browser. The pure registry maps `id → {name, wake_words, dismiss_words, model_url, is_default}` and offers `findByWakeWord(transcript)` and `findDefault()`. Wired to fetch via WS at boot in Task 9.

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/personasRegistry.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { PersonasRegistry } from './personasRegistry.js';

const SILVER = {
    id: 'silver',
    name: 'Silver',
    wake_words: ['hey silver', 'silver'],
    dismiss_words: ['goodnight silver'],
    is_default: true,
};
const RIN = {
    id: 'rin',
    name: 'Rin',
    wake_words: ['hey rin', 'rin'],
    dismiss_words: ['goodnight rin'],
    is_default: false,
};

describe('PersonasRegistry', () => {
    it('starts empty', () => {
        const r = new PersonasRegistry();
        expect(r.all()).toEqual([]);
    });

    it('replaceAll loads a list', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        expect(r.all().map((p) => p.id)).toEqual(['silver', 'rin']);
        expect(r.get('silver')).toEqual(SILVER);
    });

    it('findDefault returns the persona with is_default true', () => {
        const r = new PersonasRegistry();
        r.replaceAll([RIN, SILVER]);
        expect(r.findDefault()?.id).toBe('silver');
    });

    it('findDefault returns first alphabetical when none flagged', () => {
        const r = new PersonasRegistry();
        r.replaceAll([
            { ...RIN, is_default: false },
            { ...SILVER, is_default: false, id: 'alice', name: 'Alice' },
        ]);
        expect(r.findDefault()?.id).toBe('alice');
    });

    it('findDefault returns null when registry empty', () => {
        const r = new PersonasRegistry();
        expect(r.findDefault()).toBe(null);
    });

    it('findByWakeWord matches active persona first when tied', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        // "hey silver" matches Silver's wake word.
        const hit = r.findByWakeWord('Hey Silver, what time is it?', 'rin');
        expect(hit.persona.id).toBe('silver');
    });

    it('findByWakeWord prefers active persona on overlap', () => {
        const r = new PersonasRegistry();
        // Both have the literal phrase "hello" as a wake word — active wins.
        r.replaceAll([
            { ...SILVER, wake_words: ['hello'] },
            { ...RIN, wake_words: ['hello'] },
        ]);
        const hit = r.findByWakeWord('hello', 'rin');
        expect(hit.persona.id).toBe('rin');
    });

    it('findByWakeWord returns null when nothing matches', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        const hit = r.findByWakeWord('what time is it', 'silver');
        expect(hit).toBe(null);
    });

    it('findByWakeWord includes residual + matched phrase', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        const hit = r.findByWakeWord('Hey Rin, where are you', 'silver');
        expect(hit.persona.id).toBe('rin');
        expect(hit.phrase).toBe('hey rin');
        expect(hit.residual).toBe(', where are you');
    });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -10
```

Expected: 9 failures with module-not-found.

- [ ] **Step 3: Create `incarnation/src/personasRegistry.js`**

```js
/**
 * personasRegistry.js — browser-side cache of all personas.
 *
 * Populated at boot by fetching the personas list from the server.
 * Used by the orchestrator's voiceend handler to detect cross-persona
 * wake words ("Hey Rin" while Silver is active should fire a swap).
 */

import { matchPhrase } from './transcriptMatcher.js';

export class PersonasRegistry {
    constructor() {
        this._byId = new Map();
    }

    /** Replace the cache with a fresh list (server pushed). */
    replaceAll(personas) {
        this._byId.clear();
        for (const p of personas || []) {
            if (p && p.id) this._byId.set(p.id, p);
        }
    }

    /** Get a persona by id, or undefined. */
    get(id) {
        return this._byId.get(id);
    }

    /** All personas as an array, in insertion order. */
    all() {
        return Array.from(this._byId.values());
    }

    /**
     * Pick the boot persona:
     *   - Persona with is_default: true, if any.
     *   - Else first alphabetically (by id).
     *   - Else null when the registry is empty.
     */
    findDefault() {
        const all = this.all();
        if (!all.length) return null;
        const explicit = all.find((p) => p.is_default === true);
        if (explicit) return explicit;
        return [...all].sort((a, b) => (a.id || '').localeCompare(b.id || ''))[0];
    }

    /**
     * Find which persona's wake word(s) appear in a transcript.
     * Active persona is preferred on overlap (so saying the active
     * persona's name doesn't accidentally match a different persona
     * that shares an alias).
     *
     * @param {string} transcript
     * @param {string|null} activeId — id of the currently-active persona
     * @returns {{persona, phrase, residual}|null}
     */
    findByWakeWord(transcript, activeId) {
        if (!transcript) return null;
        // Try the active persona first.
        if (activeId) {
            const active = this.get(activeId);
            if (active) {
                const m = matchPhrase(transcript, active.wake_words);
                if (m.matched) {
                    return { persona: active, phrase: m.phrase, residual: m.residual };
                }
            }
        }
        // Then try every other persona.
        for (const persona of this.all()) {
            if (persona.id === activeId) continue;
            const m = matchPhrase(transcript, persona.wake_words);
            if (m.matched) {
                return { persona, phrase: m.phrase, residual: m.residual };
            }
        }
        return null;
    }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 6 passed (6) / Tests 71 passed (71)` (was 62, +9 new).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/personasRegistry.js incarnation/src/personasRegistry.test.js
git commit -m "feat(viewer): personasRegistry caches all personas + wake-word search"
```

---

## Task 9: Wire `personas_list` fetch + cross-persona wake matching

**Files:**
- Modify: `incarnation/src/viewer.js`

At boot, the browser sends `get_personas` over WS. The server already responds with `personas_list { personas: [...] }`. Browser populates `personasRegistry`. The voiceend handler then routes wake matches to the matching persona's id (which may differ from the active one).

- [ ] **Step 1: Add the registry import + instance**

In `incarnation/src/viewer.js`, alongside the existing imports, add:

```js
import { PersonasRegistry } from './personasRegistry.js';
```

Just below the existing `let activePersona = ...` (commit e039db8), add:

```js
const personasRegistry = new PersonasRegistry();
```

- [ ] **Step 2: Fetch personas list at boot + on persona swap**

After the existing `connection.addEventListener('persona_active', ...)` block, add:

```js
// On WS connect, request the personas list so the registry can drive
// cross-persona wake matching.
connection.addEventListener('connected', () => {
    connection.send('get_personas', {});
});

connection.addEventListener('personas_list', (e) => {
    personasRegistry.replaceAll(e.detail?.personas || []);
    console.log('[viewer] personas_list:', personasRegistry.all().map((p) => p.id));
});
```

- [ ] **Step 3: Replace the existing voiceend wake check with cross-persona search**

In the voiceend handler, find the section that does the wake gate (around line 213 of the current viewer.js, inside the `if (needsWake) { ... }` block). Replace:

```js
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
            console.log('[viewer] wake matched:', wake.phrase, '→ residual:', userInput || '(empty)');
        }
```

with:

```js
        if (needsWake) {
            // Cross-persona wake: match against ALL known personas, not just
            // the active one. A hit on a different persona triggers a swap.
            const activeId = personasRegistry.all()
                .find((p) => p.name === activePersona.name)?.id || null;
            const hit = personasRegistry.findByWakeWord(transcript, activeId);
            if (!hit) {
                console.log('[viewer] wake-mode drop, no wake-word in:', transcript);
                if (wasListening || stateMachine.current === State.THINKING) {
                    safeTransition(State.AMBIENT);
                }
                return;
            }
            userInput = hit.residual;
            console.log(
                '[viewer] wake matched:', hit.phrase,
                '→ persona:', hit.persona.id,
                '→ residual:', userInput || '(empty)',
            );

            // If the matched persona is NOT the currently-active one, fire a
            // server-side swap. The server's persona_changed handler kicks
            // off unload→load via the existing handlers (Task 10).
            const matchedId = hit.persona.id;
            if (matchedId !== activeId) {
                connection.send('set_active_persona', { id: matchedId });
                // The user_input below will route to the new persona; tag it
                // explicitly with the matched id so the server doesn't
                // accidentally route it to the previous active.
                if (userInput) {
                    connection.send('user_input', {
                        text: userInput, persona_id: matchedId,
                    });
                }
                lastUserUtterance = userInput;
                return;   // server handles the rest
            }
        }
```

- [ ] **Step 4: Verify Vitest still passes**

```bash
make test-js 2>&1 | tail -10
```

Expected: still 71 passed (no new tests; orchestrator still untested).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "feat(viewer): cross-persona wake matching via personasRegistry"
```

---

## Task 10: `persona_changed` reception + unload/load_model handlers + diagonal wipe

**Files:**
- Modify: `incarnation/src/viewer.js` (handle persona_changed, unload_model)
- Modify: `incarnation/src/incarnation.js` (add `unloadModel()` method)
- Create: `incarnation/src/wipeOverlay.js` (DOM-driven wipe animator)
- Modify: `incarnation/styles/viewer.css` (add the wipe animation)
- Modify: `incarnation/index.html` (add the wipe element)

When a swap is in flight, the browser plays a 200 ms red-diagonal wipe across the canvas, unloads the old VRM, and is ready to receive `load_model` for the new one.

- [ ] **Step 1: Add the wipe element to `index.html`**

In `incarnation/index.html`, between `<canvas id="viewer"></canvas>` and `<div id="mic-indicator" ...>`, add:

```html
    <!-- Phase 4: red-diagonal wipe shown during persona swap (200 ms). -->
    <div id="wipe-overlay" class="wipe-overlay"></div>
```

- [ ] **Step 2: Add the wipe CSS**

In `incarnation/styles/viewer.css`, append at the end:

```css
/* ── Persona swap wipe (Phase 4) ──────────────────────────── */
.wipe-overlay {
    position: fixed;
    inset: 0;
    z-index: 200;
    pointer-events: none;
    opacity: 0;
    background: linear-gradient(135deg,
        transparent 0%,
        transparent 35%,
        var(--red) 50%,
        transparent 65%,
        transparent 100%);
    transform: translateX(-100%);
}

.wipe-overlay.active {
    animation: wipeAcross 200ms cubic-bezier(.7, .1, .2, 1) forwards;
}

@keyframes wipeAcross {
    0%   { transform: translateX(-100%); opacity: 0; }
    20%  { opacity: 1; }
    80%  { opacity: 1; }
    100% { transform: translateX(100%); opacity: 0; }
}
```

- [ ] **Step 3: Create `incarnation/src/wipeOverlay.js`**

```js
/**
 * wipeOverlay.js — 200ms red-diagonal wipe shown during persona swap.
 *
 * Usage:
 *   const wipe = new WipeOverlay(document.getElementById('wipe-overlay'));
 *   await wipe.play();
 *   // safe to swap models now
 */
export class WipeOverlay {
    constructor(el) {
        this.el = el;
    }

    /** Trigger the animation; resolves when it finishes (~200 ms). */
    play() {
        if (!this.el) return Promise.resolve();
        return new Promise((resolve) => {
            const onEnd = () => {
                this.el.removeEventListener('animationend', onEnd);
                this.el.classList.remove('active');
                resolve();
            };
            this.el.addEventListener('animationend', onEnd);
            // Force a reflow so re-adding the class restarts the animation.
            void this.el.offsetWidth;
            this.el.classList.add('active');
        });
    }
}
```

- [ ] **Step 4: Add `unloadModel()` to `Incarnation`**

In `incarnation/src/incarnation.js`, find the `Incarnation` class. Locate the `loadPersona` (or `_loadModel`) method — wherever the VRM gets installed onto the scene. Add a sibling method:

```js
    /**
     * Unload the currently-loaded VRM. Used during persona swap so the
     * scene is clean before the new VRM is loaded.
     */
    unloadModel() {
        if (this.vrm) {
            this.scene.remove(this.vrm.scene);
            this.vrm = null;
        }
        if (this.model) {
            this.scene.remove(this.model);
            this.model = null;
        }
        if (this.animationManager) {
            this.animationManager.stop();
            this.animationManager = null;
        }
    }
```

(If `this.vrm`, `this.model`, or `this.animationManager` aren't the right attribute names, adjust to match the existing `loadPersona`/`loadModel` code in the same file.)

Also extend `handleCommand` to dispatch on a new `unload_model` type. Find the `switch (type)` block and add a new case:

```js
            case 'unload_model':
                this.unloadModel();
                break;
```

- [ ] **Step 5: Wire the wipe + persona_changed in `viewer.js`**

In `incarnation/src/viewer.js`, alongside the other imports, add:

```js
import { WipeOverlay } from './wipeOverlay.js';
```

Just below the existing const declarations near the top (after `const personasRegistry = new PersonasRegistry();`), add:

```js
const wipeOverlay = new WipeOverlay(document.getElementById('wipe-overlay'));
```

Add a new connection listener block near the existing `persona_active` handler:

```js
connection.addEventListener('persona_changed', async (e) => {
    const ok = e.detail?.ok;
    if (!ok) {
        console.warn('[viewer] persona_changed error:', e.detail?.error);
        return;
    }
    const persona = e.detail?.persona;
    if (!persona) return;

    // If the new persona's id matches the currently-bound activePersona,
    // it's an idempotent swap — no wipe / unload needed.
    if (persona.name === activePersona.name) {
        console.log('[viewer] persona_changed (same persona, no wipe)');
        return;
    }

    console.log('[viewer] persona_changed → swap:', persona.name);
    // Visual: kick off the wipe; in parallel the server will emit
    // unload_model + load_model. The wipe is purely cosmetic — the
    // unload/load handlers fire whenever they arrive on the WS.
    wipeOverlay.play();
});

connection.addEventListener('unload_model', () => {
    incarnation.handleCommand('unload_model', {});
    safeTransition(State.EMPTY);
});
```

- [ ] **Step 6: Verify**

```bash
make test-js 2>&1 | tail -5
```

Expected: still 71 passed.

- [ ] **Step 7: Commit**

```bash
git add incarnation/src/viewer.js incarnation/src/incarnation.js incarnation/src/wipeOverlay.js incarnation/styles/viewer.css incarnation/index.html
git commit -m "feat(viewer): persona-swap wipe overlay + unload_model handler"
```

---

## Task 11: `?persona=` URL boot + `is_default` fallback in viewer

**Files:**
- Modify: `incarnation/src/viewer.js`

Once the personas list arrives, the viewer should send `set_active_persona` with the URL's `?persona=` param if present, else the registry's `findDefault()` result. This makes `?persona=silver`, `?persona=rin`, etc. actually work.

- [ ] **Step 1: Send set_active_persona after personas_list arrives**

In `incarnation/src/viewer.js`, find the existing `personas_list` listener (added in Task 9):

```js
connection.addEventListener('personas_list', (e) => {
    personasRegistry.replaceAll(e.detail?.personas || []);
    console.log('[viewer] personas_list:', personasRegistry.all().map((p) => p.id));
});
```

Replace with:

```js
connection.addEventListener('personas_list', (e) => {
    personasRegistry.replaceAll(e.detail?.personas || []);
    console.log('[viewer] personas_list:', personasRegistry.all().map((p) => p.id));

    // Boot resolution: honor ?persona= URL param if it matches a known id;
    // else fall back to the registry's default; else do nothing (server
    // stays on whatever --persona it was launched with).
    const wanted = config.persona && personasRegistry.get(config.persona)
        ? personasRegistry.get(config.persona)
        : personasRegistry.findDefault();
    if (wanted && wanted.id) {
        console.log('[viewer] boot persona:', wanted.id);
        connection.send('set_active_persona', { id: wanted.id });
    }
});
```

- [ ] **Step 2: Manual smoke**

`make test-js 2>&1 | tail -5` should still show 71 passed.

Manual: launch the stack (Whisper + Python + Vite), open `http://localhost:5173/?persona=rin` (after seeding a Rin persona). Console should log `boot persona: rin` and the model should swap to Rin's VRM.

- [ ] **Step 3: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "feat(viewer): URL ?persona= + is_default boot resolution"
```

---

## Task 12: Intro-anim replay on same-persona re-summon

**Files:**
- Modify: `playAIdes.py` (`_handle_incarnation_message` set_active_persona handler)
- Test: `tests/integration/test_set_active_persona_ws.py` (extend)

When the same persona is re-summoned from EMPTY (e.g. user said "Hey Silver" while dismissed), the server should emit `play_animation` for the intro animation so it replays. Different-persona swap is already covered: the new model load triggers the existing post-load animation flow.

- [ ] **Step 1: Write the failing test**

In `tests/integration/test_set_active_persona_ws.py`, append to `TestSetActivePersonaWS`:

```python
    def test_replays_intro_on_same_persona_resummon(self, play, tmp_personas_dir):
        """Same-persona set_active_persona should fire play_animation for
        the intro_animation so re-summon plays the greeting."""
        # The active persona is `testbot`. Give it an intro_animation.
        # (The initial persona_file fixture seeds a minimal persona without one;
        # we patch in a fresh persona.json.)
        active_id = play.current_persona.name.strip().lower().replace(" ", "_")
        avatar_dir = tmp_personas_dir / active_id
        avatar_dir.mkdir(exist_ok=True)
        (avatar_dir / "persona.json").write_text(json.dumps({
            "name": play.current_persona.name,
            "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female",
            "language": "English",
            "avatar": {"model_url": "m.vrm", "intro_animation": "wave"},
        }))
        # Re-load the persona so the new intro_animation is in current_persona.
        play.set_persona(active_id)

        # Clear command log to focus on what the resummon emits.
        play.incarnation_server.commands.clear()

        play._handle_incarnation_message({
            "type": "set_active_persona",
            "payload": {"id": active_id},
        })

        cmds = play.incarnation_server.commands
        plays = [(c, p) for c, p in cmds if c == "play_animation"]
        assert len(plays) == 1
        assert plays[0][1]["name"] == "wave"
        assert plays[0][1]["loop"] is False
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "(FAILED|test_replays_intro_on_same_persona_resummon)" | head
```

Expected: 1 failure (no play_animation is emitted on idempotent set_persona).

- [ ] **Step 3: Add the intro replay**

In `playAIdes.py`, in the `set_active_persona` handler (added in Task 5), find the section that emits `unload_model` / `load_model` for different personas. Replace that block with:

```python
            if prev_id != requested_id:
                self.incarnation_server.send_command("unload_model", {})
                if persona.avatar and persona.avatar.model_url:
                    self.incarnation_server.send_command("load_model", {
                        "url": persona.avatar.model_url,
                    })
                if persona.avatar and persona.avatar.background_url:
                    self.incarnation_server.send_command("set_background", {
                        "url": persona.avatar.background_url,
                    })
                # Different persona: post-load animation flow handles intro
                # replay once load_default_animations finishes (existing
                # Phase-1 code).
            else:
                # Same persona re-summon (e.g. wake-after-dismiss). Model
                # is still loaded; just replay the intro clip directly.
                intro = (persona.avatar.intro_animation
                         if (persona.avatar) else None)
                if intro:
                    self.incarnation_server.send_command("play_animation", {
                        "name": intro,
                        "loop": False,
                    })
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `130 passed, 4 deselected` (was 129; +1 new).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_set_active_persona_ws.py
git commit -m "feat: replay intro_animation on same-persona resummon"
```

---

## Task 13: End-to-end smoke + final review

**Files:**
- None — verification only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `130 passed, 4 deselected`.

- [ ] **Step 2: JS tests still green**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files 6 passed (6) / Tests 71 passed (71)`.

- [ ] **Step 3: Two-TV smoke**

Phase 4's headline feature is multi-TV memory sharing. The simplest test is two browser tabs against the same backend.

```bash
# Terminal 1
make whisper

# Terminal 2
python main.py --persona personas/silver/persona.json --use_avatar

# Terminal 3
npm --prefix incarnation run dev
```

Open TWO browser tabs:
- Tab A: `http://localhost:5173/?activation=continuous`
- Tab B: `http://localhost:5173/?activation=continuous`

Click each tab once to grant mic. Both should connect, receive `personas_list`, and bind to Silver via boot resolution.

In Tab A, say *"Hello Silver, what's the weather?"* → Silver replies. Verify:
- Tab A's subtitle shows the reply
- Tab B's subtitle ALSO shows the same reply (broadcast routing via persona binding works)
- DevTools Network → WS frames in Tab B show `assistant_message` arriving without sending `user_input`

**Cross-persona swap:** seed a second persona (`personas/rin/persona.json`) with `wake_words: ["hey rin"]` and a different `model_url`. In Tab A, say *"Hey Rin, are you there?"*. Verify:
- Red diagonal wipe sweeps across Tab A's canvas
- Silver's VRM unloads, Rin's VRM loads
- Tab A is now bound to Rin (DevTools: `[viewer] persona_changed → swap: Rin`)
- Tab B is STILL bound to Silver (no wipe)
- Subsequent *"Silver, hi"* in Tab A swaps Tab A back to Silver — Tab B still bound to Silver throughout

**Dismiss + history persistence:**
1. Talk to Silver in Tab A — generate ~3 turns
2. *"Goodnight Silver"* in Tab A → canvas fades, EMPTY
3. Stop Python (Ctrl-C in T2). Restart `python main.py ...`.
4. Reload Tab A. *"Hey Silver"* → re-summons.
5. Ask Silver about something from earlier — she should reference it (history loaded from `personas/silver/chat_history.json`).

- [ ] **Step 4: Self-review against spec §10 Phase 4 row**

| Spec bullet | Where |
|---|---|
| `set_active_persona` WS + `PlayAIdes.set_persona()` | Tasks 3, 5 |
| Wake-word matching expands to all personas; cross-persona swap | Tasks 8, 9 |
| Red-diagonal wipe on swap | Task 10 |
| Per-persona chat history persisted in `personas/<id>/chat_history.json`, capped N=80, loaded on summon | Tasks 2, 3, 5 |
| Client-binding registry routes `assistant_message` to all bound TVs | Tasks 4, 6 |
| `is_default` boot resolution | Tasks 1, 11 |

- [ ] **Step 5: Final consistency check**

- `set_active_persona` literal — used identically in `viewer.js`, `incarnation_server.py` WS endpoint, and `_handle_incarnation_message`.
- `persona_changed` — server emits, client receives — same shape `{ok, persona, error?}`.
- `history_loaded` — server emits `{persona_id, history}`, client (Phase 5) will rehydrate.
- `unload_model` — Incarnation handles it, viewer dispatches it.
- `chat_histories` — server-side dict; corresponds 1:1 with on-disk `personas/<id>/chat_history.json`.
- `CHAT_HISTORY_CAP = 80` — single source of truth in playAIdes.py.
- `PersonasRegistry` — single class name across module, tests, and orchestrator.

- [ ] **Step 6: No commit (process marker)**

---

## Self-review checklist (run before marking phase 4 done)

- [ ] **Spec coverage** — every bullet in spec §10 Phase 4 row maps to a task. Checked above.
- [ ] **No placeholders** — search for `TBD`, `TODO`, `FIXME`. None.
- [ ] **Type / name consistency**:
  - `set_active_persona`, `persona_changed`, `history_loaded`, `unload_model`, `dismiss_persona` — exact WS message types both sides.
  - `CHAT_HISTORY_CAP` — single Python constant; no magic 80s elsewhere.
  - `chat_histories` — same name in `PlayAIdes` and tests.
  - `personasRegistry`, `wipeOverlay`, `WipeOverlay`, `PersonasRegistry` — same casing across files and tests.
- [ ] **Phase boundaries respected** — no chat-panel UI, no HDRI/3D backgrounds, no `?settings=` page. All Phase 5 territory.
- [ ] **Atomicity** — `_save_history` uses tempfile + os.replace per spec §6.
- [ ] **Idempotency** — `set_persona(id)` is a no-op if id matches active (still loads history).
