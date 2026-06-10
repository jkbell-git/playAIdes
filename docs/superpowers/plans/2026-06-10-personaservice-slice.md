# PersonaService Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the persona domain (CRUD, chat-history I/O, triggers) out of the `PlayAIdes` god object into `PersonaService` + two stores + an `/api/v1/personas` router, and migrate creator.js persona CRUD from WS frames to REST so the WS dispatcher CRUD branches are deleted, not delegated.

**Architecture:** Approach A from the spec — `backend/stores/personas.py` + `backend/stores/history.py` (pure file I/O, traversal guard at the filesystem layer) composed by `backend/services/persona.py` (domain rules: slug, validated writes, typed exceptions, history cache+cap) behind `backend/api/personas.py` (`/api/v1`, `require_api_key`, `request.app.state.persona_service` — the slice-2 pattern). `PlayAIdes` keeps one-line delegation shims for internal callers; `ConversationService` is rewired to a real by-id load (D6). A new `incarnation/src/apiClient.js` (the `consoleApi.js` mold) carries creator.js.

**Tech Stack:** Python, FastAPI, pydantic v2, pytest (via `bin/test`, dockerized); JS with vitest (`incarnation/`). Spec: `docs/superpowers/specs/2026-06-10-personaservice-slice-design.md` (commit `c5bf1d1`). Parent: `docs/superpowers/specs/2026-06-09-backend-frontend-architecture-redesign.md`.

**Branch:** create `personaservice-slice` off `main` (Task 1 Step 0). Suite baseline on `main`: 341 passed / 5 skipped.

---

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `backend/stores/personas.py` | Create | `PersonaStore` — pure file I/O over `personas/<id>/persona.json`; `_check_id` traversal guard. |
| `backend/stores/history.py` | Create | `HistoryStore` — pure file I/O over `personas/<id>/chat_history.json`; atomic writes ported verbatim. |
| `backend/services/persona.py` | Create | `PersonaService` + `PersonaNotFound`/`PersonaExists`/`PersonaActive` + `slug()`. Domain owner: validated CRUD, history cache+cap, triggers. |
| `backend/api/personas.py` | Create | The `/api/v1/personas` router; status-code mapping per the spec table. |
| `persona.py` | Modify | Add `AnimationClip` model + `Persona.animations` (discovered gap — see Task 3 rationale). |
| `playAIdes.py` | Modify | Construct stores+service; delegation shims; `chat_histories` property; ConversationService rewire (D6); delete 4 WS dispatcher CRUD branches. |
| `incarnation_server.py` | Modify | Import + mount the personas router. |
| `incarnation/src/apiClient.js` | Create | Shared REST client seed (`ApiClient`), persona surface. |
| `incarnation/src/creator.js` | Modify | CRUD WS send/listener pairs → `ApiClient` calls; voice frames + REST uploads untouched. |
| `tests/unit/test_persona_store.py` | Create | PersonaStore unit tests. |
| `tests/unit/test_history_store.py` | Create | HistoryStore unit tests. |
| `tests/unit/test_persona_service.py` | Create | PersonaService unit tests (real stores on tmp dirs). |
| `tests/unit/test_personas_api.py` | Create | Router unit tests (fake service; every status mapping). |
| `tests/unit/test_persona.py` | Modify | Add the `animations` round-trip test. |
| `tests/unit/test_playaides_persona_ops.py` | Modify | Replace the silent-create-on-update test (old behavior = D7 bug); add collision test. |
| `tests/unit/test_playaides_chat.py` | Modify | Add the D6 pin test (`run_turn` targets the requested persona). |
| `tests/unit/test_ws_crud_removed.py` | Create | Deleted dispatcher branches are inert; `get_personas` still answers. |
| `tests/integration/test_personas_rest.py` | Create | Full CRUD+triggers flow on the real IncarnationServer app. |
| `incarnation/src/apiClient.test.js` | Create | vitest tests in the `consoleApi.test.js` mold. |
| `CONTINUITY.md` | Modify | Closure: Now & Next, Decisions, TODO; unpark note for the trigger console. |

**Out of scope (do NOT touch):** activation (`set_persona` / `set_active_persona` choreography), the upload WS branches (`model_uploaded`/`animation_uploaded`), voice frames (`design_voice`/`test_voice`), `incarnation/src/viewer.js` (its `get_personas` stays WS), history REST endpoints, the trigger-console UI, memories/VectorDB, refactoring `consoleApi.js` onto `apiClient.js`.

---

## Task 1: `PersonaStore` — pure persona-file I/O + traversal guard

**Files:**
- Create: `backend/stores/personas.py`
- Test: `tests/unit/test_persona_store.py`

- [ ] **Step 0: Create the branch**

```bash
git checkout -b personaservice-slice main
```

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_persona_store.py`:

```python
"""Hermetic unit tests for backend.stores.personas.PersonaStore."""
from __future__ import annotations

import json

import pytest

from backend.stores.personas import PersonaStore


@pytest.fixture
def store(tmp_path):
    return PersonaStore(base_dir=tmp_path / "personas")


def test_write_read_round_trip(store):
    store.write("alpha", {"name": "Alpha"})
    assert store.read("alpha") == {"name": "Alpha"}
    assert store.exists("alpha") is True


def test_read_missing_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.read("ghost")
    assert store.exists("ghost") is False


def test_list_ids_only_dirs_with_persona_json(store, tmp_path):
    store.write("alpha", {"name": "A"})
    store.write("beta", {"name": "B"})
    (tmp_path / "personas" / "empty_dir").mkdir()
    (tmp_path / "personas" / "stray.txt").write_text("hi")
    assert store.list_ids() == ["alpha", "beta"]


def test_list_ids_creates_base_dir(tmp_path):
    base = tmp_path / "not_yet"
    store = PersonaStore(base_dir=base)
    assert store.list_ids() == []
    assert base.is_dir()


def test_delete_removes_directory(store, tmp_path):
    store.write("alpha", {"name": "A"})
    store.delete("alpha")
    assert not (tmp_path / "personas" / "alpha").exists()


def test_delete_missing_raises_keyerror(store):
    with pytest.raises(KeyError):
        store.delete("ghost")


@pytest.mark.parametrize("bad_id", ["", ".", "..", "../etc", "a/b", "a\\b"])
def test_traversal_guard_rejects(store, bad_id):
    with pytest.raises(ValueError):
        store.read(bad_id)
    with pytest.raises(ValueError):
        store.write(bad_id, {})
    with pytest.raises(ValueError):
        store.delete(bad_id)
    with pytest.raises(ValueError):
        store.exists(bad_id)


def test_write_pretty_prints(store, tmp_path):
    store.write("alpha", {"name": "A"})
    text = (tmp_path / "personas" / "alpha" / "persona.json").read_text()
    assert text == json.dumps({"name": "A"}, indent=2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test pytest tests/unit/test_persona_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.stores.personas'`.

- [ ] **Step 3: Create `backend/stores/personas.py`**

```python
"""Pure file I/O for persona documents (personas/<id>/persona.json).

No Pydantic, no business rules — validation and domain logic live in
backend/services/persona.py. The path-traversal guard lives HERE because it
protects the filesystem (spec 2026-06-10, component 1). Constructor-arg base
dir so tests run on tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Union


def _check_id(persona_id: str) -> None:
    """Reject ids that could escape the base directory (ported from
    PlayAIdes.delete_persona / _history_path)."""
    if (not persona_id or "/" in persona_id or "\\" in persona_id
            or persona_id in {".", ".."}):
        raise ValueError(f"Suspicious persona_id: {persona_id!r}")


class PersonaStore:
    def __init__(self, base_dir: Union[str, Path] = "personas"):
        self.base_dir = Path(base_dir)

    def _dir(self, persona_id: str) -> Path:
        _check_id(persona_id)
        return self.base_dir / persona_id

    def list_ids(self) -> list:
        """Ids of subdirectories containing a persona.json. Creates the base
        dir if absent (ported from PlayAIdes.list_personas)."""
        os.makedirs(self.base_dir, exist_ok=True)
        return sorted(
            d.name for d in self.base_dir.iterdir()
            if d.is_dir() and (d / "persona.json").exists()
        )

    def exists(self, persona_id: str) -> bool:
        return (self._dir(persona_id) / "persona.json").exists()

    def read(self, persona_id: str) -> dict:
        path = self._dir(persona_id) / "persona.json"
        if not path.exists():
            raise KeyError(persona_id)
        with open(path) as f:
            return json.load(f)

    def write(self, persona_id: str, data: dict) -> None:
        d = self._dir(persona_id)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "persona.json", "w") as f:
            json.dump(data, f, indent=2)

    def delete(self, persona_id: str) -> None:
        d = self._dir(persona_id)
        if not d.is_dir():
            raise KeyError(persona_id)
        shutil.rmtree(d)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test pytest tests/unit/test_persona_store.py -q`
Expected: PASS (8 tests, one parametrized).

- [ ] **Step 5: Commit**

```bash
git add backend/stores/personas.py tests/unit/test_persona_store.py
git commit -m "feat(stores): PersonaStore — pure persona-file I/O with traversal guard"
```

---

## Task 2: `HistoryStore` — chat-history I/O with atomic writes

**Files:**
- Create: `backend/stores/history.py`
- Test: `tests/unit/test_history_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_history_store.py`:

```python
"""Hermetic unit tests for backend.stores.history.HistoryStore."""
from __future__ import annotations

import json
import os

import pytest

from backend.stores.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(base_dir=tmp_path / "personas")


def test_missing_file_reads_empty(store):
    assert store.read("nobody") == []


def test_write_read_round_trip(store):
    history = [{"role": "user", "content": "hi"}]
    store.write("alpha", history)
    assert store.read("alpha") == history


def test_corrupt_file_warns_and_reads_empty(store, tmp_path):
    d = tmp_path / "personas" / "alpha"
    d.mkdir(parents=True)
    (d / "chat_history.json").write_text("{not json")
    assert store.read("alpha") == []


def test_write_is_atomic_and_cleans_up_tempfile(store, tmp_path, monkeypatch):
    store.write("alpha", [{"role": "user", "content": "before"}])

    def boom(*a, **kw):
        raise OSError("disk full simulation")
    monkeypatch.setattr(os, "replace", boom)

    with pytest.raises(OSError):
        store.write("alpha", [{"role": "user", "content": "after"}])

    path = tmp_path / "personas" / "alpha" / "chat_history.json"
    assert json.loads(path.read_text()) == [{"role": "user", "content": "before"}]
    leftovers = list((tmp_path / "personas" / "alpha").glob(".chat_history.*.json.tmp"))
    assert leftovers == [], f"orphan tempfile(s): {leftovers}"


def test_delete_removes_file_and_tolerates_missing(store, tmp_path):
    store.write("alpha", [{"role": "user", "content": "x"}])
    store.delete("alpha")
    assert not (tmp_path / "personas" / "alpha" / "chat_history.json").exists()
    store.delete("alpha")  # second delete is a no-op


@pytest.mark.parametrize("bad_id", ["", ".", "..", "a/b", "a\\b"])
def test_traversal_guard_rejects(store, bad_id):
    with pytest.raises(ValueError):
        store.read(bad_id)
    with pytest.raises(ValueError):
        store.write(bad_id, [])
    with pytest.raises(ValueError):
        store.delete(bad_id)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test pytest tests/unit/test_history_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.stores.history'`.

- [ ] **Step 3: Create `backend/stores/history.py`**

```python
"""Pure file I/O for per-persona chat history (personas/<id>/chat_history.json).

Atomic writes (sibling tempfile + os.replace, unlink-on-failure) ported
verbatim from PlayAIdes._save_history so a mid-write crash never corrupts the
file. Corrupt/unreadable history degrades to empty with a warning (ported from
PlayAIdes._load_history).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Union

from backend.stores.personas import _check_id

logger = logging.getLogger(__name__)


class HistoryStore:
    def __init__(self, base_dir: Union[str, Path] = "personas"):
        self.base_dir = Path(base_dir)

    def _path(self, persona_id: str) -> Path:
        _check_id(persona_id)
        return self.base_dir / persona_id / "chat_history.json"

    def read(self, persona_id: str) -> list:
        path = self._path(persona_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s — starting empty", path, e)
            return []

    def write(self, persona_id: str, history: list) -> None:
        path = self._path(persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling tempfile, then atomically rename over the target.
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

    def delete(self, persona_id: str) -> None:
        path = self._path(persona_id)
        if path.exists():
            path.unlink()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test pytest tests/unit/test_history_store.py -q`
Expected: PASS (6 tests, one parametrized).

- [ ] **Step 5: Commit**

```bash
git add backend/stores/history.py tests/unit/test_history_store.py
git commit -m "feat(stores): HistoryStore — atomic chat-history I/O"
```

---

## Task 3: Declare `Persona.animations` (gap found during planning)

**Why (not in the spec):** the `animation_uploaded` WS branch writes a top-level `animations: [{name, url}]` key into persona.json, and creator.js round-trips it (`buildPersonaPayload`, `renderCustomAnims`). The `Persona` model does not declare the field, and pydantic v2 silently drops undeclared keys in `model_dump()`. D3 (validate ALL writes) would therefore silently destroy every persona's custom animations on the first validated update. Declaring the field is required for "internal callers behave as before".

**Files:**
- Modify: `persona.py` (add `AnimationClip`; add field to `Persona`)
- Test: `tests/unit/test_persona.py` (append one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_persona.py`:

```python
def test_animations_round_trip_through_model():
    """Custom uploaded clips (top-level `animations`) must survive a validated
    write (D3) — previously undeclared, so model_dump() dropped them."""
    from persona import Persona
    data = {
        "name": "T", "back_ground": "bg", "psyche": {"traits": []},
        "gender": "Female",
        "animations": [{"name": "wave", "url": "outputs/anims/wave.vrma"}],
    }
    dumped = Persona(**data).model_dump()
    assert dumped["animations"] == [{"name": "wave", "url": "outputs/anims/wave.vrma"}]
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test pytest tests/unit/test_persona.py -q`
Expected: FAIL — `KeyError: 'animations'` (the model dropped the key).

- [ ] **Step 3: Add the model + field in `persona.py`**

Insert after the `Memories` class (around line 38):

```python
class AnimationClip(BaseModel):
    """A custom uploaded animation bound to a persona (creator page /
    animation_uploaded). Top-level `animations` in persona.json."""
    name: str
    url: str
```

Add to the `Persona` class, after `memories: Optional[Memories] = None`:

```python
    animations: Optional[List[AnimationClip]] = None  # custom uploads (creator)
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_persona.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add persona.py tests/unit/test_persona.py
git commit -m "feat(persona): declare animations field so validated writes preserve it"
```

---

## Task 4: `PersonaService` — CRUD, typed exceptions, `get_model`

**Files:**
- Create: `backend/services/persona.py`
- Test: `tests/unit/test_persona_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_persona_service.py`:

```python
"""PersonaService unit tests — real stores on tmp dirs (hermetic)."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.services.persona import (
    PersonaActive, PersonaExists, PersonaNotFound, PersonaService, slug,
)
from backend.stores.history import HistoryStore
from backend.stores.personas import PersonaStore

VALID = {
    "name": "TestBot", "back_ground": "bg",
    "psyche": {"traits": []}, "gender": "Female", "language": "English",
}


@pytest.fixture
def base(tmp_path):
    return tmp_path / "personas"


@pytest.fixture
def svc(base):
    return PersonaService(
        persona_store=PersonaStore(base_dir=base),
        history_store=HistoryStore(base_dir=base),
        active_persona_id=lambda: "active_bot",
        history_cap=5,
    )


def _seed(base, pid, doc=None):
    d = base / pid
    d.mkdir(parents=True)
    (d / "persona.json").write_text(json.dumps(doc or VALID))


def test_slug_rule():
    assert slug("  New Friend ") == "new_friend"


class TestCrud:
    def test_create_writes_full_defaulted_doc(self, svc, base):
        out = svc.create("New Friend", "A brand new persona.")
        assert out["id"] == "new_friend"
        on_disk = json.loads((base / "new_friend" / "persona.json").read_text())
        assert on_disk["name"] == "New Friend"
        assert on_disk["back_ground"] == "A brand new persona."
        # Full defaulted document, not today's partial dict (D3):
        assert on_disk["triggers"] == [] and on_disk["skills"] == []
        assert on_disk["is_default"] is False
        assert "id" not in on_disk

    def test_create_collision_raises(self, svc, base):
        _seed(base, "testbot")
        with pytest.raises(PersonaExists):
            svc.create("TestBot", "again")          # slugs to "testbot"

    def test_get_injects_id_and_missing_raises(self, svc, base):
        _seed(base, "testbot")
        assert svc.get("testbot")["id"] == "testbot"
        with pytest.raises(PersonaNotFound):
            svc.get("ghost")

    def test_list_skips_corrupt_files(self, svc, base):
        _seed(base, "good")
        bad = base / "bad"
        bad.mkdir(parents=True)
        (bad / "persona.json").write_text("{nope")
        out = svc.list()
        assert [p["id"] for p in out] == ["good"]

    def test_update_missing_raises(self, svc):
        with pytest.raises(PersonaNotFound):
            svc.update("ghost", dict(VALID))

    def test_update_strips_id_and_validates(self, svc, base):
        _seed(base, "testbot")
        data = dict(VALID, id="testbot", back_ground="edited")
        out = svc.update("testbot", data)
        assert out["id"] == "testbot" and out["back_ground"] == "edited"
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert "id" not in on_disk and on_disk["back_ground"] == "edited"

    def test_update_invalid_doc_leaves_file_untouched(self, svc, base):
        _seed(base, "testbot")
        with pytest.raises(ValidationError):
            svc.update("testbot", {"name": "only a name"})
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert on_disk["back_ground"] == "bg"

    def test_update_preserves_animations(self, svc, base):
        # Pin for the Task-3 gap: validated writes must not drop custom clips.
        _seed(base, "testbot")
        data = dict(VALID, animations=[{"name": "wave", "url": "u.vrma"}])
        svc.update("testbot", data)
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert on_disk["animations"] == [{"name": "wave", "url": "u.vrma"}]

    def test_delete_guards(self, svc, base):
        with pytest.raises(PersonaNotFound):
            svc.delete("ghost")
        _seed(base, "active_bot")
        with pytest.raises(PersonaActive):
            svc.delete("active_bot")                 # injected callable matches

    def test_delete_removes_dir_and_cached_history(self, svc, base):
        _seed(base, "doomed")
        svc.load_history("doomed")
        assert "doomed" in svc.histories
        svc.delete("doomed")
        assert not (base / "doomed").exists()
        assert "doomed" not in svc.histories         # no resurrection on re-create

    def test_get_model_returns_persona(self, svc, base):
        from persona import Persona
        _seed(base, "testbot")
        p = svc.get_model("testbot")
        assert isinstance(p, Persona) and p.name == "TestBot"
        with pytest.raises(PersonaNotFound):
            svc.get_model("ghost")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test pytest tests/unit/test_persona_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.persona'`.

- [ ] **Step 3: Create `backend/services/persona.py`**

```python
"""PersonaService — the persona domain owner (spec 2026-06-10, D1–D7).

Composes the two pure-I/O stores. Every write round-trips through the
Persona/Trigger Pydantic models (D3), so an invalid document can never reach
disk; pydantic ValidationError propagates as itself (the router maps it to
422). The history cache + cap live here — single owner; PlayAIdes reads the
cache through its chat_histories property for the history_loaded WS frame.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from persona import Persona

logger = logging.getLogger(__name__)


class PersonaNotFound(Exception):
    """No persona with that id."""


class PersonaExists(Exception):
    """create() collided with an existing persona (D7: 409, not overwrite)."""


class PersonaActive(Exception):
    """delete() refused: the persona is currently active (D7: 409)."""


def slug(name: str) -> str:
    """The persona-id slug rule (single home, moved from create_persona)."""
    return name.strip().lower().replace(" ", "_")


class PersonaService:
    def __init__(self, persona_store, history_store,
                 active_persona_id: Callable[[], Optional[str]],
                 history_cap: int = 80):
        self._personas = persona_store
        self._history_store = history_store
        self._active_persona_id = active_persona_id
        self._history_cap = history_cap
        self._histories: Dict[str, List[dict]] = {}

    # ── CRUD ──────────────────────────────────────────────────────────────
    def list(self) -> List[dict]:
        """Every readable persona doc with "id" injected. Corrupt files are
        logged and skipped — one bad file must not take down the list."""
        out = []
        for pid in self._personas.list_ids():
            try:
                doc = self._personas.read(pid)
            except Exception as e:
                logger.error("Error reading persona %s: %s", pid, e)
                continue
            doc["id"] = pid
            out.append(doc)
        return out

    def get(self, persona_id: str) -> dict:
        try:
            doc = self._personas.read(persona_id)
        except KeyError:
            raise PersonaNotFound(persona_id)
        doc["id"] = persona_id
        return doc

    def get_model(self, persona_id: str) -> Persona:
        """Typed by-id load for internal consumers (ConversationService, D6)."""
        try:
            data = self._personas.read(persona_id)
        except KeyError:
            raise PersonaNotFound(persona_id)
        return Persona(**data)

    def create(self, name: str, description: str) -> dict:
        persona_id = slug(name)
        if self._personas.exists(persona_id):
            raise PersonaExists(persona_id)
        model = Persona(
            name=name,
            back_ground=description,
            psyche={"traits": []},
            gender="Female",
            language="English",
        )
        doc = model.model_dump()
        self._personas.write(persona_id, doc)
        doc["id"] = persona_id
        return doc

    def update(self, persona_id: str, data: dict) -> dict:
        if not self._personas.exists(persona_id):
            raise PersonaNotFound(persona_id)
        data = dict(data)
        data.pop("id", None)
        doc = Persona(**data).model_dump()   # ValidationError propagates (422)
        self._personas.write(persona_id, doc)
        doc["id"] = persona_id
        return doc

    def delete(self, persona_id: str) -> None:
        if not self._personas.exists(persona_id):
            raise PersonaNotFound(persona_id)
        if self._active_persona_id() == persona_id:
            raise PersonaActive(persona_id)
        self._personas.delete(persona_id)      # rmtree removes chat history too
        self._histories.pop(persona_id, None)  # no resurrection on re-create
```

(History + triggers methods land in Task 5 — the tests above only touch `load_history`/`histories` via `test_delete_removes_dir_and_cached_history`; add this minimal pair now so Task 4's tests pass:)

```python
    # ── History (full surface in the next commit) ─────────────────────────
    @property
    def histories(self) -> Dict[str, List[dict]]:
        """The in-memory cache. PlayAIdes' chat_histories property returns
        this same dict; the history_loaded activation frame reads it."""
        return self._histories

    def load_history(self, persona_id: str) -> List[dict]:
        if persona_id in self._histories:
            return self._histories[persona_id]
        history = self._history_store.read(persona_id)
        if len(history) > self._history_cap:
            history = history[-self._history_cap:]
        self._histories[persona_id] = history
        return history
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test pytest tests/unit/test_persona_service.py -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/persona.py tests/unit/test_persona_service.py
git commit -m "feat(service): PersonaService CRUD — validated writes, typed exceptions, get_model"
```

---

## Task 5: `PersonaService` — history cache/cap + triggers

**Files:**
- Modify: `backend/services/persona.py`
- Test: `tests/unit/test_persona_service.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_persona_service.py`:

```python
class TestHistory:
    def test_load_caps_and_caches_same_object(self, svc, base):
        d = base / "alpha"
        d.mkdir(parents=True)
        big = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        (d / "chat_history.json").write_text(json.dumps(big))
        loaded = svc.load_history("alpha")
        assert len(loaded) == 5                      # history_cap=5 fixture
        assert loaded[-1] == {"role": "user", "content": "m19"}
        assert loaded is svc.histories["alpha"]      # same object: in-place
                                                     # mutation hits the cache

    def test_load_is_idempotent_and_keeps_mutations(self, svc):
        first = svc.load_history("alpha")
        first.append({"role": "user", "content": "hi"})
        assert svc.load_history("alpha") is first

    def test_save_persists_cache_and_delete_clears_both(self, svc, base):
        svc.load_history("alpha").append({"role": "user", "content": "ping"})
        svc.save_history("alpha")
        path = base / "alpha" / "chat_history.json"
        assert json.loads(path.read_text()) == [{"role": "user", "content": "ping"}]
        svc.delete_history("alpha")
        assert "alpha" not in svc.histories
        assert not path.exists()


class TestTriggers:
    def test_get_triggers_defaults_empty(self, svc, base):
        _seed(base, "testbot")                       # VALID has no triggers key
        assert svc.get_triggers("testbot") == []
        with pytest.raises(PersonaNotFound):
            svc.get_triggers("ghost")

    def test_replace_validates_rows_and_persists(self, svc, base):
        _seed(base, "testbot")
        trig = [{"on": {"phrase": "show camera"},
                 "do": {"skill": "show_pip", "params": {"source": "cam.1"}}}]
        out = svc.replace_triggers("testbot", trig)
        assert out[0]["on"]["phrase"] == "show camera"
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert on_disk["triggers"][0]["do"]["skill"] == "show_pip"

    def test_replace_invalid_row_leaves_file_untouched(self, svc, base):
        _seed(base, "testbot")
        with pytest.raises(ValidationError):
            # TriggerOn requires phrase or event — {} is invalid.
            svc.replace_triggers("testbot", [{"on": {}, "do": {"skill": "x"}}])
        on_disk = json.loads((base / "testbot" / "persona.json").read_text())
        assert "triggers" not in on_disk or on_disk["triggers"] == []
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `bin/test pytest tests/unit/test_persona_service.py -q`
Expected: FAIL — `AttributeError` for `save_history` / `delete_history` / `get_triggers` / `replace_triggers`.

- [ ] **Step 3: Complete the service**

In `backend/services/persona.py`, replace the section comment `# ── History (full surface in the next commit) ──` with `# ── History (cache + cap, moved from PlayAIdes — single owner) ──` and append below `load_history`:

```python
    def save_history(self, persona_id: str) -> None:
        """Persist the cached list (atomic via the store)."""
        self._history_store.write(persona_id, self._histories.get(persona_id, []))

    def delete_history(self, persona_id: str) -> None:
        self._histories.pop(persona_id, None)
        self._history_store.delete(persona_id)

    # ── Triggers (D2: whole-list replace, no row ids) ────────────────────
    def get_triggers(self, persona_id: str) -> List[dict]:
        return self.get(persona_id).get("triggers") or []

    def replace_triggers(self, persona_id: str, triggers: List[dict]) -> List[dict]:
        """Validate the WHOLE persona with the new list spliced in (each row
        through Trigger, and the doc stays coherent — spec D2/D3), write,
        return the new list."""
        try:
            doc = self._personas.read(persona_id)
        except KeyError:
            raise PersonaNotFound(persona_id)
        doc.pop("id", None)
        doc["triggers"] = triggers
        validated = Persona(**doc).model_dump()  # ValidationError propagates
        self._personas.write(persona_id, validated)
        return validated["triggers"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_persona_service.py -q`
Expected: PASS (18 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/persona.py tests/unit/test_persona_service.py
git commit -m "feat(service): PersonaService history cache/cap + whole-list trigger replace"
```

---

## Task 6: `backend/api/personas.py` — the `/api/v1/personas` router

**Files:**
- Create: `backend/api/personas.py`
- Test: `tests/unit/test_personas_api.py`

> ⚠️ **Pydantic trap this task pins:** `pydantic.ValidationError` subclasses `ValueError`. The handlers must catch `ValidationError` (→ 422) **before** `ValueError` (the stores' traversal guard, → 404), or every invalid body becomes a 404.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_personas_api.py`:

```python
"""Router unit tests for backend/api/personas.py — every status mapping in the
spec table, against a scriptable fake service injected via app.state."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.testclient import TestClient

from backend.api.personas import router
from backend.services.persona import PersonaActive, PersonaExists, PersonaNotFound
from persona import Persona


def _validation_error() -> ValidationError:
    try:
        Persona()                      # missing required fields
    except ValidationError as e:
        return e
    raise AssertionError("unreachable")


class FakePersonaService:
    """Each method returns its scripted value, or raises its scripted error."""

    def __init__(self):
        self.behavior = {}
        self.calls = []

    def _do(self, method, default, *args):
        self.calls.append((method, args))
        b = self.behavior.get(method)
        if isinstance(b, Exception):
            raise b
        return default if b is None else b

    def list(self): return self._do("list", [{"id": "a"}])
    def get(self, pid): return self._do("get", {"id": pid}, pid)
    def create(self, name, description):
        return self._do("create", {"id": "x", "name": name}, name, description)
    def update(self, pid, data):
        return self._do("update", {"id": pid, **data}, pid, data)
    def delete(self, pid): return self._do("delete", None, pid)
    def get_triggers(self, pid): return self._do("get_triggers", [], pid)
    def replace_triggers(self, pid, triggers):
        return self._do("replace_triggers", triggers, pid, triggers)


@pytest.fixture
def fake_svc():
    return FakePersonaService()


@pytest.fixture
def client(fake_svc):
    app = FastAPI()
    app.include_router(router)
    app.state.persona_service = fake_svc
    return TestClient(app)


def test_list_ok(client):
    r = client.get("/api/v1/personas")
    assert r.status_code == 200 and r.json() == [{"id": "a"}]


def test_create_201_and_409(client, fake_svc):
    r = client.post("/api/v1/personas", json={"name": "X", "description": "d"})
    assert r.status_code == 201
    assert fake_svc.calls[-1] == ("create", ("X", "d"))
    fake_svc.behavior["create"] = PersonaExists("x")
    assert client.post("/api/v1/personas", json={"name": "X"}).status_code == 409


def test_get_ok_404_and_traversal_404(client, fake_svc):
    assert client.get("/api/v1/personas/a").status_code == 200
    fake_svc.behavior["get"] = PersonaNotFound("ghost")
    assert client.get("/api/v1/personas/ghost").status_code == 404
    fake_svc.behavior["get"] = ValueError("Suspicious persona_id")
    r = client.get("/api/v1/personas/dots")
    assert r.status_code == 404
    assert "Suspicious" not in r.json()["detail"]       # guard details not leaked


def test_put_ok_404_and_422(client, fake_svc):
    assert client.put("/api/v1/personas/a", json={"name": "X"}).status_code == 200
    fake_svc.behavior["update"] = PersonaNotFound("ghost")
    assert client.put("/api/v1/personas/ghost", json={"name": "X"}).status_code == 404
    # The except-order pin: ValidationError must map to 422, not the ValueError 404.
    fake_svc.behavior["update"] = _validation_error()
    assert client.put("/api/v1/personas/a", json={"name": "X"}).status_code == 422


def test_delete_204_404_409(client, fake_svc):
    r = client.delete("/api/v1/personas/a")
    assert r.status_code == 204 and r.content == b""
    fake_svc.behavior["delete"] = PersonaNotFound("ghost")
    assert client.delete("/api/v1/personas/ghost").status_code == 404
    fake_svc.behavior["delete"] = PersonaActive("a")
    assert client.delete("/api/v1/personas/a").status_code == 409


def test_triggers_get_and_put(client, fake_svc):
    assert client.get("/api/v1/personas/a/triggers").status_code == 200
    fake_svc.behavior["get_triggers"] = PersonaNotFound("ghost")
    assert client.get("/api/v1/personas/ghost/triggers").status_code == 404

    trig = [{"on": {"phrase": "p"}, "do": {"skill": "s", "params": {}}}]
    r = client.put("/api/v1/personas/a/triggers", json=trig)
    assert r.status_code == 200 and r.json() == trig
    assert fake_svc.calls[-1] == ("replace_triggers", ("a", trig))  # bare array body
    fake_svc.behavior["replace_triggers"] = _validation_error()
    assert client.put("/api/v1/personas/a/triggers", json=trig).status_code == 422


def test_503_when_service_absent():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/v1/personas").status_code == 503


def test_401_when_key_set_and_no_header(fake_svc, with_api_key):
    app = FastAPI()
    app.include_router(router)
    app.state.persona_service = fake_svc
    client = TestClient(app)
    assert client.get("/api/v1/personas").status_code == 401
    ok = client.get("/api/v1/personas",
                    headers={"Authorization": f"Bearer {with_api_key}"})
    assert ok.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test pytest tests/unit/test_personas_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.api.personas'`.

- [ ] **Step 3: Create `backend/api/personas.py`**

```python
"""REST surface for the persona domain (spec 2026-06-10, component 4).

Mirrors backend/api/conversation.py: a self-contained APIRouter behind
require_api_key, reaching its service via request.app.state (503 when absent).
History gets NO REST surface this slice — rehydration stays on the WS
history_loaded frame at activation.

Status mapping (spec table): PersonaNotFound → 404; PersonaExists → 409;
PersonaActive → 409; pydantic ValidationError → 422; store ValueError
(path-traversal guard) → 404 without leaking guard details. NOTE:
ValidationError subclasses ValueError, so it MUST be caught first.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ValidationError

from backend.api.deps import require_api_key
from backend.services.persona import PersonaActive, PersonaExists, PersonaNotFound

router = APIRouter(
    prefix="/api/v1",
    tags=["personas"],
    dependencies=[Depends(require_api_key)],
)


class PersonaCreateIn(BaseModel):
    name: str
    description: str = ""


def _service(request: Request):
    svc = getattr(request.app.state, "persona_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="persona service unavailable")
    return svc


def _not_found(persona_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"persona not found: {persona_id}")


@router.get("/personas")
def list_personas(request: Request) -> list:
    return _service(request).list()


@router.post("/personas", status_code=201)
def create_persona(body: PersonaCreateIn, request: Request) -> dict:
    try:
        return _service(request).create(body.name, body.description)
    except PersonaExists:
        raise HTTPException(status_code=409, detail=f"persona already exists: {body.name}")


@router.get("/personas/{persona_id}")
def get_persona(persona_id: str, request: Request) -> dict:
    try:
        return _service(request).get(persona_id)
    except (PersonaNotFound, ValueError):
        raise _not_found(persona_id)


@router.put("/personas/{persona_id}")
def update_persona(persona_id: str, body: dict, request: Request) -> dict:
    try:
        return _service(request).update(persona_id, body)
    except PersonaNotFound:
        raise _not_found(persona_id)
    except ValidationError as e:           # before ValueError — it subclasses it
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError:
        raise _not_found(persona_id)


@router.delete("/personas/{persona_id}", status_code=204)
def delete_persona(persona_id: str, request: Request) -> Response:
    try:
        _service(request).delete(persona_id)
    except PersonaNotFound:
        raise _not_found(persona_id)
    except PersonaActive:
        raise HTTPException(status_code=409, detail="cannot delete the active persona")
    except ValueError:
        raise _not_found(persona_id)
    return Response(status_code=204)


@router.get("/personas/{persona_id}/triggers")
def get_triggers(persona_id: str, request: Request) -> list:
    try:
        return _service(request).get_triggers(persona_id)
    except (PersonaNotFound, ValueError):
        raise _not_found(persona_id)


@router.put("/personas/{persona_id}/triggers")
def replace_triggers(persona_id: str, triggers: list, request: Request) -> list:
    try:
        return _service(request).replace_triggers(persona_id, triggers)
    except PersonaNotFound:
        raise _not_found(persona_id)
    except ValidationError as e:           # before ValueError — it subclasses it
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError:
        raise _not_found(persona_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test pytest tests/unit/test_personas_api.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/api/personas.py tests/unit/test_personas_api.py
git commit -m "feat(api): /api/v1/personas router — CRUD + triggers, spec status mapping"
```

---

## Task 7: Wire `PlayAIdes` onto the service (delegations, history, D6 rewire)

**Files:**
- Modify: `playAIdes.py` (imports; `__init__` lines ~102–170; CRUD methods ~211–289; history methods ~389–444)
- Modify: `tests/unit/test_playaides_persona_ops.py` (two behavior-change tests)
- Modify: `tests/unit/test_playaides_chat.py` (add the D6 pin test)

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_playaides_persona_ops.py`, **replace** `TestUpdatePersona.test_creates_dir_if_missing` (the old silent-create is the D7 bug, not a contract) with:

```python
    def test_update_missing_persona_raises(self, play: PlayAIdes):
        from backend.services.persona import PersonaNotFound
        with pytest.raises(PersonaNotFound):
            play.update_persona("fresh", {"name": "Fresh", "back_ground": "b",
                                          "psyche": {"traits": []}, "gender": "Female"})
```

Add to `TestCreatePersona`:

```python
    def test_create_collision_raises(self, play: PlayAIdes):
        # D7: silent overwrite was a bug. "TestBot" slugs to the seeded "testbot".
        from backend.services.persona import PersonaExists
        with pytest.raises(PersonaExists):
            play.create_persona("TestBot", "again")
```

In `tests/unit/test_playaides_chat.py`, add (top-level, after the existing imports):

```python
class _RecordingLLM(MockLLM):
    """MockLLM subclass (passes the PlayAIdesArgs isinstance check) that
    records the system prompt each turn."""
    def __init__(self):
        self.system_prompts = []

    def chat(self, messages, system_prompt=None):
        self.system_prompts.append(system_prompt)
        return "ok"

    def chat_stream(self, messages, system_prompt=None):
        self.system_prompts.append(system_prompt)
        yield "ok"
```

and inside `TestChat`:

```python
    def test_run_turn_targets_the_requested_persona_not_the_active_one(
        self, persona_file, fake_tts, no_incarnation, tmp_personas_dir
    ):
        """D6 pin: the old wiring (get_persona=lambda pid: current_persona)
        ignored the pid — a turn addressed to a non-active persona ran with
        the ACTIVE persona's character. The rewire loads the target by id."""
        import json
        (tmp_personas_dir / "rin").mkdir()
        (tmp_personas_dir / "rin" / "persona.json").write_text(json.dumps({
            "name": "Rin", "back_ground": "A completely different background.",
            "psyche": {"traits": []}, "gender": "Female", "language": "English",
        }))
        llm = _RecordingLLM()
        args = PlayAIdesArgs(
            persona=[str(persona_file)], generate_voice=False, use_voice=False,
            use_avatar=False, generate_avatar=False, llm=llm, tts=fake_tts,
        )
        play = PlayAIdes(args)              # active persona: testbot
        play.chat("hello", persona_id="rin")
        assert "A completely different background." in llm.system_prompts[-1]
        assert "A persona used only in tests." not in llm.system_prompts[-1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `bin/test pytest tests/unit/test_playaides_persona_ops.py tests/unit/test_playaides_chat.py -q`
Expected: FAIL — `update_persona` still silently creates (no raise), `create_persona` silently overwrites, and the D6 test sees TestBot's background in the system prompt.

- [ ] **Step 3: Construct the service in `__init__` and rewire**

In `playAIdes.py`, add to the imports (after the `backend.clients.tts` import):

```python
from backend.services.persona import (
    PersonaActive, PersonaExists, PersonaNotFound, PersonaService,
)
from backend.stores.history import HistoryStore
from backend.stores.personas import PersonaStore
```

Immediately after the `self.tts = ...` line (~102), insert:

```python
        # The persona domain owner (spec 2026-06-10). Stores default to the
        # relative "personas" dir, same as the methods they replace.
        self.personas = PersonaService(
            persona_store=PersonaStore(),
            history_store=HistoryStore(),
            active_persona_id=lambda: (
                self.current_persona.name.strip().lower().replace(" ", "_")
                if self.current_persona else None
            ),
            history_cap=CHAT_HISTORY_CAP,
        )
```

**Delete** the `self.chat_histories: Dict[...] = {}` assignment and its comment block (lines ~114–117) — `chat_histories` becomes a property (Step 4) and assigning would raise `AttributeError`. Keep the `self.chat_history: List[Dict[str, str]] = []` alias line.

Rewire the `ConversationService` construction (~158):

```python
        self.conversation = ConversationService(
            get_persona=self._conversation_persona,
            history_load=self.personas.load_history,
            history_save=self.personas.save_history,
            dispatch=self._dispatch_skill,
            llm=self.llm,
            ha=self.ha_client,
            speak=self.speak_as_persona,
            ha_default_agent_id=self.args.ha_default_agent_id,
            history_cap=CHAT_HISTORY_CAP,
        )
        if self.incarnation_server is not None:
            self.incarnation_server.app.state.conversation_service = self.conversation
            self.incarnation_server.app.state.persona_service = self.personas
```

Add the D6 adapter method (place it next to `chat`, near the bottom):

```python
    def _conversation_persona(self, persona_id: str) -> Optional[Persona]:
        """D6: load the TARGETED persona by id. The old wiring ignored the pid
        and always returned the active persona, so a turn addressed to a
        non-active persona ran with the wrong character. None keeps
        ConversationService's existing "No persona loaded." handling for
        unknown ids."""
        try:
            return self.personas.get_model(persona_id)
        except (PersonaNotFound, ValueError):
            return None
```

- [ ] **Step 4: Replace the CRUD + history methods with delegations**

Replace `list_personas` / `get_persona_by_id` / `create_persona` / `update_persona` / `delete_persona` (lines ~211–289) with:

```python
    def list_personas(self) -> List[dict]:
        return self.personas.list()

    def get_persona_by_id(self, persona_id: str) -> Optional[dict]:
        try:
            return self.personas.get(persona_id)
        except (PersonaNotFound, ValueError):
            return None

    def create_persona(self, name: str, description: str) -> dict:
        return self.personas.create(name, description)

    def update_persona(self, persona_id: str, data: dict) -> dict:
        return self.personas.update(persona_id, data)

    def delete_persona(self, persona_id: str) -> bool:
        """Legacy bool surface for internal callers: the service's typed
        exceptions translate back to today's False returns."""
        try:
            self.personas.delete(persona_id)
        except (PersonaNotFound, PersonaActive, ValueError) as e:
            logger.warning("delete_persona(%r) refused: %s", persona_id, e)
            return False
        return True
```

Replace `_history_path` / `_load_history` / `_save_history` / `delete_history` (lines ~389–444) with (`_history_path` is deleted outright — nothing outside those methods referenced it; the stores own pathing now):

```python
    @property
    def chat_histories(self) -> Dict[str, List[Dict[str, str]]]:
        """The PersonaService history cache — the SAME dict, not a copy, so
        legacy readers/writers and the history_loaded frame keep operating on
        live state. The chat_history alias still points at the active entry."""
        return self.personas.histories

    def _load_history(self, persona_id: str) -> List[Dict[str, str]]:
        return self.personas.load_history(persona_id)

    def _save_history(self, persona_id: str):
        self.personas.save_history(persona_id)

    def delete_history(self, persona_id: str):
        self.personas.delete_history(persona_id)
```

- [ ] **Step 5: Run the affected suites**

Run: `bin/test pytest tests/unit/test_playaides_persona_ops.py tests/unit/test_playaides_chat.py tests/unit/test_chat_history.py tests/unit/test_set_persona.py tests/unit/test_conversation_service.py -q`
Expected: PASS — the new tests pass, and every pre-existing test in these files still passes (the delegations preserve the dict-in/dict-out signatures, the same-object history cache, and the atomic-write behavior the tests pin).

- [ ] **Step 6: Run the full unit tier as a checkpoint**

Run: `bin/test pytest tests/unit -q`
Expected: PASS (no regressions elsewhere — `test_handle_event`, `test_chat_skill_dispatch`, `test_playaides_default_persona`, etc. all construct PlayAIdes and must still work).

- [ ] **Step 7: Commit**

```bash
git add playAIdes.py tests/unit/test_playaides_persona_ops.py tests/unit/test_playaides_chat.py
git commit -m "refactor(playaides): persona domain delegates to PersonaService; D6 by-id conversation rewire"
```

---

## Task 8: Delete the WS CRUD branches + mount the router

**Files:**
- Modify: `playAIdes.py` (`_handle_incarnation_message`: delete the `get_persona` branch ~490–496 and the `create_persona`/`update_persona`/`delete_persona` branches ~595–617)
- Modify: `incarnation_server.py` (import ~line 18; mount ~line 172)
- Test: `tests/unit/test_ws_crud_removed.py` (create)
- Test: `tests/integration/test_personas_rest.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ws_crud_removed.py`:

```python
"""The WS dispatcher's persona-CRUD branches are DELETED (creator.js was their
only consumer, now on REST). get_personas stays — viewer.js consumes it."""
from __future__ import annotations

import pytest

from model_interfaces import MockLLM
from playAIdes import PlayAIdes, PlayAIdesArgs


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)], generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False, llm=MockLLM(), tts=fake_tts,
    )
    return PlayAIdes(args)


def test_crud_frames_are_inert(play):
    before = list(play.incarnation_server.commands)
    for msg_type, payload in [
        ("get_persona", {"id": "testbot"}),
        ("create_persona", {"name": "Ghost", "description": ""}),
        ("update_persona", {"id": "testbot", "name": "Hacked"}),
        ("delete_persona", {"id": "testbot"}),
    ]:
        play._handle_incarnation_message({"type": msg_type, "payload": payload})
    assert play.incarnation_server.commands == before   # no reply frames
    assert play.get_persona_by_id("ghost") is None       # nothing created
    assert play.get_persona_by_id("testbot")["name"] == "TestBot"  # nothing changed


def test_get_personas_still_answers(play):
    play._handle_incarnation_message({"type": "get_personas", "payload": {}})
    cmds = dict(play.incarnation_server.commands)
    assert [p["id"] for p in cmds["personas_list"]["personas"]] == ["testbot"]
```

Create `tests/integration/test_personas_rest.py`:

```python
"""End-to-end /api/v1/personas tests on the real IncarnationServer app with a
real PersonaService over tmp dirs — proves the router is mounted and the whole
request cycle (router → service → stores) works."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.services.persona import PersonaService
from backend.stores.history import HistoryStore
from backend.stores.personas import PersonaStore

pytestmark = pytest.mark.integration


@pytest.fixture
def client(tmp_path):
    from incarnation_server import IncarnationServer
    server = IncarnationServer()
    base = tmp_path / "personas"
    server.app.state.persona_service = PersonaService(
        persona_store=PersonaStore(base_dir=base),
        history_store=HistoryStore(base_dir=base),
        active_persona_id=lambda: "keeper",
    )
    return TestClient(server.app)


def test_full_crud_and_triggers_flow(client):
    # create → 201, full defaulted document (D3)
    r = client.post("/api/v1/personas",
                    json={"name": "New Friend", "description": "hello"})
    assert r.status_code == 201
    doc = r.json()
    assert doc["id"] == "new_friend" and doc["triggers"] == []

    # collision → 409 (D7)
    assert client.post("/api/v1/personas", json={"name": "New Friend"}).status_code == 409

    # list + get
    assert [p["id"] for p in client.get("/api/v1/personas").json()] == ["new_friend"]
    assert client.get("/api/v1/personas/new_friend").json()["name"] == "New Friend"

    # full-document replace
    doc["back_ground"] = "edited"
    r = client.put("/api/v1/personas/new_friend", json=doc)
    assert r.status_code == 200 and r.json()["back_ground"] == "edited"

    # invalid update → 422, file untouched (D3)
    assert client.put("/api/v1/personas/new_friend",
                      json={"name": "broken only"}).status_code == 422
    assert client.get("/api/v1/personas/new_friend").json()["back_ground"] == "edited"

    # triggers: whole-list replace (D2) + bad row → 422
    trig = [{"on": {"phrase": "show camera"},
             "do": {"skill": "show_pip", "params": {}}}]
    assert client.put("/api/v1/personas/new_friend/triggers", json=trig).status_code == 200
    got = client.get("/api/v1/personas/new_friend/triggers").json()
    assert got[0]["on"]["phrase"] == "show camera"
    assert client.put("/api/v1/personas/new_friend/triggers",
                      json=[{"on": {}, "do": {"skill": "x"}}]).status_code == 422

    # delete-active 409 (D7), then delete → 204 → 404
    client.post("/api/v1/personas", json={"name": "Keeper"})
    assert client.delete("/api/v1/personas/keeper").status_code == 409
    assert client.delete("/api/v1/personas/new_friend").status_code == 204
    assert client.get("/api/v1/personas/new_friend").status_code == 404
    assert client.delete("/api/v1/personas/new_friend").status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `bin/test pytest tests/unit/test_ws_crud_removed.py tests/integration/test_personas_rest.py -q`
Expected: FAIL — `test_crud_frames_are_inert` sees reply frames (`persona_data`, `persona_created`, …) and a created "ghost" persona; the integration tests 404 (router not mounted).

- [ ] **Step 3: Delete the four dispatcher branches**

In `playAIdes.py` `_handle_incarnation_message`:

- Delete the entire `if msg_type == "get_persona":` block (lines ~490–496).
- Delete the entire `if msg_type == "create_persona":`, `if msg_type == "update_persona":`, and `if msg_type == "delete_persona":` blocks (lines ~595–617).
- Leave `get_personas` (viewer.js), `user_input`, `set_active_persona`, `dismiss_persona`, `model_uploaded`, `animation_uploaded`, `design_voice`, `test_voice`, and `status` untouched.

Optionally add one comment where the deleted blocks were:

```python
        # Persona CRUD frames (get_persona/create/update/delete + their reply
        # frames) were deleted 2026-06-10: creator.js — their only consumer —
        # now uses REST (/api/v1/personas). get_personas stays for viewer.js.
```

- [ ] **Step 4: Mount the router**

In `incarnation_server.py`, add to the imports inside the try block (next to the other router imports, ~line 18):

```python
    from backend.api.personas import router as personas_router
```

and after `self.app.include_router(conversation_router)` (~line 171):

```python
        self.app.include_router(personas_router)
```

- [ ] **Step 5: Run to verify they pass**

Run: `bin/test pytest tests/unit/test_ws_crud_removed.py tests/integration/test_personas_rest.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add playAIdes.py incarnation_server.py tests/unit/test_ws_crud_removed.py tests/integration/test_personas_rest.py
git commit -m "feat(server): mount /api/v1/personas; delete WS persona-CRUD dispatcher branches"
```

---

## Task 9: `incarnation/src/apiClient.js` — the shared REST client seed

**Files:**
- Create: `incarnation/src/apiClient.js`
- Test: `incarnation/src/apiClient.test.js`

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/apiClient.test.js`:

```js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from './apiClient.js';

describe('ApiClient', () => {
  beforeEach(() => { global.fetch = vi.fn(); });

  it('createPersona posts the body with the bearer token to /api/v1', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 'x' }) });
    const api = new ApiClient('the-key');
    await api.createPersona('New Friend', 'hello');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/personas');
    expect(opts.method).toBe('POST');
    expect(opts.headers.Authorization).toBe('Bearer the-key');
    expect(JSON.parse(opts.body)).toEqual({ name: 'New Friend', description: 'hello' });
  });

  it('omits the Authorization header when no key is configured (dev mode)', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    await new ApiClient().listPersonas();
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBeUndefined();
  });

  it('prefixes a configured base and encodes ids in paths', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    const api = new ApiClient(null, 'http://host:8765');
    await api.getPersona('a b');
    expect(global.fetch.mock.calls[0][0]).toBe('http://host:8765/api/v1/personas/a%20b');
  });

  it('deletePersona resolves null on 204 without reading a body', async () => {
    const json = vi.fn();
    global.fetch.mockResolvedValue({ ok: true, status: 204, json });
    expect(await new ApiClient().deletePersona('x')).toBeNull();
    expect(json).not.toHaveBeenCalled();
  });

  it('replaceTriggers PUTs the bare array', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    const trig = [{ on: { phrase: 'p' }, do: { skill: 's', params: {} } }];
    await new ApiClient().replaceTriggers('a', trig);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/personas/a/triggers');
    expect(opts.method).toBe('PUT');
    expect(JSON.parse(opts.body)).toEqual(trig);
  });

  it('throws the server detail string on an error status', async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: 'cannot delete the active persona' }),
    });
    await expect(new ApiClient().deletePersona('a'))
      .rejects.toThrow('cannot delete the active persona');
  });

  it('falls back to method/path/status when the error body is not a string', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ loc: [] }] }) });
    await expect(new ApiClient().updatePersona('a', {}))
      .rejects.toThrow('PUT /personas/a -> 422');
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd incarnation && npm test -- src/apiClient.test.js`
Expected: FAIL — cannot resolve `./apiClient.js`. (If `node_modules` is missing, run `npm install` first.)

- [ ] **Step 3: Create `incarnation/src/apiClient.js`**

```js
// Shared REST client for the playAIdes /api/v1 surface — the ICD's
// consumer-side seed (spec 2026-06-10 D4), starting with the persona resource.
// Plain JS, no framework: importable by vanilla pages (creator.js) and React
// (console) alike. Mold: console/consoleApi.js — same bearer-header handling,
// except the header is omitted entirely when no key is configured so dev-mode
// pages (PLAYAIDES_API_KEY unset) work without one.

const BASE = '/api/v1';

export class ApiClient {
  constructor(apiKey = null, base = '') {
    this.apiKey = apiKey;
    this.base = base;
  }

  async _req(method, path, body) {
    const headers = { 'Content-Type': 'application/json' };
    if (this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;
    const res = await fetch(`${this.base}${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      // Surface FastAPI's {detail: "..."} when it's a plain string (404/409);
      // 422 detail is a list of error objects — fall back to the terse form.
      const detail = await res.json().then((d) => d?.detail).catch(() => null);
      throw new Error(typeof detail === 'string' ? detail : `${method} ${path} -> ${res.status}`);
    }
    return res.status === 204 ? null : res.json();
  }

  listPersonas() { return this._req('GET', '/personas'); }
  getPersona(id) { return this._req('GET', `/personas/${encodeURIComponent(id)}`); }
  createPersona(name, description = '') {
    return this._req('POST', '/personas', { name, description });
  }
  updatePersona(id, doc) {
    return this._req('PUT', `/personas/${encodeURIComponent(id)}`, doc);
  }
  deletePersona(id) { return this._req('DELETE', `/personas/${encodeURIComponent(id)}`); }
  getTriggers(id) { return this._req('GET', `/personas/${encodeURIComponent(id)}/triggers`); }
  replaceTriggers(id, list) {
    return this._req('PUT', `/personas/${encodeURIComponent(id)}/triggers`, list);
  }
}
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd incarnation && npm test -- src/apiClient.test.js`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/apiClient.js incarnation/src/apiClient.test.js
git commit -m "feat(frontend): apiClient.js — shared /api/v1 REST client seeded with personas"
```

---

## Task 10: Migrate creator.js CRUD to REST

**Files:**
- Modify: `incarnation/src/creator.js`

The CRUD `conn.send`/`addEventListener` pairs are replaced with `ApiClient` calls. **Untouched:** the voice frames (`design_voice`/`test_voice` sends and `voice_designed`/`voice_tested`/`voice_test_failed` listeners), the REST uploads (`uploadModel`/`uploadAnimations`), and everything else. Failed REST calls surface through the existing `toast(...)` mechanism — today's WS failures show nothing at all.

- [ ] **Step 1: Imports + client construction**

At the top of `creator.js`, extend the imports:

```js
import { createCreatorScene } from './creatorScene.js';
import { ConnectionManager } from './connectionManager.js';
import { ApiClient } from './apiClient.js';
```

After the `API_BASE` constant, add:

```js
// Persona CRUD client (REST, /api/v1). The optional ?key= param carries the
// bearer token when PLAYAIDES_API_KEY is set; dev mode needs none.
const api = new ApiClient(params.get('key'), API_BASE);
```

Update the file's header comment line `*   • Persona CRUD via the /ws WebSocket (handled server-side by PlayAIdes)` to:

```js
 *   • Persona CRUD via REST (/api/v1/personas, apiClient.js)
```

- [ ] **Step 2: Replace the list/load path**

Add a refresh helper (above `populatePersonaSelect`):

```js
async function refreshPersonas() {
    try {
        populatePersonaSelect(await api.listPersonas());
    } catch (err) {
        toast('err', 'Personas', `List failed: ${err.message}`);
    }
}
```

In the `'connected'` listener, replace `conn.send('get_personas');` with `refreshPersonas();`.

**Delete** these five listeners entirely: `conn.addEventListener('personas_list', …)`, `('persona_data', …)`, `('persona_created', …)`, `('persona_updated', …)`, `('persona_deleted', …)`.

After `conn.connect(WS_URL);`, add an immediate load (REST doesn't need the socket):

```js
refreshPersonas();
```

- [ ] **Step 3: Replace the four CRUD handlers**

`personaSelect` change:

```js
personaSelect.addEventListener('change', async () => {
    const id = personaSelect.value;
    if (!id) { clearActivePersona(); return; }
    try {
        setActivePersona(await api.getPersona(id));
    } catch (err) {
        toast('err', 'Persona', `Load failed: ${err.message}`);
    }
});
```

`newBtn` (the returned doc is used directly — no more setTimeout-and-refetch dance):

```js
newBtn.addEventListener('click', async () => {
    const name = prompt('Name your new persona:');
    if (!name) return;
    const description = prompt('A one-line background (optional):') || '';
    try {
        const p = await api.createPersona(name.trim(), description.trim());
        toast('ok', 'Forged', `Persona "${p.name}" created`);
        await refreshPersonas();
        personaSelect.value = p.id;
        setActivePersona(p);
    } catch (err) {
        toast('err', 'Forge', err.message);   // e.g. 409 "persona already exists"
    }
});
```

`saveBtn`:

```js
saveBtn.addEventListener('click', async () => {
    if (!activePersona?.id) {
        toast('err', 'Save', 'No persona selected. Use + NEW first.');
        return;
    }
    try {
        const p = await api.updatePersona(activePersona.id, buildPersonaPayload());
        toast('ok', 'Saved', `"${p.name}" updated`);
        await refreshPersonas();
    } catch (err) {
        toast('err', 'Save', err.message);    // 422 = the doc failed validation
    }
});
```

`deleteBtn`:

```js
deleteBtn.addEventListener('click', async () => {
    if (!activePersona?.id) return;
    const id = activePersona.id;
    const name = activePersona.name || id;
    if (!confirm(`Permanently delete persona "${name}"?\nThis removes the directory under personas/${id}/ on disk.`)) {
        return;
    }
    try {
        await api.deletePersona(id);
        toast('ok', 'Deleted', `"${id}" removed`);
        clearActivePersona();
        await refreshPersonas();
    } catch (err) {
        toast('err', 'Delete', `Could not delete "${id}": ${err.message}`);
    }
});
```

- [ ] **Step 4: Migrate the voice-save (it used the WS `update_persona`)**

Replace the `saveVoiceBtn` listener:

```js
saveVoiceBtn.addEventListener('click', async () => {
    if (!activePersona?.id || !pendingSpeakerId) return;
    activePersona.persona_voice = {
        voice: pendingSpeakerId,
        voice_instruct: [vInstruct.value.trim()].filter(Boolean),
    };
    try {
        await api.updatePersona(activePersona.id, buildPersonaPayload());
        toast('ok', 'Voice', 'Voice saved to persona');
        pendingSpeakerId = null;
        saveVoiceBtn.disabled = true;
    } catch (err) {
        toast('err', 'Voice', `Save failed: ${err.message}`);
    }
});
```

(`designBtn` and `testVoiceBtn` keep their `conn.send('design_voice', …)` / `conn.send('test_voice', …)` — voice frames are out of scope.)

- [ ] **Step 5: Verify no CRUD WS traffic remains**

Run:
```bash
grep -nE "conn\.send\('(get_personas|get_persona|create_persona|update_persona|delete_persona)'|addEventListener\('(personas_list|persona_data|persona_created|persona_updated|persona_deleted)'" incarnation/src/creator.js
```
Expected: **no matches**. Then run the JS suite: `cd incarnation && npm test` — Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add incarnation/src/creator.js
git commit -m "feat(creator): persona CRUD over REST via apiClient; WS CRUD pairs removed"
```

---

## Task 11: Full suite green + browser verification + docs closure

**Files:**
- Modify: `CONTINUITY.md`

- [ ] **Step 1: Confirm no stragglers reference the deleted WS surface**

Run:
```bash
grep -rnE "persona_created|persona_updated|persona_deleted|\"persona_data\"|'persona_data'" \
  --include='*.py' --include='*.js' . | grep -vE "node_modules|dist|\.test-output|docs/"
```
Expected: **no matches** (viewer.js never used these frames; only creator.js and the dispatcher did).

- [ ] **Step 2: Run the full Python suite**

Run: `bin/test pytest -q`
Expected: PASS — baseline 341 plus the new tests (~390 total), 5 skipped, 0 failed. Common causes if not: a test still pinning silent-create/silent-overwrite (fix the test — D7), or a missed `chat_histories` assignment (the property cannot be assigned).

- [ ] **Step 3: Run the full JS suite**

Run: `cd incarnation && npm test`
Expected: PASS (all existing tests + the 7 new apiClient tests).

- [ ] **Step 4: [MANUAL/ASSISTED — desktop browser, no TV] Creator flow verification**

With the harness backend running, open `http://<host>:8765/creator.html` in a desktop browser (or drive it via the chrome-devtools MCP) and verify:

- [ ] Persona list populates on page load (REST, even before the WS dot goes green).
- [ ] **Create**: + NEW → persona appears in the select, auto-selected.
- [ ] **Create collision**: + NEW with the same name → red toast with the 409 detail.
- [ ] **Edit + Save**: change the background, SAVE → "updated" toast; reload page → edit persisted.
- [ ] **Delete**: delete the test persona → removed from the list; deleting the *active* persona → red 409 toast.
- [ ] **Triggers**: `curl -s -X PUT http://<host>:8765/api/v1/personas/<id>/triggers -H 'Content-Type: application/json' -d '[{"on":{"phrase":"show camera"},"do":{"skill":"show_pip","params":{}}}]'` then GET it back — list round-trips.
- [ ] Voice design/test buttons still work over WS (unchanged path), if a rig is up.

- [ ] **Step 5: Update CONTINUITY.md**

Per the living-docs conventions: update **Now & Next** (PersonaService slice DONE; next = unpark `2026-06-09-console-trigger-redesign-PARKED.md` — its resume condition is now met), tick the slice TODO, and add a **Decisions** entry dated 2026-06-10 summarizing: PersonaService + stores + `/api/v1/personas` landed; creator.js on REST; WS CRUD branches deleted; D6 by-id conversation fix; D7 error semantics live; `Persona.animations` declared (data-loss gap found during planning).

- [ ] **Step 6: Commit**

```bash
git add CONTINUITY.md
git commit -m "docs: PersonaService slice landed; trigger-console brainstorm unparked"
```

---

## Self-review

**Spec coverage:** Components 1–2 (stores → Tasks 1–2) ✓; component 3 service incl. CRUD/history/triggers/`get_model` (Tasks 4–5) ✓; component 4 router + status table + 503 + auth (Task 6) ✓; component 5 apiClient.js (Task 9) ✓; "what shrinks" — delegations, `chat_histories` property, CAP pass-through, D6 rewire (Task 7) ✓; WS branch deletion + `get_personas` kept (Task 8) ✓; creator.js migration incl. the voice-save WS update (Task 10) ✓; D1–D7 each realized and pinned by at least one test; test plan tiers (unit stores/service/router, D6 regression, dispatcher, integration REST, JS unit, manual browser) all present ✓. **Beyond the spec (flagged):** `Persona.animations` (Task 3) — required so D3's validated writes don't destroy data the system already writes; and the D6 wiring uses a `None`-on-missing adapter rather than raw `get_model` so ConversationService's existing "No persona loaded." contract holds for unknown ids.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; the only non-scripted step is the explicitly-manual browser checklist (Task 11 Step 4), mirroring the slice-3 precedent.

**Type/name consistency:** `PersonaStore(base_dir)` / `.list_ids/.exists/.read/.write/.delete`, `HistoryStore(base_dir)` / `.read/.write/.delete`, `_check_id`, `PersonaService(persona_store, history_store, active_persona_id, history_cap)` / `.list/.get/.get_model/.create/.update/.delete/.histories/.load_history/.save_history/.delete_history/.get_triggers/.replace_triggers`, exceptions `PersonaNotFound/PersonaExists/PersonaActive`, `slug()`, router file `backend/api/personas.py`, `app.state.persona_service`, JS `ApiClient(apiKey, base)` with `listPersonas/getPersona/createPersona/updatePersona/deletePersona/getTriggers/replaceTriggers` — used identically across tasks and tests. The except-order hazard (`ValidationError` ⊂ `ValueError`) is encoded in both the router code and a dedicated test.
