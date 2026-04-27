# Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 1 (HA → playAIdes trigger ergonomics over HTTP) and Phase 2 (Persona → HA skills via explicit `house_words` delegation, routing residual to HA's `/api/conversation/process`).

**Architecture:** Three new HTTP routes on the existing FastAPI server gated by a shared bearer token (Phase 1). A new `ha_client.py` module + `match_keywords.py` helper, routed from `playAIdes.chat()` when a persona-specific `house_word` matches the user input prefix (Phase 2). HA's response is spoken verbatim or — if the persona opts in — rephrased through the persona's own LLM. No persona-LLM tool-calling; HA owns the LLM-with-tools work.

**Tech Stack:** Python 3 / Pydantic v2 / FastAPI / pytest with `responses` for HTTP mocking. No frontend changes.

**Spec:** [docs/superpowers/specs/2026-04-26-ha-integration-design.md](../specs/2026-04-26-ha-integration-design.md)

**Branch:** create `ha_integration` from `main` (no worktrees per project preference). Current `main` tip is `e22e198` (`spec: HA integration design`) — verify with `git log --oneline -1`.

## Conventions for this plan

- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.
- Backend uses TDD via `make test` (Dockerized — do not call `pytest` directly).
- Each task ends with a commit. Conventional Commits prefixes (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- No frontend changes — `make test-js` is run only at the end as a regression sanity check.

## Baseline going in

- Branch: `main` at HEAD = `e22e198` — verify with `git log --oneline -1`.
- Tests: `make test` → 138 passed, 4 deselected. `make test-js` → 89 passed.
- Spec committed at `docs/superpowers/specs/2026-04-26-ha-integration-design.md`.

## File structure

| File | Status | Responsibility |
|---|---|---|
| `persona.py` | Modify | Add 3 optional fields to `Persona`: `house_words`, `rephrase_ha_response`, `ha_agent_id` |
| `match_keywords.py` | **Create** | Pure helper: `match_keyword_prefix(text, keywords)` returns `(matched, residual)` |
| `ha_client.py` | **Create** | `HAClient` + `ConversationResponse` dataclass — wraps HA's `/api/conversation/process` |
| `playAIdes.py` | Modify | New HA env args on `PlayAIdesArgs`; `HAClient` construction; `chat()` routing branch |
| `incarnation_server.py` | Modify | `require_api_key` dep + 3 new HTTP routes |
| `tests/conftest.py` | Modify | New `mock_ha_client` and `with_api_key` fixtures |
| `tests/unit/test_persona_schema.py` | Modify | (or new — see Task 1) Defaults + backwards-compat for new fields |
| `tests/unit/test_match_keywords.py` | **Create** | Pure unit tests for `match_keyword_prefix` |
| `tests/unit/test_ha_client.py` | **Create** | Pure unit tests for `HAClient` (uses `responses`) |
| `tests/integration/test_ha_trigger_endpoints.py` | **Create** | HTTP-level tests for the 3 new routes |
| `tests/integration/test_ha_routing.py` | **Create** | `chat()` routing tests using `mock_ha_client` |
| `docs/ha-integration.md` | **Create** | HA-side YAML reference + manual smoke recipe |

---

## Task 0: Branch creation

**Files:** none (git only).

- [ ] **Step 1: Verify baseline + create branch**

```bash
cd /home/bell/repo/ai_life/playAIdes
git log --oneline -1                     # expect: e22e198 spec: HA integration design ...
git checkout -b ha_integration main
make test 2>&1 | tail -3                 # expect: 138 passed, 4 deselected
```

If the baseline doesn't match exactly, STOP and report — something has shifted since the spec landed.

- [ ] **Step 2: Verify `responses` is in dev deps**

```bash
grep -E "^\s*\"responses" pyproject.toml
```

Expected: a line like `"responses>=0.25",`. If missing, STOP and report (the spec assumed it was already present per the planning-prep exploration).

---

## Task 1: Extend `Persona` schema with HA fields

**Files:**
- Modify: `persona.py` (`Persona` class)
- Test: `tests/unit/test_persona_schema.py` (find the existing class for `Persona` field tests; if none exists, find any `tests/unit/test_persona*.py` file — there's at least one — and extend the existing test class)

The spec adds three optional fields. All must default to "disabled" so existing `persona.json` files keep working unchanged.

- [ ] **Step 1: Find the existing persona-schema test file**

```bash
ls tests/unit/ | grep -i persona
```

Expected: at least one file like `test_persona*.py` or similar. Read it to find the test class that covers `Persona` field defaults / loading. If no schema-defaults class exists yet, add a new one in the same file.

- [ ] **Step 2: Write the failing test**

Append to the persona-schema test file (replacing `<TestClassName>` with whichever class you found, or `TestPersonaHAFields` as a new class):

```python
    def test_ha_fields_default_to_disabled(self):
        """house_words/rephrase_ha_response/ha_agent_id all default to HA-disabled."""
        from persona import Persona, Psyche
        p = Persona(
            name="Test", back_ground="bg",
            psyche=Psyche(traits=[]),
            gender="Female", language="English",
        )
        assert p.house_words == []
        assert p.rephrase_ha_response is False
        assert p.ha_agent_id is None

    def test_ha_fields_load_from_persona_json(self, tmp_path):
        """A persona.json with HA fields loads into the model correctly."""
        import json
        from persona import Persona
        path = tmp_path / "persona.json"
        path.write_text(json.dumps({
            "name": "Silver", "back_ground": "bg",
            "psyche": {"traits": []},
            "gender": "Female", "language": "English",
            "house_words": ["house"],
            "rephrase_ha_response": True,
            "ha_agent_id": "conversation.openai_assist",
        }))
        p = Persona(**json.loads(path.read_text()))
        assert p.house_words == ["house"]
        assert p.rephrase_ha_response is True
        assert p.ha_agent_id == "conversation.openai_assist"
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|test_ha_fields" | head
```

Expected: 2 failures with `AttributeError` or Pydantic validation error.

- [ ] **Step 4: Add the fields to `Persona`**

In `persona.py`, find the `Persona` class (around line 40). After `is_default: bool = False`, add:

```python
    house_words: List[str] = []
    rephrase_ha_response: bool = False
    ha_agent_id: Optional[str] = None
```

If `List` and `Optional` aren't already imported in `persona.py`, the existing imports for `wake_words: Optional[List[str]] = None` mean both are. Confirm with `grep -E "^from typing" persona.py`.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `140 passed, 4 deselected` (was 138; +2 new).

- [ ] **Step 6: Commit**

```bash
git add persona.py tests/unit/test_persona*.py
git commit -m "feat: add house_words / rephrase_ha_response / ha_agent_id to Persona"
```

---

## Task 2: Add `PLAYAIDES_API_KEY` arg + env fallback

**Files:**
- Modify: `playAIdes.py` (`PlayAIdesArgs` class around line 75)
- Modify: `main.py` (argparse block around line 77)

The Phase 1 endpoints need a shared bearer token. Read it from `--api-key` CLI flag with `PLAYAIDES_API_KEY` env fallback. Unset = dev mode (no auth, with startup warning — implemented in Task 3).

- [ ] **Step 1: Add the field to `PlayAIdesArgs`**

In `playAIdes.py` (around line 75), add to the `PlayAIdesArgs` model after the `tts: Optional[PersonaTTS] = None` line:

```python
    api_key: Optional[str] = None
```

- [ ] **Step 2: Wire the CLI arg in `main.py`**

In `main.py` around line 77, add to the argparse block (after the existing `--generate_avatar` arg):

```python
    parser.add_argument("--api-key", type=str, default=None,
                        help="Bearer token for HA→playAIdes endpoints. "
                             "Falls back to PLAYAIDES_API_KEY env. "
                             "Unset = dev mode (no auth).")
```

In the `casted_args = PlayAIdesArgs(...)` call at the bottom of the same block, add (using the `os.environ.get(...) or default` pattern this codebase uses elsewhere):

```python
        api_key=args.api_key or os.environ.get("PLAYAIDES_API_KEY"),
```

If `os` isn't imported in `main.py`, add `import os` at the top.

- [ ] **Step 3: Verify nothing breaks**

```bash
make test 2>&1 | tail -3
```

Expected: `140 passed, 4 deselected` (count unchanged — no new test, just plumbing).

- [ ] **Step 4: Commit**

```bash
git add playAIdes.py main.py
git commit -m "feat: PlayAIdesArgs.api_key + --api-key CLI flag (PLAYAIDES_API_KEY env fallback)"
```

---

## Task 3: Add `require_api_key` dependency + `POST /api/personas/{id}/activate`

**Files:**
- Modify: `incarnation_server.py` (add dependency function + new route)
- Modify: `tests/conftest.py` (add `with_api_key` fixture)
- Test: `tests/integration/test_ha_trigger_endpoints.py` (**create**)

The first endpoint validates the auth pattern. Subsequent endpoints (Tasks 4, 5) reuse the same dependency.

- [ ] **Step 1: Add the `with_api_key` fixture**

In `tests/conftest.py`, append:

```python
@pytest.fixture
def with_api_key(monkeypatch):
    """Set PLAYAIDES_API_KEY for endpoints that require auth.
    Returns the token value so tests can assemble Authorization headers."""
    token = "test-api-key-secret-1234"
    monkeypatch.setenv("PLAYAIDES_API_KEY", token)
    return token
```

- [ ] **Step 2: Write the failing tests**

Create `tests/integration/test_ha_trigger_endpoints.py`:

```python
"""Integration tests for HA→playAIdes HTTP trigger endpoints."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from incarnation_server import IncarnationServer

pytestmark = pytest.mark.integration


@pytest.fixture
def server_with_callback():
    """Boot an IncarnationServer with a recording callback (no PlayAIdes needed)."""
    received: list[dict] = []

    def cb(msg):
        received.append(msg)

    srv = IncarnationServer(host="testhost", port=0, on_message_callback=cb)
    srv.received = received  # for test access
    return srv


class TestActivateEndpointAuth:
    def test_missing_authorization_header_returns_401(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate")
        assert r.status_code == 401

    def test_wrong_token_returns_401(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate",
                        headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_correct_token_returns_200_and_dispatches(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate",
                        headers={"Authorization": f"Bearer {with_api_key}"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # The callback should have been invoked with the synthesized message.
        assert server_with_callback.received == [
            {"type": "set_active_persona", "payload": {"id": "silver"}},
        ]

    def test_no_env_key_set_returns_200_in_dev_mode(self, server_with_callback, monkeypatch):
        """When PLAYAIDES_API_KEY is unset, auth is skipped (dev convenience)."""
        monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)
        client = TestClient(server_with_callback.app)
        r = client.post("/api/personas/silver/activate")
        assert r.status_code == 200
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|test_ha_trigger" | head
```

Expected: 4 failures — endpoints don't exist (404s) or `with_api_key` fixture missing.

- [ ] **Step 4: Add `require_api_key` dependency + route in `incarnation_server.py`**

Near the top of `incarnation_server.py` after the existing imports, add:

```python
from fastapi import Header, HTTPException
```

(check if `Header` / `HTTPException` are already imported — extend the existing FastAPI import line if so.)

Inside `_setup_routes(self)`, before the existing route definitions, add the dependency:

```python
        def require_api_key(authorization: Optional[str] = Header(default=None)):
            expected = os.environ.get("PLAYAIDES_API_KEY")
            if not expected:
                # Dev mode: no auth configured. Logged once at startup elsewhere.
                return
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="missing bearer token")
            if authorization.removeprefix("Bearer ") != expected:
                raise HTTPException(status_code=401, detail="invalid bearer token")
```

If `Optional` isn't already imported in `incarnation_server.py`, add it to the existing typing import line.

Then add the activate route alongside the other routes:

```python
        @self.app.post("/api/personas/{persona_id}/activate")
        async def activate_persona(persona_id: str, _auth=Depends(require_api_key)):
            if self.on_message_callback:
                self.on_message_callback({
                    "type": "set_active_persona",
                    "payload": {"id": persona_id},
                })
            return {"ok": True, "active_persona_id": persona_id}
```

Add `Depends` to the FastAPI imports if not already present:

```python
from fastapi import Depends, Header, HTTPException
```

- [ ] **Step 5: Add the dev-mode startup warning**

In `incarnation_server.py`, in `IncarnationServer.__init__` (around the existing `dist` check at line 78-88), add after that block:

```python
        if not os.environ.get("PLAYAIDES_API_KEY"):
            logger.warning(
                "PLAYAIDES_API_KEY not set — HA trigger endpoints accept "
                "any request (dev mode). Set the env var in any non-local "
                "deployment."
            )
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `144 passed, 4 deselected` (was 140; +4 new).

- [ ] **Step 7: Commit**

```bash
git add incarnation_server.py tests/conftest.py tests/integration/test_ha_trigger_endpoints.py
git commit -m "feat: POST /api/personas/{id}/activate + Bearer-token auth dependency"
```

---

## Task 4: Add `POST /api/dismiss` endpoint

**Files:**
- Modify: `incarnation_server.py`
- Modify: `tests/integration/test_ha_trigger_endpoints.py`

Voice-driven dismiss is purely client-side today (frontend transitions to EMPTY on matching a dismiss word). For HA-driven dismiss we need a server-pushed signal. v1 broadcasts `unload_model` to all connected clients (an existing message the frontend already handles) and clears all server-side bindings. A more polished EMPTY-state push is a follow-up.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_ha_trigger_endpoints.py`:

```python
class TestDismissEndpoint:
    def test_dismiss_requires_auth(self, server_with_callback, with_api_key):
        client = TestClient(server_with_callback.app)
        r = client.post("/api/dismiss")
        assert r.status_code == 401

    def test_dismiss_clears_bindings_and_broadcasts_unload(self, server_with_callback, with_api_key):
        # Seed bindings to verify they get cleared.
        server_with_callback._bindings = {object(): "silver", object(): "rin"}
        # Stub broadcast_to_all so we can observe the emit.
        broadcasts: list[tuple[str, dict]] = []
        server_with_callback.broadcast_to_all = lambda c, p=None: broadcasts.append((c, p or {}))

        client = TestClient(server_with_callback.app)
        r = client.post("/api/dismiss",
                        headers={"Authorization": f"Bearer {with_api_key}"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert server_with_callback._bindings == {}
        assert broadcasts == [("unload_model", {})]
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "FAILED|test_dismiss" | head
```

Expected: 2 failures (404 endpoint not found).

- [ ] **Step 3: Add the route**

In `incarnation_server.py`, add alongside the activate route:

```python
        @self.app.post("/api/dismiss")
        async def dismiss(_auth=Depends(require_api_key)):
            self._bindings.clear()
            self.broadcast_to_all("unload_model", {})
            logger.info("HA-driven dismiss: cleared bindings, broadcast unload_model")
            return {"ok": True}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `146 passed, 4 deselected` (was 144; +2 new).

- [ ] **Step 5: Commit**

```bash
git add incarnation_server.py tests/integration/test_ha_trigger_endpoints.py
git commit -m "feat: POST /api/dismiss broadcasts unload_model + clears bindings"
```

---

## Task 5: Add `GET /api/state` endpoint

**Files:**
- Modify: `incarnation_server.py`
- Modify: `tests/integration/test_ha_trigger_endpoints.py`

Read-only status query for HA dashboard polling. There's no server-side state machine, so we surface what we have: bound client count plus (if a callback can supply it) the active persona id. We pass a state-provider callable into the server constructor to avoid coupling to `PlayAIdes`.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_ha_trigger_endpoints.py`:

```python
class TestStateEndpoint:
    def test_state_does_not_require_auth(self, server_with_callback, monkeypatch):
        """GET /api/state is unauthenticated by design (read-only, no PII)."""
        monkeypatch.setenv("PLAYAIDES_API_KEY", "anything")
        client = TestClient(server_with_callback.app)
        r = client.get("/api/state")
        assert r.status_code == 200

    def test_state_returns_active_persona_and_client_count(self, server_with_callback):
        # Seed two bound clients and a state-provider that reports "silver".
        server_with_callback._bindings = {object(): "silver", object(): "silver"}
        server_with_callback.state_provider = lambda: {"active_persona_id": "silver"}

        client = TestClient(server_with_callback.app)
        r = client.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["active_persona_id"] == "silver"
        assert body["bound_client_count"] == 2

    def test_state_handles_missing_state_provider(self, server_with_callback):
        """If no state_provider is set, active_persona_id is None."""
        server_with_callback.state_provider = None
        client = TestClient(server_with_callback.app)
        r = client.get("/api/state")
        assert r.status_code == 200
        assert r.json()["active_persona_id"] is None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
make test 2>&1 | grep -E "FAILED|test_state" | head
```

Expected: 3 failures (404).

- [ ] **Step 3: Add the route + state_provider hook**

In `incarnation_server.py`, in `IncarnationServer.__init__`, add `state_provider=None` to the signature and store it:

```python
    def __init__(self, host="0.0.0.0", port=8765, on_message_callback=None,
                 state_provider=None):
        ...
        self.state_provider = state_provider
```

(Match the existing keyword style — extend the existing signature.)

Then add the route:

```python
        @self.app.get("/api/state")
        async def get_state():
            active = None
            if self.state_provider:
                try:
                    active = self.state_provider().get("active_persona_id")
                except Exception as e:
                    logger.warning("state_provider failed: %s", e)
            return {
                "active_persona_id": active,
                "bound_client_count": len(self._bindings),
            }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `149 passed, 4 deselected` (was 146; +3 new).

- [ ] **Step 5: Wire `state_provider` from `PlayAIdes`**

In `playAIdes.py`, find the `IncarnationServer(...)` construction (around line 95-100). Add a `state_provider` lambda that returns the current persona's id. The persona id is derived from the persona's name the same way the rest of the codebase does (see `set_persona` for the canonical pattern; usually `name.strip().lower().replace(" ", "_")` or similar — check the existing code and reuse).

```python
        self.incarnation_server = IncarnationServer(
            ...,
            on_message_callback=self._handle_incarnation_message,
            state_provider=lambda: {
                "active_persona_id": (
                    self.current_persona.name.strip().lower().replace(" ", "_")
                    if self.current_persona else None
                ),
            },
        )
```

(Match exactly however persona ids are derived in `set_persona`. If they're stored as a separate field somewhere, use that field instead.)

- [ ] **Step 6: Run all tests one more time**

```bash
make test 2>&1 | tail -3
```

Expected: `149 passed, 4 deselected` (count unchanged — wiring only).

- [ ] **Step 7: Commit**

```bash
git add incarnation_server.py playAIdes.py tests/integration/test_ha_trigger_endpoints.py
git commit -m "feat: GET /api/state returns active_persona_id + bound_client_count"
```

---

## Task 6: `match_keywords.py` helper

**Files:**
- Create: `match_keywords.py`
- Test: `tests/unit/test_match_keywords.py` (**create**)

Pure helper used by `chat()` to detect house-word delegation. Mirrors the semantics of `incarnation/src/transcriptMatcher.js` `matchPhrase` but for prefix-only matching: the keyword must appear as the first non-whitespace token. Case-insensitive; leading/trailing whitespace tolerated.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_match_keywords.py`:

```python
"""Unit tests for match_keywords.match_keyword_prefix."""
from match_keywords import match_keyword_prefix


def test_no_keywords_returns_no_match():
    assert match_keyword_prefix("turn off the lights", []) == (False, "")


def test_keyword_at_start_matches_and_strips():
    matched, residual = match_keyword_prefix("house turn off the lights", ["house"])
    assert matched is True
    assert residual == "turn off the lights"


def test_match_is_case_insensitive():
    matched, residual = match_keyword_prefix("HOUSE turn off the lights", ["house"])
    assert matched is True
    assert residual == "turn off the lights"


def test_keyword_only_returns_match_with_empty_residual():
    matched, residual = match_keyword_prefix("house", ["house"])
    assert matched is True
    assert residual == ""


def test_keyword_in_middle_does_not_match():
    """Prefix match only — house anywhere but the start is not a delegation."""
    matched, residual = match_keyword_prefix(
        "play the song House of the Rising Sun", ["house"]
    )
    assert matched is False
    assert residual == ""


def test_leading_whitespace_tolerated():
    matched, residual = match_keyword_prefix("   house  turn off  ", ["house"])
    assert matched is True
    assert residual == "turn off"


def test_first_match_wins_with_multiple_keywords():
    matched, residual = match_keyword_prefix(
        "home, dim the lights", ["house", "home"]
    )
    assert matched is True
    assert residual == "dim the lights"


def test_keyword_must_be_followed_by_space_or_end():
    """A word starting with the keyword (e.g. 'household') is not a match."""
    matched, residual = match_keyword_prefix("household chores", ["house"])
    assert matched is False


def test_punctuation_after_keyword_is_residual():
    matched, residual = match_keyword_prefix("house, turn off", ["house"])
    assert matched is True
    assert residual == ", turn off"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|test_match_keywords|ImportError" | head
```

Expected: ImportError or 9 failures.

- [ ] **Step 3: Implement `match_keywords.py`**

Create `match_keywords.py` at the repo root:

```python
"""Keyword-prefix matching for routing user input.

Used by playAIdes.chat() to detect 'house word' delegation: when the user's
input begins with a configured keyword (e.g. "house"), the residual text
after that keyword is forwarded to Home Assistant's conversation agent.

Mirrors the prefix-only semantics intended for transcriptMatcher.js's
matchPhrase but is intentionally more conservative — only the prefix
position counts as a match (so "play the song House of the Rising Sun"
does NOT delegate)."""
from __future__ import annotations

from typing import List, Tuple


def match_keyword_prefix(text: str, keywords: List[str]) -> Tuple[bool, str]:
    """Return (matched, residual) for the first keyword that prefixes text.

    Matching is case-insensitive, leading/trailing whitespace is tolerated,
    and the keyword must be followed by either end-of-string or a non-letter
    non-digit character (so "house" matches "house, turn..." but not
    "household chores").

    Returns (False, "") if no keyword matches or `keywords` is empty.
    """
    if not keywords:
        return (False, "")
    stripped = text.strip()
    lowered = stripped.lower()
    for kw in keywords:
        if not kw:
            continue
        kw_lower = kw.lower()
        if not lowered.startswith(kw_lower):
            continue
        # Word-boundary check: the char right after the keyword must be
        # absent (end of string) or non-alphanumeric.
        end = len(kw_lower)
        if end < len(lowered) and lowered[end].isalnum():
            continue
        # Residual is the remainder of the ORIGINAL (case-preserved) text
        # after the matched keyword, with leading whitespace stripped.
        residual = stripped[end:].lstrip(" \t")
        # Trailing whitespace is also stripped for ergonomics.
        return (True, residual.rstrip())
    return (False, "")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `158 passed, 4 deselected` (was 149; +9 new).

- [ ] **Step 5: Commit**

```bash
git add match_keywords.py tests/unit/test_match_keywords.py
git commit -m "feat: match_keywords.py — prefix keyword matcher for house-word routing"
```

---

## Task 7: `ha_client.py` — HA conversation API wrapper

**Files:**
- Create: `ha_client.py`
- Test: `tests/unit/test_ha_client.py` (**create**)

Pure HTTP wrapper for HA's `/api/conversation/process`. Returns a `ConversationResponse` dataclass with normalized success/error semantics. No playAIdes internals.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ha_client.py`:

```python
"""Unit tests for ha_client.HAClient (HTTP mocked with `responses`)."""
import responses

from ha_client import HAClient, ConversationResponse


HA_BASE = "http://ha.test:8123"


@responses.activate
def test_converse_success_extracts_speech_text():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        json={
            "response": {
                "response_type": "action_done",
                "speech": {"plain": {"speech": "Turning off the lights"}},
            },
            "conversation_id": "conv-123",
        },
        status=200,
    )
    client = HAClient(HA_BASE, "tok")
    r = client.converse("turn off the lights", agent_id="conversation.assist")
    assert isinstance(r, ConversationResponse)
    assert r.success is True
    assert r.speech_text == "Turning off the lights"
    assert r.conversation_id == "conv-123"
    assert r.error_code is None


@responses.activate
def test_converse_no_intent_match_returns_failure():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        json={
            "response": {
                "response_type": "error",
                "data": {"code": "no_intent_match"},
                "speech": {"plain": {"speech": "Sorry, I couldn't understand that"}},
            },
            "conversation_id": None,
        },
        status=200,
    )
    client = HAClient(HA_BASE, "tok")
    r = client.converse("xyzzy")
    assert r.success is False
    assert r.error_code == "no_intent_match"
    assert r.speech_text == "I didn't catch that — try rephrasing?"


@responses.activate
def test_converse_401_returns_failure_with_generic_message():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        json={"message": "Unauthorized"},
        status=401,
    )
    client = HAClient(HA_BASE, "bad-token")
    r = client.converse("anything")
    assert r.success is False
    assert r.error_code == "ha_http_401"
    assert "can't reach" in r.speech_text.lower() or "trouble" in r.speech_text.lower()


@responses.activate
def test_converse_timeout_returns_failure():
    responses.add(
        responses.POST,
        f"{HA_BASE}/api/conversation/process",
        body=ConnectionError("simulated network drop"),
    )
    client = HAClient(HA_BASE, "tok", timeout=1.0)
    r = client.converse("anything")
    assert r.success is False
    assert r.error_code == "ha_unreachable"
    assert "can't reach the house" in r.speech_text.lower()


@responses.activate
def test_health_check_true_on_200():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=200)
    assert HAClient(HA_BASE, "tok").health_check() is True


@responses.activate
def test_health_check_false_on_5xx():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=500)
    assert HAClient(HA_BASE, "tok").health_check() is False


@responses.activate
def test_health_check_false_on_network_error():
    responses.add(
        responses.GET, f"{HA_BASE}/api/",
        body=ConnectionError("simulated"),
    )
    assert HAClient(HA_BASE, "tok").health_check() is False


@responses.activate
def test_converse_sends_bearer_token_and_agent_id():
    captured: dict = {}

    def callback(request):
        captured["auth"] = request.headers.get("Authorization")
        import json as _json
        captured["body"] = _json.loads(request.body)
        return (200, {}, '{"response": {"speech": {"plain": {"speech": "ok"}}}, "conversation_id": null}')

    responses.add_callback(
        responses.POST, f"{HA_BASE}/api/conversation/process", callback=callback,
    )
    HAClient(HA_BASE, "my-token").converse(
        "hello", agent_id="conversation.foo", conversation_id="prev-id",
    )
    assert captured["auth"] == "Bearer my-token"
    assert captured["body"]["text"] == "hello"
    assert captured["body"]["agent_id"] == "conversation.foo"
    assert captured["body"]["conversation_id"] == "prev-id"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|test_ha_client|ImportError" | head
```

Expected: ImportError on `ha_client`.

- [ ] **Step 3: Implement `ha_client.py`**

Create `ha_client.py` at the repo root:

```python
"""HTTP client for Home Assistant's conversation API.

Wraps POST /api/conversation/process. Returns normalized
ConversationResponse with success/error_code/speech_text shape.

Designed so playAIdes.chat() never has to interpret HA's response shape
or HTTP errors directly — it just gets a speech_text it can hand to TTS
and a success flag for branching.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class ConversationResponse:
    success: bool
    speech_text: str
    conversation_id: Optional[str]
    error_code: Optional[str]


# User-facing fallback strings. Kept here so they're easy to localize later.
_FALLBACK_NO_INTENT = "I didn't catch that — try rephrasing?"
_FALLBACK_UNREACHABLE = "I can't reach the house right now."
_FALLBACK_HTTP_ERROR = "I'm having trouble talking to the house — try again in a moment."


class HAClient:
    """Thin wrapper over HA's conversation REST endpoint."""

    def __init__(self, base_url: str, token: str, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def converse(
        self,
        text: str,
        agent_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ConversationResponse:
        url = f"{self.base_url}/api/conversation/process"
        body: dict = {"text": text}
        if agent_id:
            body["agent_id"] = agent_id
        if conversation_id:
            body["conversation_id"] = conversation_id

        try:
            resp = requests.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout, ConnectionError) as e:
            logger.warning("HA conversation unreachable: %s", e)
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_UNREACHABLE,
                conversation_id=None,
                error_code="ha_unreachable",
            )

        if resp.status_code != 200:
            logger.warning("HA conversation returned %s", resp.status_code)
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_HTTP_ERROR,
                conversation_id=None,
                error_code=f"ha_http_{resp.status_code}",
            )

        try:
            payload = resp.json()
        except ValueError as e:
            logger.warning("HA conversation returned non-JSON: %s", e)
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_HTTP_ERROR,
                conversation_id=None,
                error_code="ha_bad_json",
            )

        response_obj = payload.get("response", {}) or {}
        speech = (
            response_obj.get("speech", {}).get("plain", {}).get("speech")
            or ""
        )
        conv_id = payload.get("conversation_id")
        response_type = response_obj.get("response_type")
        error_code = (response_obj.get("data") or {}).get("code")

        if response_type == "error" or error_code:
            # HA understood our HTTP request but couldn't fulfill the intent.
            return ConversationResponse(
                success=False,
                speech_text=_FALLBACK_NO_INTENT,
                conversation_id=conv_id,
                error_code=error_code or "ha_response_error",
            )

        return ConversationResponse(
            success=True,
            speech_text=speech,
            conversation_id=conv_id,
            error_code=None,
        )

    def health_check(self) -> bool:
        try:
            resp = requests.get(
                f"{self.base_url}/api/",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `166 passed, 4 deselected` (was 158; +8 new).

- [ ] **Step 5: Commit**

```bash
git add ha_client.py tests/unit/test_ha_client.py
git commit -m "feat: ha_client.HAClient wraps HA's /api/conversation/process"
```

---

## Task 8: HA env wiring + `HAClient` construction in `PlayAIdes`

**Files:**
- Modify: `playAIdes.py` (`PlayAIdesArgs`, `__init__`)
- Modify: `main.py`

Add `--ha-url` / `--ha-token` / `--ha-default-agent-id` CLI args + env fallbacks. Construct `HAClient` only when both URL and token are set; warn at startup if a persona has `house_words` but no client / agent.

- [ ] **Step 1: Extend `PlayAIdesArgs`**

In `playAIdes.py`, add to `PlayAIdesArgs` after `api_key`:

```python
    ha_url: Optional[str] = None
    ha_token: Optional[str] = None
    ha_default_agent_id: Optional[str] = None
```

- [ ] **Step 2: Wire CLI args in `main.py`**

After the `--api-key` arg (Task 2), add:

```python
    parser.add_argument("--ha-url", type=str, default=None,
                        help="Home Assistant base URL (HA_URL env fallback). "
                             "Required for any HA feature.")
    parser.add_argument("--ha-token", type=str, default=None,
                        help="HA long-lived access token (HA_TOKEN env fallback).")
    parser.add_argument("--ha-default-agent-id", type=str, default=None,
                        help="HA conversation agent_id (HA_DEFAULT_AGENT_ID env "
                             "fallback). Used when a persona has no ha_agent_id.")
```

In the `casted_args = PlayAIdesArgs(...)` block, add:

```python
        ha_url=args.ha_url or os.environ.get("HA_URL"),
        ha_token=args.ha_token or os.environ.get("HA_TOKEN"),
        ha_default_agent_id=args.ha_default_agent_id
                            or os.environ.get("HA_DEFAULT_AGENT_ID"),
```

- [ ] **Step 3: Construct `HAClient` in `PlayAIdes.__init__`**

In `playAIdes.py`, near the top of `PlayAIdes.__init__` (after `self.args = args` or wherever args are stored), import and add:

```python
        from ha_client import HAClient
        self.ha_client: Optional[HAClient] = None
        if args.ha_url and args.ha_token:
            self.ha_client = HAClient(args.ha_url, args.ha_token)
            logger.info("HA client configured for %s", args.ha_url)
        elif args.ha_url or args.ha_token:
            logger.warning(
                "HA partially configured (need both ha_url and ha_token); "
                "HA features disabled."
            )

        # Per-persona conversation_id cache for HA's multi-turn context.
        # Cleared on persona dismiss/swap by Task 9 hook.
        self._ha_conversation_ids: dict[str, str] = {}
```

- [ ] **Step 4: Add startup warning for personas with house_words but no HA**

After persona loading (find where `self.list_personas()` or similar enumerates loaded personas — there's already loading code in `__init__`), add:

```python
        if not self.ha_client:
            for p in self.list_personas():
                if p.get("house_words"):
                    logger.warning(
                        "Persona %r has house_words but HA is not configured; "
                        "delegation will be disabled.",
                        p.get("name", "?"),
                    )
```

(If `self.list_personas()` isn't available at this point in `__init__`, look at the equivalent loop that already handles persona loading and piggy-back on it. The exact structure of persona iteration in this codebase is `Persona` objects in `self.personas` or similar — match what's there.)

- [ ] **Step 5: Verify nothing breaks**

```bash
make test 2>&1 | tail -3
```

Expected: `166 passed, 4 deselected` (count unchanged — wiring only).

- [ ] **Step 6: Commit**

```bash
git add playAIdes.py main.py
git commit -m "feat: HAClient construction + --ha-url/--ha-token CLI args + env fallbacks"
```

---

## Task 9: `chat()` routes to HA on house-word match (verbatim path)

**Files:**
- Modify: `playAIdes.py` (`chat()`)
- Modify: `tests/conftest.py` (add `mock_ha_client` fixture)
- Test: `tests/integration/test_ha_routing.py` (**create**)

The simplest delegation path: house word matches → HA call → speak the verbatim response. Rephrase + failure handling come in Tasks 10 and 11.

- [ ] **Step 1: Add the `mock_ha_client` fixture**

In `tests/conftest.py`, append:

```python
class _MockHAClient:
    """Test stub that returns scripted ConversationResponses.
    Use .script(speech_text=..., success=True, error_code=None) to enqueue
    one response per converse() call.
    """
    def __init__(self):
        self._queue: list = []
        self.calls: list[dict] = []

    def script(self, speech_text="OK", success=True,
               conversation_id=None, error_code=None):
        from ha_client import ConversationResponse
        self._queue.append(ConversationResponse(
            success=success, speech_text=speech_text,
            conversation_id=conversation_id, error_code=error_code,
        ))

    def converse(self, text, agent_id=None, conversation_id=None):
        self.calls.append({
            "text": text, "agent_id": agent_id,
            "conversation_id": conversation_id,
        })
        from ha_client import ConversationResponse
        if not self._queue:
            return ConversationResponse(
                True, "OK", None, None,
            )
        return self._queue.pop(0)

    def health_check(self):
        return True


@pytest.fixture
def mock_ha_client():
    return _MockHAClient()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/integration/test_ha_routing.py`:

```python
"""Integration tests for chat() routing to HA on house-word match."""
from __future__ import annotations

import json
import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


def _seed_persona_with_house_words(tmp_personas_dir, pid="silver",
                                    house_words=None,
                                    rephrase=False, agent_id=None):
    pdir = tmp_personas_dir / pid
    pdir.mkdir(exist_ok=True)
    persona = {
        "name": pid.capitalize(),
        "back_ground": "bg",
        "psyche": {"traits": []},
        "gender": "Female",
        "language": "English",
        "avatar": {"model_url": "x.vrm"},
        "house_words": house_words or [],
        "rephrase_ha_response": rephrase,
        "ha_agent_id": agent_id,
    }
    (pdir / "persona.json").write_text(json.dumps(persona))


@pytest.fixture
def play_with_ha(persona_file, fake_tts, no_incarnation, mock_ha_client):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False, use_voice=False,
        use_avatar=True, generate_avatar=False,
        llm=MockLLM(), tts=fake_tts,
    )
    play = PlayAIdes(args)
    # Inject the mock HA client post-construction.
    play.ha_client = mock_ha_client
    return play


class TestHouseWordRouting:
    def test_house_word_match_calls_ha_and_uses_verbatim_response(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], agent_id="conversation.foo",
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="Lights are off.")

        result = play_with_ha.chat("house turn off the lights")

        assert mock_ha_client.calls == [{
            "text": "turn off the lights",
            "agent_id": "conversation.foo",
            "conversation_id": None,
        }]
        assert result == "Lights are off."

    def test_no_house_word_match_uses_persona_llm(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver", house_words=["house"],
        )
        play_with_ha.set_persona("silver")
        result = play_with_ha.chat("how are you?")
        # No HA call.
        assert mock_ha_client.calls == []
        # MockLLM echoes the input.
        assert "how are you?" in result

    def test_empty_house_words_never_calls_ha(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(tmp_personas_dir, "silver", house_words=[])
        play_with_ha.set_persona("silver")
        play_with_ha.chat("house turn off the lights")
        assert mock_ha_client.calls == []
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|test_ha_routing|test_house_word" | head
```

Expected: 3 failures (chat doesn't route to HA).

- [ ] **Step 4: Add the routing branch in `chat()`**

In `playAIdes.py`, find `def chat(self, user_input: str, persona_id: Optional[str] = None) -> str:` (line 678). After the persona resolution + history append (which already happens early in chat), but **before** `response = self.llm.chat(...)` (around line 708), insert the HA routing block. The exact position: right before the existing `system_prompt = ...` / `response = self.llm.chat(...)` block. Read the existing chat() flow first to find the cleanest seam — there's a comment around persona resolution that's a good landmark.

```python
        # ─ HA delegation via house_words ────────────────────────────────
        from match_keywords import match_keyword_prefix
        house_words = self.current_persona.house_words or []
        matched, residual = match_keyword_prefix(user_input, house_words)
        if matched and self.ha_client:
            agent_id = (
                self.current_persona.ha_agent_id
                or self.args.ha_default_agent_id
            )
            conv_id = self._ha_conversation_ids.get(target_id)
            ha_resp = self.ha_client.converse(
                residual, agent_id=agent_id, conversation_id=conv_id,
            )
            if ha_resp.conversation_id:
                self._ha_conversation_ids[target_id] = ha_resp.conversation_id
            response = ha_resp.speech_text
        else:
            # ─ Existing persona-LLM path (unchanged) ────────────────────
            response = self.llm.chat(history, system_prompt=system_prompt)
```

(Replace the existing single `response = self.llm.chat(...)` line with this if/else block. Keep the existing system_prompt construction code that precedes it — it's only used in the `else` branch but it's cheap and the spec says "downstream code unchanged." Alternative: move system_prompt construction into the else branch if it's expensive.)

`target_id` should already be a local in `chat()` (used by the existing history routing) — if not, derive it from `persona_id` parameter or `self.current_persona`'s id field. Match exactly what the existing code does for `_save_history(target_id)`.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `169 passed, 4 deselected` (was 166; +3 new).

- [ ] **Step 6: Clear conversation cache on persona dismiss**

In `playAIdes.py`'s `_handle_incarnation_message`, find the existing `dismiss_persona` block (around line 508). Add inside that block, before the `return`:

```python
            # Drop any cached HA conversation_id for the dismissed persona
            # so the next session starts a fresh HA context.
            for ws, pid in list(self.incarnation_server._bindings.items()):
                self._ha_conversation_ids.pop(pid, None)
```

(Or simpler — just clear the entire dict if you're confident dismiss is per-binding. Per the WS code, dismiss is per-websocket; the binding is cleared by the WS layer immediately before this callback fires. So we can't easily know which persona was dismissed here. A pragmatic v1: clear on persona-swap instead. Add the same clear in `set_persona` before swapping current_persona.)

Pragmatic alternative — drop the dismiss-side clear and add to `set_persona` instead:

```python
def set_persona(self, persona_id: str) -> Optional[Persona]:
    ...existing body...
    # Reset HA conversation context on every persona change.
    self._ha_conversation_ids.pop(persona_id, None)
    ...
```

Pick one approach (the `set_persona`-side clear is recommended — simpler and equally correct).

- [ ] **Step 7: Re-run tests**

```bash
make test 2>&1 | tail -3
```

Expected: still `169 passed, 4 deselected`.

- [ ] **Step 8: Commit**

```bash
git add playAIdes.py tests/conftest.py tests/integration/test_ha_routing.py
git commit -m "feat: chat() routes to HA on house-word match (verbatim response path)"
```

---

## Task 10: Rephrase HA response through persona LLM

**Files:**
- Modify: `playAIdes.py` (`chat()`)
- Modify: `tests/integration/test_ha_routing.py`

When `persona.rephrase_ha_response` is true, take HA's `speech_text` and pass it through the persona's own LLM with a styling prompt before TTS.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_ha_routing.py`:

```python
class TestRephrase:
    def test_rephrase_enabled_calls_persona_llm_with_ha_response(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], rephrase=True,
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="Lights are off.")

        result = play_with_ha.chat("house turn off the lights")

        # HA was called once.
        assert len(mock_ha_client.calls) == 1
        # MockLLM echoes its last input — so the result should contain the
        # raw HA speech_text wrapped in the rephrase prompt.
        assert "Lights are off." in result

    def test_rephrase_disabled_skips_persona_llm(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], rephrase=False,
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="OK.")
        result = play_with_ha.chat("house turn off lights")
        # MockLLM echo would prefix with 'Mock Response:' — so absence
        # confirms the persona LLM was not called.
        assert "Mock Response" not in result
        assert result == "OK."
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|TestRephrase" | head
```

Expected: 1 failure (the first test — second already passes).

- [ ] **Step 3: Add the rephrase branch in `chat()`**

In the HA branch added in Task 9, after `response = ha_resp.speech_text`:

```python
            if (
                ha_resp.success
                and self.current_persona.rephrase_ha_response
            ):
                rephrase_prompt = (
                    f"You are {self.current_persona.name}. "
                    f"Rephrase this in your voice, keeping the meaning "
                    f"intact: {ha_resp.speech_text}"
                )
                try:
                    response = self.llm.chat(
                        [{"role": "user", "content": rephrase_prompt}],
                        system_prompt=None,
                    )
                except Exception as e:
                    logger.warning(
                        "Rephrase LLM call failed, falling back to verbatim: %s", e,
                    )
                    response = ha_resp.speech_text
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `171 passed, 4 deselected` (was 169; +2 new).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_ha_routing.py
git commit -m "feat: rephrase_ha_response routes HA speech_text through persona LLM"
```

---

## Task 11: Failure handling + empty residual

**Files:**
- Modify: `playAIdes.py` (`chat()`)
- Modify: `tests/integration/test_ha_routing.py`

Cover the remaining failure modes: empty residual after the house word, HA returns `success=False`, rephrase fails.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_ha_routing.py`:

```python
class TestEdgeCases:
    def test_empty_residual_speaks_default_phrase_no_ha_call(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver", house_words=["house"],
        )
        play_with_ha.set_persona("silver")
        result = play_with_ha.chat("house")
        assert mock_ha_client.calls == []
        assert result == "What about the house?"

    def test_ha_failure_speaks_fallback_no_rephrase(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], rephrase=True,  # rephrase ON but should be skipped
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(
            speech_text="I can't reach the house right now.",
            success=False, error_code="ha_unreachable",
        )
        result = play_with_ha.chat("house turn off lights")
        assert result == "I can't reach the house right now."
        # MockLLM was never called for rephrase (no Mock Response prefix).
        assert "Mock Response" not in result

    def test_rephrase_llm_failure_falls_back_to_verbatim(
        self, play_with_ha, tmp_personas_dir, mock_ha_client,
    ):
        _seed_persona_with_house_words(
            tmp_personas_dir, "silver",
            house_words=["house"], rephrase=True,
        )
        play_with_ha.set_persona("silver")
        mock_ha_client.script(speech_text="Lights are off.")

        # Make the LLM raise on this call.
        from model_interfaces import LLMError
        original_chat = play_with_ha.llm.chat
        def failing_chat(*a, **kw):
            raise LLMError("simulated")
        play_with_ha.llm.chat = failing_chat
        try:
            result = play_with_ha.chat("house turn off lights")
        finally:
            play_with_ha.llm.chat = original_chat

        assert result == "Lights are off."
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "FAILED|TestEdgeCases" | head
```

Expected: 1-3 failures depending on what the verbatim/rephrase code did before.

- [ ] **Step 3: Add empty-residual + failure short-circuit to `chat()`**

Modify the HA branch from Task 9. Before calling `ha_client.converse(...)`, add:

```python
        if matched and self.ha_client:
            if not residual:
                # House word with no follow-up — short-circuit, no HA call.
                response = "What about the house?"
            else:
                agent_id = (
                    self.current_persona.ha_agent_id
                    or self.args.ha_default_agent_id
                )
                conv_id = self._ha_conversation_ids.get(target_id)
                ha_resp = self.ha_client.converse(
                    residual, agent_id=agent_id, conversation_id=conv_id,
                )
                if ha_resp.conversation_id:
                    self._ha_conversation_ids[target_id] = ha_resp.conversation_id
                response = ha_resp.speech_text
                if (
                    ha_resp.success
                    and self.current_persona.rephrase_ha_response
                ):
                    rephrase_prompt = (
                        f"You are {self.current_persona.name}. "
                        f"Rephrase this in your voice, keeping the meaning "
                        f"intact: {ha_resp.speech_text}"
                    )
                    try:
                        response = self.llm.chat(
                            [{"role": "user", "content": rephrase_prompt}],
                            system_prompt=None,
                        )
                    except Exception as e:
                        logger.warning(
                            "Rephrase LLM call failed, falling back to verbatim: %s", e,
                        )
                        response = ha_resp.speech_text
        else:
            response = self.llm.chat(history, system_prompt=system_prompt)
```

(This is the consolidated final shape — replace the entire HA if/else block from Tasks 9 and 10 with this version.)

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `174 passed, 4 deselected` (was 171; +3 new).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_ha_routing.py
git commit -m "fix: chat() handles empty residual + HA failure + rephrase failure gracefully"
```

---

## Task 12: HA-side documentation

**Files:**
- Create: `docs/ha-integration.md`

No code, no tests. Just a copy-pasteable HA configuration reference.

- [ ] **Step 1: Write the doc**

Create `docs/ha-integration.md` with sections:

````markdown
# Home Assistant Integration

playAIdes can be driven from Home Assistant in two ways:
1. **HTTP triggers** — HA tells playAIdes to swap, dismiss, or query state.
2. **Skills delegation** — the user invokes HA's conversation agent through a persona by prefixing utterances with a configured "house word."

This doc is the HA-side configuration reference. The architecture is documented in `docs/superpowers/specs/2026-04-26-ha-integration-design.md`.

## Prerequisites

- A Home Assistant instance reachable from the playAIdes host.
- A long-lived access token. Settings → Profile → Long-Lived Access Tokens → Create Token. Copy the value immediately — HA does not store it.
- For skills: at least one configured conversation agent with an LLM backend (Settings → Voice Assistants → New Assistant → pick an LLM-backed agent like the OpenAI integration, Google AI, or HA's local LLM via Ollama).

## playAIdes-side environment

```bash
export PLAYAIDES_API_KEY="some-long-random-string"  # Bearer token HA must send
export HA_URL="http://homeassistant.local:8123"
export HA_TOKEN="<long-lived-token>"
export HA_DEFAULT_AGENT_ID="conversation.openai_assist"  # find in HA logs or Settings
```

`PLAYAIDES_API_KEY` left unset = dev mode (no auth check, with a startup warning). Do NOT leave it unset on a network-exposed host.

## HA-side YAML

### `secrets.yaml`

```yaml
playaides_api_key: "Bearer some-long-random-string"
```

### `configuration.yaml` — `rest_command:` block

```yaml
rest_command:
  playaides_activate_persona:
    url: "http://playaides.local:8765/api/personas/{{ persona_id }}/activate"
    method: POST
    headers:
      Authorization: !secret playaides_api_key
    timeout: 5

  playaides_dismiss:
    url: "http://playaides.local:8765/api/dismiss"
    method: POST
    headers:
      Authorization: !secret playaides_api_key
    timeout: 5
```

### Sample automations

**Show Silver in the kitchen at 7 AM:**
```yaml
alias: Morning Silver
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: rest_command.playaides_activate_persona
    data:
      persona_id: silver
  - action: fully_kiosk.load_url
    data:
      url: "http://playaides.local:8765/?persona=silver"
    target:
      device_id: <kitchen-tablet-device-id>
```

**Bedtime — dismiss across all TVs:**
```yaml
alias: Bedtime Persona Dismiss
triggers:
  - trigger: state
    entity_id: input_boolean.bedtime_routine
    to: "on"
actions:
  - action: rest_command.playaides_dismiss
```

### Polling state for a dashboard widget

```yaml
sensor:
  - platform: rest
    name: PlayAIdes Active Persona
    resource: http://playaides.local:8765/api/state
    value_template: "{{ value_json.active_persona_id or 'none' }}"
    json_attributes:
      - bound_client_count
    scan_interval: 30
```

(`/api/state` is unauthenticated by design — read-only, no PII.)

## Per-persona skills config (`personas/<id>/persona.json`)

```jsonc
{
  "name": "Silver",
  "wake_words": ["Hey Silver"],
  "dismiss_words": ["Goodnight Silver"],

  "house_words": ["house"],
  "rephrase_ha_response": false,
  "ha_agent_id": "conversation.openai_assist"
}
```

- `house_words`: keywords (case-insensitive, prefix-only) that route the residual to HA. Empty = HA delegation disabled.
- `rephrase_ha_response`: if true, HA's response is restyled by the persona's own LLM before TTS. Adds latency.
- `ha_agent_id`: which HA conversation agent to address. Omit to use `HA_DEFAULT_AGENT_ID`.

Find your agent_id in Settings → Voice Assistants — the entity_id pattern is `conversation.<name>`.

## Manual smoke test

1. Start playAIdes with the env vars above set.
2. Open the viewer: `http://playaides.local:8765/?persona=silver`.
3. From a host that can reach playAIdes:
   ```bash
   # Activate (no browser reload):
   curl -X POST -H "Authorization: $PLAYAIDES_API_KEY" \
     http://playaides.local:8765/api/personas/silver/activate

   # State:
   curl http://playaides.local:8765/api/state

   # Dismiss:
   curl -X POST -H "Authorization: $PLAYAIDES_API_KEY" \
     http://playaides.local:8765/api/dismiss
   ```
4. With Silver active, say or type "house, what's the temperature in the kitchen". Confirm:
   - Lipsync fires.
   - HA logs (`config/home-assistant.log`) show a conversation hit.
   - The response matches what HA's conversation agent returned (or a rephrased version if you enabled `rephrase_ha_response`).

## Future phases (not yet implemented)

- **Phase 3**: HA → persona event-driven automations (e.g. "door opened → say welcome home"). See spec § 7.1.
- **Phase 4**: HACS `homeassistant-playaides` custom_component so HA voice satellites can use a persona as their conversation agent. See spec § 7.2.
````

- [ ] **Step 2: Verify nothing breaks**

```bash
make test 2>&1 | tail -3
```

Expected: `174 passed, 4 deselected` (count unchanged).

- [ ] **Step 3: Commit**

```bash
git add docs/ha-integration.md
git commit -m "docs: HA integration YAML + manual smoke recipe"
```

---

## Task 13: End-of-pass smoke + final review

**Files:** none — verification only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `174 passed, 4 deselected` (or close — 17 new tests since baseline of 138).

- [ ] **Step 2: Frontend tests still green**

```bash
make test-js 2>&1 | tail -10
```

Expected: `89 passed (89)` — unchanged since no frontend code was touched.

- [ ] **Step 3: Linter/type-check (if configured)**

```bash
# If the project uses one — check Makefile for a `lint` or `typecheck` target.
grep -E "^(lint|typecheck|mypy|ruff):" Makefile && make lint
```

If neither target exists, skip — this project doesn't currently lint as part of CI.

- [ ] **Step 4: Self-review checklist**

- [ ] All 6 components from spec § 3 implemented.
- [ ] All 3 data-flow scenarios from spec § 4 testable end-to-end (Scenario A by activating endpoint test; Scenario B by routing tests; Scenario C by edge-case tests).
- [ ] All 7 failure modes from spec § 4.3 have a corresponding test or an explicit "covered by health_check" note.
- [ ] No new TODO / FIXME / TBD strings (`grep -nE "TODO|FIXME|TBD" $(git diff --name-only main..HEAD | grep -E "\.(py|md)$")`).
- [ ] Persona schema is backwards-compatible: a `persona.json` from before this branch loads cleanly with all new fields defaulting (Task 1's second test asserts this).
- [ ] No dependency added to `pyproject.toml` beyond what was already there (the spec assumed `responses` was already present — Task 0 verified).
- [ ] Spec sections 7.1, 7.2, 7.3, 7.4 — all out-of-scope items remain unimplemented (no code added for Phase 3, Phase 4, persona-LLM tool-calling, or TV identity).

- [ ] **Step 5: No commit (process marker)**

---

## Self-review checklist (run before marking implementation done)

- [ ] **Spec coverage**: every section of the spec maps to a Task above.
- [ ] **No placeholders**: no TBD/TODO/FIXME in any plan task.
- [ ] **Type / name consistency**: `house_words`, `rephrase_ha_response`, `ha_agent_id`, `HAClient`, `ConversationResponse`, `match_keyword_prefix`, `_ha_conversation_ids`, `require_api_key`, `state_provider` — same names everywhere they appear.
- [ ] **No silent scope creep**: every task is a fix/feature/refactor that maps directly to a spec component.
- [ ] **Backwards compat preserved**: existing `persona.json` files load; no existing endpoints broken; no existing tests regressed.
