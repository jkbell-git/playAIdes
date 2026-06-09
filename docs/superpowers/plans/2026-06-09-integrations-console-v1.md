# Integrations Console v1 Implementation Plan — Slice 1 of the architecture redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a system-level config console that lets the operator connect Home Assistant (behind a generic provider seam), scan it for entities, and map them to playAIdes capabilities (PiP display, launch targets, scripts) — replacing hardcoded config, starting with the Fire-TV launch targets.

**Architecture:** This is **slice 1** of the clean re-architecture (see `docs/superpowers/specs/2026-06-09-backend-frontend-architecture-redesign.md`) — the greenfield reference implementation of the new layered backend. New code lives under a **`backend/` package** (`api / clients / stores`); the existing flat root modules stay put and migrate in later slices (strangler-fig). The console is a thin **`APIRouter`** (`/api/v1/integrations`, behind an extracted `require_api_key` dependency) over a **provider seam** (`health/discover/invoke`, HA wrapping the root `ha_client.py`), a **config store** + **write-only secrets store**, and a one-time **migration seed**. A **React master–detail console** page is added to the Vite MPA; the first consumer rewired to read the store is `bin/silver-launch.py`.

**Tech Stack:** Python 3.11 · FastAPI (`APIRouter`) · `requests` (HTTP) · `responses` (HTTP mocking in unit tests) · pytest (`bin/test`) · Vite 7 MPA · React 18 + `@vitejs/plugin-react` · Vitest (`bin/test-js`).

---

## Conventions for every task

- **Run Python tests with:** `bin/test pytest <path>::<test> -v` — runs pytest **inside** the Docker test container (repo bind-mounted read-only at `/app`, `PYTHONPATH=/app`, coverage to `/out`). Args after `bin/test` replace the compose `command`. The new `backend/` package is importable because `/app` is on `PYTHONPATH` (it has `__init__.py` markers from Task 0).
- **Run JS tests with:** `bin/test-js` (runs `npx vitest run` in `incarnation/`). Vitest's `include` is `src/**/*.test.js`, so logic tests live next to their module as `*.test.js`.
- **Config/secrets writes in tests must target a tmp dir** — never the repo. The `incarnation_server`/`client` integration fixtures already `monkeypatch.chdir(tmp_path)`; unit tests pass an explicit `path=tmp_path/...`.
- **The HA token never passes through chat, argv, or any tool output.** It is POSTed once to the secret endpoint, persisted server-side, and never returned.
- **Layer rule:** `backend/api` → `backend/services` (none in this slice) → `backend/clients` / `backend/stores`. Imports point downward only. The console routes hold **no server-instance state** — that's why they live in a standalone router.
- **Commit after each task** with the message shown in its final step.

## File Structure

**New `backend/` package (Task 0 scaffolds the dirs + markers):**
- `backend/__init__.py`, `backend/api/__init__.py`, `backend/clients/__init__.py`, `backend/clients/providers/__init__.py`, `backend/stores/__init__.py` — package markers.
- `backend/api/deps.py` — `require_api_key` (extracted from the `incarnation_server.py` nested closure; reusable + testable).
- `backend/api/integrations.py` — the console `APIRouter` (`/api/v1/integrations`) + request bodies.
- `backend/clients/providers/base.py` — `Provider` ABC + `Status` / `Item` + capability-key constants. The seam contract.
- `backend/clients/providers/fake.py` — `FakeProvider` (locks the seam; v2/v3 template).
- `backend/clients/providers/homeassistant.py` — `HomeAssistantProvider`, wrapping the **root** `ha_client.HAClient`.
- `backend/clients/providers/registry.py` — `build_provider(provider_id)`: reads the store + resolves the token, builds the provider. The single seam tests/routes monkeypatch.
- `backend/stores/config_store.py` — typed atomic load/save of `config/integrations.json` + `seed_if_absent`.
- `backend/stores/secrets_store.py` — write-only `config/secrets.json` (atomic) + `resolve_token` (file → `HA_TOKEN` env).
- `backend/stores/launch_targets.py` — `DEFAULT_LAUNCH_TARGETS` + `load_launch_targets()` (store → fallback).

**Modified (stay at repo root this slice — strangler-fig):**
- `ha_client.py` — add `get_states()` and `call_service()` (HA provider imports it).
- `incarnation_server.py` — delegate the nested `require_api_key` to `backend/api/deps.py`; `include_router(integrations_router)`; startup migration seed; serve `/console`.
- `bin/silver-launch.py` — resolve launch targets from the store via `backend.stores.launch_targets`.
- `pyproject.toml` — register the `backend` package. `.gitignore` — ignore the runtime config files.

**Runtime data (repo-root, gitignored — it's data, not code):** `config/integrations.json`, `config/secrets.json`.

**New frontend (Vite MPA entry: console):**
- `incarnation/vite.config.js` — **new** MPA config (`rollupOptions.input` for index/creator/design-preview/console) + `@vitejs/plugin-react`.
- `incarnation/package.json` — add `react`, `react-dom`, `@vitejs/plugin-react`.
- `incarnation/console.html` · `incarnation/src/console/main.jsx` · `incarnation/src/console/App.jsx`
- `incarnation/src/console/consoleApi.js` (fetch wrappers, hits `/api/v1/integrations`) · `incarnation/src/console/mappingsModel.js` (pure helpers) · `incarnation/styles/console.css`.

**New tests:**
- `tests/unit/`: `test_deps_auth.py`, `test_provider_seam.py`, `test_ha_provider.py`, `test_config_store.py`, `test_secrets_store.py`, `test_ha_client_states.py`, `test_launch_targets.py`, `test_silver_launch_targets.py`
- `tests/integration/test_integrations_endpoints.py`
- `incarnation/src/console/mappingsModel.test.js`, `incarnation/src/console/consoleApi.test.js`

---

## Task 0: Scaffold the `backend` package + extract the auth dependency

**Files:**
- Create: `backend/__init__.py`, `backend/api/__init__.py`, `backend/clients/__init__.py`, `backend/clients/providers/__init__.py`, `backend/stores/__init__.py`
- Create: `backend/api/deps.py`
- Modify: `incarnation_server.py` (delegate to the extracted dependency)
- Modify: `pyproject.toml` (register the `backend` package)
- Test: `tests/unit/test_deps_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_deps_auth.py
"""require_api_key extracted to backend.api.deps — reusable + unit-testable."""
import pytest
from fastapi import HTTPException

from backend.api.deps import require_api_key


def test_dev_mode_no_key_allows(monkeypatch):
    monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)
    assert require_api_key(authorization=None) is None  # dev convenience: no gate


def test_missing_bearer_rejected(monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "k")
    with pytest.raises(HTTPException) as e:
        require_api_key(authorization=None)
    assert e.value.status_code == 401


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "k")
    with pytest.raises(HTTPException):
        require_api_key(authorization="Bearer nope")


def test_correct_token_passes(monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "k")
    assert require_api_key(authorization="Bearer k") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_deps_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend'`.

- [ ] **Step 3a: Create the package markers**

Create these five files, each empty (or a one-line docstring):

```python
# backend/__init__.py
"""playAIdes backend — layered: api / clients / stores (see the architecture spec)."""
```

```python
# backend/api/__init__.py
```
```python
# backend/clients/__init__.py
```
```python
# backend/clients/providers/__init__.py
```
```python
# backend/stores/__init__.py
```

- [ ] **Step 3b: Create the extracted auth dependency**

```python
# backend/api/deps.py
"""Shared FastAPI dependencies for the api layer."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException


def require_api_key(authorization: Optional[str] = Header(default=None)):
    """Bearer-token gate. Dev mode (PLAYAIDES_API_KEY unset) = no auth (logged at
    startup elsewhere). Moved verbatim from incarnation_server._setup_routes so it
    can be reused by routers and unit-tested directly."""
    expected = os.environ.get("PLAYAIDES_API_KEY")
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.removeprefix("Bearer ") != expected:
        raise HTTPException(status_code=401, detail="invalid bearer token")
```

- [ ] **Step 3c: Point the existing server at the extracted dependency**

In `incarnation_server.py`, add to the top-level imports:

```python
from backend.api.deps import require_api_key
```

Then **delete** the nested `def require_api_key(...)` block inside `_setup_routes` (`incarnation_server.py:123-131`). The existing routes still reference the name `require_api_key`; it now resolves to the imported one (identical behavior).

- [ ] **Step 3d: Register the package for setuptools**

In `pyproject.toml`, under `[tool.setuptools.packages.find]`, add `"backend*"` to `include`:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["voice_generation*", "backend*"]
exclude = ["voice_generation.voice_server*", "tests*", "incarnation*", "personas*"]
```

- [ ] **Step 4: Run tests to verify they pass (+ regression on the wired auth)**

Run: `bin/test pytest tests/unit/test_deps_auth.py tests/integration/test_ha_trigger_endpoints.py -v`
Expected: PASS — the 4 new unit tests pass, and the existing auth integration tests (which exercise `require_api_key` through the server) still pass, proving the delegation didn't change behavior.

- [ ] **Step 5: Commit**

```bash
git add backend/ tests/unit/test_deps_auth.py incarnation_server.py pyproject.toml
git commit -m "feat(backend): scaffold backend package + extract require_api_key dependency"
```

---

## Task 1: Provider seam contract + fake provider

**Files:**
- Create: `backend/clients/providers/base.py`
- Create: `backend/clients/providers/fake.py`
- Test: `tests/unit/test_provider_seam.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_provider_seam.py
"""The fake provider locks the seam contract and templates v2/v3 providers."""
from backend.clients.providers.base import Provider, Status, Item, CAP_PIP
from backend.clients.providers.fake import FakeProvider


def test_fake_provider_satisfies_the_seam():
    p = FakeProvider(
        items=[Item(id="camera.front", domain="camera", name="Front",
                    capabilities=[CAP_PIP])],
        healthy=True,
    )
    assert isinstance(p, Provider)
    assert p.kind == "fake"

    health = p.health()
    assert isinstance(health, Status)
    assert health.ok is True

    items = p.discover()
    assert [i.id for i in items] == ["camera.front"]
    assert items[0].capabilities == [CAP_PIP]

    result = p.invoke(CAP_PIP, "camera.front", {"preview": True})
    assert result["ok"] is True
    assert p.invocations == [(CAP_PIP, "camera.front", {"preview": True})]


def test_fake_provider_reports_unhealthy_with_reason():
    s = FakeProvider(healthy=False).health()
    assert s.ok is False
    assert s.reason  # non-empty human-readable reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_provider_seam.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.clients.providers.base'`.

- [ ] **Step 3: Write the seam + fake provider**

```python
# backend/clients/providers/base.py
"""The provider seam — deliberately small so HA's needs shape it without over-fitting.

A provider connects one external service, reports its health, discovers the
entities it exposes (normalized), and invokes a capability against a target.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# playAIdes capability keys — generic, provider-agnostic. A discovered Item advertises
# which of these it can fill. Most map to a single (provider, entity); `pip` is a generic
# display slot whose mapping is a typed source — {kind:"camera", provider, entity} or
# {kind:"url", url} — so a camera is just one PiP source among others.
CAP_PIP = "pip"
CAP_SAY_TARGET = "say_target"
CAP_LAUNCH_TARGETS = "launch_targets"
CAP_SCRIPTS = "scripts"


@dataclass
class Status:
    ok: bool
    reason: Optional[str] = None  # human-readable failure reason; None when ok


@dataclass
class Item:
    """A normalized, discovered entity."""
    id: str                       # provider-native id, e.g. "camera.front_door"
    domain: str                   # grouping key, e.g. "camera"
    name: str                     # friendly name
    capabilities: list[str] = field(default_factory=list)  # caps it can fill


class Provider(ABC):
    kind: str                     # e.g. "homeassistant"
    config_schema: list[str] = [] # non-secret config fields needed to connect

    @abstractmethod
    def health(self) -> Status: ...

    @abstractmethod
    def discover(self) -> list[Item]: ...

    @abstractmethod
    def invoke(self, capability: str, target: str, args: Optional[dict] = None) -> dict: ...
```

```python
# backend/clients/providers/fake.py
"""In-memory provider implementing the seam — used in tests and as the v2/v3 template."""
from __future__ import annotations

from typing import Optional

from backend.clients.providers.base import Provider, Status, Item


class FakeProvider(Provider):
    kind = "fake"
    config_schema = ["base_url"]

    def __init__(self, items: Optional[list[Item]] = None, healthy: bool = True):
        self._items = list(items or [])
        self._healthy = healthy
        self.invocations: list[tuple] = []

    def health(self) -> Status:
        if self._healthy:
            return Status(ok=True)
        return Status(ok=False, reason="fake provider is offline")

    def discover(self) -> list[Item]:
        return list(self._items)

    def invoke(self, capability: str, target: str, args: Optional[dict] = None) -> dict:
        args = args or {}
        self.invocations.append((capability, target, args))
        return {"ok": True, "capability": capability, "target": target}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_provider_seam.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/clients/providers/base.py backend/clients/providers/fake.py tests/unit/test_provider_seam.py
git commit -m "feat(providers): add provider seam contract + fake provider"
```

---

## Task 2: Config store (atomic load/save)

**Files:**
- Create: `backend/stores/config_store.py`
- Test: `tests/unit/test_config_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config_store.py
import json
from pathlib import Path

from backend.stores import config_store


def test_load_missing_returns_empty_skeleton(tmp_path: Path):
    data = config_store.load(str(tmp_path / "integrations.json"))
    assert data == {"providers": {}, "mappings": {}}


def test_save_then_load_roundtrips(tmp_path: Path):
    path = str(tmp_path / "config" / "integrations.json")  # nested dir is created
    payload = {"providers": {"homeassistant": {"kind": "homeassistant"}},
               "mappings": {"launch_targets": []}}
    config_store.save(payload, path)
    assert json.loads(Path(path).read_text()) == payload
    assert config_store.load(path) == payload


def test_save_is_atomic_no_tmp_left_behind(tmp_path: Path):
    path = str(tmp_path / "integrations.json")
    config_store.save({"providers": {}, "mappings": {}}, path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_config_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.stores.config_store'`.

- [ ] **Step 3: Write the config store (load/save only — seed comes in Task 7)**

```python
# backend/stores/config_store.py
"""Typed load/save for the integrations config store (config/integrations.json).

The single source of truth for provider connection config and capability->entity
mappings. Writes are atomic (temp file + os.replace) so a mid-write crash never
corrupts the file. The HA token is NOT stored here — see secrets_store.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

DEFAULT_PATH = "config/integrations.json"


def _empty() -> dict:
    return {"providers": {}, "mappings": {}}


def load(path: str = DEFAULT_PATH) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return _empty()


def save(data: dict, path: str = DEFAULT_PATH) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)  # atomic on POSIX
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_config_store.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/stores/config_store.py tests/unit/test_config_store.py
git commit -m "feat(stores): add atomic integrations config store"
```

---

## Task 3: Secrets store + token resolver (write-only)

**Files:**
- Create: `backend/stores/secrets_store.py`
- Test: `tests/unit/test_secrets_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_secrets_store.py
from pathlib import Path

from backend.stores import secrets_store


def test_set_then_get_secret(tmp_path: Path):
    path = str(tmp_path / "config" / "secrets.json")
    secrets_store.set_secret("homeassistant", "token", "shhh", path)
    assert secrets_store.get_secret("homeassistant", "token", path) == "shhh"


def test_get_missing_secret_returns_none(tmp_path: Path):
    path = str(tmp_path / "secrets.json")
    assert secrets_store.get_secret("homeassistant", "token", path) is None


def test_resolve_token_prefers_file_over_env(tmp_path: Path):
    path = str(tmp_path / "secrets.json")
    secrets_store.set_secret("homeassistant", "token", "from-file", path)
    tok = secrets_store.resolve_token("homeassistant", path, env={"HA_TOKEN": "from-env"})
    assert tok == "from-file"


def test_resolve_token_falls_back_to_env(tmp_path: Path):
    path = str(tmp_path / "secrets.json")  # no file written
    tok = secrets_store.resolve_token("homeassistant", path, env={"HA_TOKEN": "from-env"})
    assert tok == "from-env"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_secrets_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.stores.secrets_store'`.

- [ ] **Step 3: Write the secrets store**

```python
# backend/stores/secrets_store.py
"""Write-only secrets store for provider credentials (config/secrets.json).

Secrets are POSTed once to the API, persisted here, and NEVER returned to the
browser or echoed in any response. `resolve_token` reads this file first and
falls back to the HA_TOKEN env var so existing .env-based setups keep working.
Writes are atomic.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Optional

DEFAULT_PATH = "config/secrets.json"


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def set_secret(provider_id: str, key: str, value: str, path: str = DEFAULT_PATH) -> None:
    data = _load(path)
    data.setdefault(provider_id, {})[key] = value
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def get_secret(provider_id: str, key: str, path: str = DEFAULT_PATH) -> Optional[str]:
    return (_load(path).get(provider_id) or {}).get(key)


def resolve_token(provider_id: str = "homeassistant", path: str = DEFAULT_PATH,
                  env: Optional[dict] = None) -> Optional[str]:
    """Resolve the provider token: secrets file first, then HA_TOKEN env fallback."""
    from_file = get_secret(provider_id, "token", path)
    if from_file:
        return from_file
    return (env if env is not None else os.environ).get("HA_TOKEN")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_secrets_store.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/stores/secrets_store.py tests/unit/test_secrets_store.py
git commit -m "feat(stores): add write-only secrets store + token resolver"
```

---

## Task 4: Extend HAClient with `get_states()` and `call_service()`

**Files:**
- Modify: `ha_client.py` (root — add two methods to `HAClient`, after `health_check`, around `ha_client.py:164`)
- Test: `tests/unit/test_ha_client_states.py`

`ha_client.py` stays at the repo root this slice (it's consumed by `playAIdes.py` too); it re-homes to `backend/clients/ha.py` in a later slice.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ha_client_states.py
"""Unit tests for HAClient.get_states / call_service (HTTP mocked with `responses`)."""
import responses

from ha_client import HAClient

HA_BASE = "http://ha.test:8123"


@responses.activate
def test_get_states_returns_list():
    responses.add(
        responses.GET, f"{HA_BASE}/api/states",
        json=[{"entity_id": "camera.front", "attributes": {"friendly_name": "Front"}}],
        status=200,
    )
    out = HAClient(HA_BASE, "tok").get_states()
    assert out == [{"entity_id": "camera.front", "attributes": {"friendly_name": "Front"}}]


@responses.activate
def test_get_states_returns_none_on_error():
    responses.add(responses.GET, f"{HA_BASE}/api/states", status=500)
    assert HAClient(HA_BASE, "tok").get_states() is None


@responses.activate
def test_call_service_true_on_200_and_sends_bearer():
    captured = {}

    def cb(request):
        captured["auth"] = request.headers.get("Authorization")
        return (200, {}, "[]")

    responses.add_callback(
        responses.POST, f"{HA_BASE}/api/services/script/turn_on", callback=cb,
    )
    ok = HAClient(HA_BASE, "my-token").call_service(
        "script", "turn_on", {"entity_id": "script.greet"})
    assert ok is True
    assert captured["auth"] == "Bearer my-token"


@responses.activate
def test_call_service_false_on_network_error():
    responses.add(
        responses.POST, f"{HA_BASE}/api/services/script/turn_on",
        body=ConnectionError("down"),
    )
    assert HAClient(HA_BASE, "tok").call_service("script", "turn_on", {}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_ha_client_states.py -v`
Expected: FAIL — `AttributeError: 'HAClient' object has no attribute 'get_states'`.

- [ ] **Step 3: Add the two methods**

Insert after the `health_check` method (end of the class, `ha_client.py:164`):

```python
    def get_states(self) -> Optional[list]:
        """GET /api/states — all entities. Returns the raw list, or None on any
        error (unreachable, non-200, non-JSON). The provider normalizes."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/states",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout, ConnectionError) as e:
            logger.warning("HA states unreachable: %s", e)
            return None
        if resp.status_code != 200:
            logger.warning("HA states returned %s", resp.status_code)
            return None
        try:
            return resp.json()
        except ValueError:
            logger.warning("HA states returned non-JSON")
            return None

    def call_service(self, domain: str, service: str, data: dict) -> bool:
        """POST /api/services/<domain>/<service>. Returns True on HTTP 200,
        False on any error. Used by the provider's invoke() test-fire."""
        try:
            resp = requests.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                json=data,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout, ConnectionError) as e:
            logger.warning("HA service %s/%s unreachable: %s", domain, service, e)
            return False
        return resp.status_code == 200
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_ha_client_states.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ha_client.py tests/unit/test_ha_client_states.py
git commit -m "feat(ha): add HAClient.get_states and call_service"
```

---

## Task 5: Home Assistant provider (discover / health / invoke)

**Files:**
- Create: `backend/clients/providers/homeassistant.py`
- Test: `tests/unit/test_ha_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ha_provider.py
"""HomeAssistantProvider normalizes /api/states and routes invoke() (HTTP mocked)."""
import responses

from backend.clients.providers.base import Status, CAP_PIP, CAP_SCRIPTS, CAP_LAUNCH_TARGETS
from backend.clients.providers.homeassistant import HomeAssistantProvider

HA_BASE = "http://ha.test:8123"


def _provider():
    return HomeAssistantProvider(HA_BASE, "tok")


@responses.activate
def test_health_ok_when_api_reachable():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=200)
    s = _provider().health()
    assert isinstance(s, Status) and s.ok is True


@responses.activate
def test_health_reports_reason_when_unreachable():
    responses.add(responses.GET, f"{HA_BASE}/api/", status=401)
    s = _provider().health()
    assert s.ok is False and s.reason


@responses.activate
def test_discover_keeps_only_v1_domains_and_normalizes():
    responses.add(
        responses.GET, f"{HA_BASE}/api/states",
        json=[
            {"entity_id": "camera.front", "attributes": {"friendly_name": "Front Cam"}},
            {"entity_id": "media_player.tv", "attributes": {"friendly_name": "TV"}},
            {"entity_id": "script.greet", "attributes": {}},
            {"entity_id": "sun.sun", "attributes": {"friendly_name": "Sun"}},  # dropped
        ],
        status=200,
    )
    items = _provider().discover()
    assert [i.id for i in items] == ["camera.front", "media_player.tv", "script.greet"]
    cam = items[0]
    assert cam.domain == "camera"
    assert cam.name == "Front Cam"
    assert CAP_PIP in cam.capabilities
    mp = items[1]
    assert set(mp.capabilities) == {"say_target", CAP_LAUNCH_TARGETS}
    assert items[2].name == "script.greet"  # friendly_name absent -> entity_id


@responses.activate
def test_invoke_camera_returns_resolved_url():
    responses.add(
        responses.GET, f"{HA_BASE}/api/states/camera.front",
        json={"attributes": {"access_token": "abc"}}, status=200,
    )
    out = _provider().invoke(CAP_PIP, "camera.front")
    assert out["ok"] is True
    assert out["url"].endswith("/api/camera_proxy/camera.front?token=abc")


@responses.activate
def test_invoke_script_fires_service():
    responses.add(
        responses.POST, f"{HA_BASE}/api/services/script/turn_on", json=[], status=200,
    )
    out = _provider().invoke(CAP_SCRIPTS, "script.greet")
    assert out["ok"] is True


def test_invoke_unsupported_capability_is_handled():
    out = _provider().invoke("nope", "x")
    assert out["ok"] is False and out["reason"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_ha_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.clients.providers.homeassistant'`.

- [ ] **Step 3: Write the HA provider**

```python
# backend/clients/providers/homeassistant.py
"""Home Assistant provider — wraps the (root) HAClient behind the seam.

discover() reads GET /api/states and surfaces only the v1 domains; invoke()
test-fires a capability (resolve a camera URL, or run a script).
"""
from __future__ import annotations

from typing import Optional

from ha_client import HAClient  # root module (re-homed to backend/clients/ha.py later)
from backend.clients.providers.base import (
    Provider, Status, Item,
    CAP_PIP, CAP_SAY_TARGET, CAP_LAUNCH_TARGETS, CAP_SCRIPTS,
)

# HA domains surfaced in v1, and which playAIdes capabilities each can fill.
_DOMAIN_CAPS: dict[str, list[str]] = {
    "camera": [CAP_PIP],
    "media_player": [CAP_SAY_TARGET, CAP_LAUNCH_TARGETS],
    "script": [CAP_SCRIPTS],
}


class HomeAssistantProvider(Provider):
    kind = "homeassistant"
    config_schema = ["base_url"]

    def __init__(self, base_url: str, token: str, timeout: float = 5.0):
        self._client = HAClient(base_url, token, timeout=timeout)

    def health(self) -> Status:
        if self._client.health_check():
            return Status(ok=True)
        return Status(ok=False, reason="Home Assistant unreachable or token rejected")

    def discover(self) -> list[Item]:
        states = self._client.get_states() or []
        items: list[Item] = []
        for s in states:
            entity_id = s.get("entity_id", "")
            domain = entity_id.split(".", 1)[0] if "." in entity_id else ""
            caps = _DOMAIN_CAPS.get(domain)
            if not caps:
                continue
            name = (s.get("attributes") or {}).get("friendly_name") or entity_id
            items.append(Item(id=entity_id, domain=domain, name=name,
                              capabilities=list(caps)))
        items.sort(key=lambda i: (i.domain, i.id))
        return items

    def invoke(self, capability: str, target: str, args: Optional[dict] = None) -> dict:
        if capability == CAP_PIP:
            # Camera-kind PiP source: resolve the live, token-rotating stream URL.
            # (url-kind PiP sources are operator-entered and never reach a provider.)
            url = self._client.camera_url(target)
            if url:
                return {"ok": True, "url": url}
            return {"ok": False, "reason": "camera entity did not resolve to a stream"}
        if capability == CAP_SCRIPTS:
            ok = self._client.call_service("script", "turn_on", {"entity_id": target})
            return {"ok": ok} if ok else {"ok": False, "reason": "script service call failed"}
        return {"ok": False, "reason": f"unsupported capability {capability!r}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_ha_provider.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/clients/providers/homeassistant.py tests/unit/test_ha_provider.py
git commit -m "feat(providers): add Home Assistant provider (discover/health/invoke)"
```

---

## Task 6: Launch-target defaults + store-aware loader

**Files:**
- Create: `backend/stores/launch_targets.py`
- Test: `tests/unit/test_launch_targets.py`

Single source of truth for the Fire-TV defaults, imported by both the migration seed (Task 7) and `bin/silver-launch.py` (Task 12).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_launch_targets.py
import json
from pathlib import Path

from backend.stores import launch_targets


def test_defaults_present():
    assert set(launch_targets.DEFAULT_LAUNCH_TARGETS) == {"bedroom", "box8", "living"}


def test_load_falls_back_when_store_missing(tmp_path: Path):
    out = launch_targets.load_launch_targets(
        store_path=str(tmp_path / "nope.json"),
        fallback=launch_targets.DEFAULT_LAUNCH_TARGETS,
    )
    assert out == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_load_reads_launch_targets_from_store(tmp_path: Path):
    path = tmp_path / "integrations.json"
    path.write_text(json.dumps({
        "mappings": {"launch_targets": [
            {"provider": "homeassistant", "entity": "media_player.tv_a", "label": "den"},
            {"provider": "homeassistant", "entity": "media_player.tv_b", "label": "office"},
        ]}
    }))
    out = launch_targets.load_launch_targets(
        store_path=str(path), fallback=launch_targets.DEFAULT_LAUNCH_TARGETS)
    assert out == {"den": "media_player.tv_a", "office": "media_player.tv_b"}


def test_load_falls_back_when_mapping_empty(tmp_path: Path):
    path = tmp_path / "integrations.json"
    path.write_text(json.dumps({"mappings": {"launch_targets": []}}))
    out = launch_targets.load_launch_targets(
        store_path=str(path), fallback=launch_targets.DEFAULT_LAUNCH_TARGETS)
    assert out == launch_targets.DEFAULT_LAUNCH_TARGETS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_launch_targets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.stores.launch_targets'`.

- [ ] **Step 3: Write the module**

```python
# backend/stores/launch_targets.py
"""Fire-TV launch targets — the canonical defaults plus a store-aware loader.

Single source of truth shared by the migration seed (config_store.seed_if_absent)
and bin/silver-launch.py, so rewiring the launcher to read the config store is a
non-breaking change: when the store has no launch_targets mapping, the hardcoded
defaults are used.
"""
from __future__ import annotations

import json
from typing import Optional

# The Fire TV media_player entities that were hardcoded as BOXES in
# bin/silver-launch.py (label -> entity_id).
DEFAULT_LAUNCH_TARGETS: dict[str, str] = {
    "bedroom": "media_player.fire_tv_192_168_0_233",
    "box8":    "media_player.fire_tv_192_168_0_8",
    "living":  "media_player.fire_tv_192_168_0_234",
}


def load_launch_targets(store_path: str = "config/integrations.json",
                        fallback: Optional[dict] = None) -> dict:
    """Return {label: entity_id} from the store's launch_targets mapping, falling
    back to `fallback` (the hardcoded defaults) when the store or mapping is absent."""
    fallback = dict(fallback or {})
    try:
        with open(store_path) as f:
            store = json.load(f)
    except (FileNotFoundError, ValueError):
        return fallback
    targets = (store.get("mappings") or {}).get("launch_targets") or []
    out: dict[str, str] = {}
    for t in targets:
        label, entity = t.get("label"), t.get("entity")
        if label and entity:
            out[label] = entity
    return out or fallback
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_launch_targets.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/stores/launch_targets.py tests/unit/test_launch_targets.py
git commit -m "feat(stores): add launch-target defaults + store-aware loader"
```

---

## Task 7: Migration seed (`config_store.seed_if_absent`)

**Files:**
- Modify: `backend/stores/config_store.py` (add `seed_if_absent`)
- Test: `tests/unit/test_config_store.py` (append)

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
# tests/unit/test_config_store.py  (append)
from backend.stores import launch_targets


def test_seed_writes_once_from_defaults(tmp_path):
    path = str(tmp_path / "config" / "integrations.json")
    seeded = config_store.seed_if_absent(path, env={"HA_URL": "http://ha.local:8123/"})
    assert seeded is True
    data = config_store.load(path)
    assert data["providers"]["homeassistant"]["kind"] == "homeassistant"
    assert data["providers"]["homeassistant"]["config"]["base_url"] == "http://ha.local:8123"
    labels = {t["label"]: t["entity"] for t in data["mappings"]["launch_targets"]}
    assert labels == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_seed_is_idempotent(tmp_path):
    path = str(tmp_path / "integrations.json")
    assert config_store.seed_if_absent(path, env={"HA_URL": "x"}) is True
    assert config_store.seed_if_absent(path, env={"HA_URL": "y"}) is False  # already there
    assert config_store.load(path)["providers"]["homeassistant"]["config"]["base_url"] == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_config_store.py -k seed -v`
Expected: FAIL — `AttributeError: module 'backend.stores.config_store' has no attribute 'seed_if_absent'`.

- [ ] **Step 3: Add `seed_if_absent` to `backend/stores/config_store.py`**

Add at the end of the file:

```python
def seed_if_absent(path: str = DEFAULT_PATH, env: Optional[dict] = None) -> bool:
    """One-time migration: if the store is absent, write an initial version from
    today's hardcoded values (HA base_url from env, the Fire-TV launch targets).
    Returns True if it seeded, False if the store already existed.

    pip / say_target are intentionally left unmapped — the operator maps them in
    the console (pip takes a camera or url source; see the plan's deferral note).
    Idempotent: never overwrites an existing store."""
    from backend.stores import launch_targets  # local import keeps load/save lean

    if os.path.exists(path):
        return False
    env = env if env is not None else os.environ
    base_url = (env.get("HA_URL") or "").rstrip("/")
    data = {
        "providers": {
            "homeassistant": {
                "kind": "homeassistant",
                "enabled": True,
                "config": {"base_url": base_url},
            }
        },
        "mappings": {
            "launch_targets": [
                {"provider": "homeassistant", "entity": entity, "label": label}
                for label, entity in launch_targets.DEFAULT_LAUNCH_TARGETS.items()
            ],
        },
    }
    save(data, path)
    return True
```

(`Optional` and `os` are already imported at the top of `config_store.py` from Task 2.)

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_config_store.py -v`
Expected: PASS (5 passed — 3 original + 2 seed).

- [ ] **Step 5: Commit**

```bash
git add backend/stores/config_store.py tests/unit/test_config_store.py
git commit -m "feat(stores): add one-time migration seed for the integrations store"
```

---

## Task 8: Provider registry (`build_provider`)

**Files:**
- Create: `backend/clients/providers/registry.py`
- Test: `tests/unit/test_ha_provider.py` (append)

The registry is the single seam the router and integration tests go through; tests monkeypatch `registry.build_provider`.

- [ ] **Step 1: Write the failing test (append)**

```python
# tests/unit/test_ha_provider.py  (append)
from pathlib import Path

from backend.stores import config_store, secrets_store
from backend.clients.providers import registry


def test_build_provider_constructs_ha_from_store_and_secret(tmp_path: Path):
    store_path = str(tmp_path / "integrations.json")
    secret_path = str(tmp_path / "secrets.json")
    config_store.save({
        "providers": {"homeassistant": {
            "kind": "homeassistant", "enabled": True,
            "config": {"base_url": "http://ha.local:8123"}}},
        "mappings": {},
    }, store_path)
    secrets_store.set_secret("homeassistant", "token", "tok", secret_path)

    p = registry.build_provider("homeassistant", store_path=store_path, secret_path=secret_path)
    assert isinstance(p, HomeAssistantProvider)


def test_build_provider_returns_none_for_unknown(tmp_path: Path):
    store_path = str(tmp_path / "integrations.json")
    config_store.save({"providers": {}, "mappings": {}}, store_path)
    assert registry.build_provider("ghost", store_path=store_path,
                                   secret_path=str(tmp_path / "s.json")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_ha_provider.py -k build_provider -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.clients.providers.registry'`.

- [ ] **Step 3: Write the registry**

```python
# backend/clients/providers/registry.py
"""Construct a live Provider for a given provider id from the config + secrets stores.

The single seam the API routes go through, so tests can monkeypatch build_provider
to return a FakeProvider without touching HTTP.
"""
from __future__ import annotations

import os
from typing import Optional

from backend.stores import config_store, secrets_store
from backend.clients.providers.base import Provider
from backend.clients.providers.homeassistant import HomeAssistantProvider


def build_provider(
    provider_id: str,
    store_path: str = config_store.DEFAULT_PATH,
    secret_path: str = secrets_store.DEFAULT_PATH,
) -> Optional[Provider]:
    store = config_store.load(store_path)
    pconf = (store.get("providers") or {}).get(provider_id)
    if not pconf or not pconf.get("enabled", True):
        return None
    if pconf.get("kind") == "homeassistant":
        base_url = (pconf.get("config") or {}).get("base_url") or os.environ.get("HA_URL", "")
        token = secrets_store.resolve_token(provider_id, secret_path) or ""
        return HomeAssistantProvider(base_url, token)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_ha_provider.py -k build_provider -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/clients/providers/registry.py tests/unit/test_ha_provider.py
git commit -m "feat(providers): add provider registry (build_provider from store)"
```

---

## Task 9: Integrations API router + mount + startup seed

**Files:**
- Create: `backend/api/integrations.py` (the `APIRouter`)
- Modify: `incarnation_server.py` (import imports near the top; `include_router`; startup seed after the `os.makedirs(...)` block at `incarnation_server.py:78`; `/console` is added in Task 11)
- Test: `tests/integration/test_integrations_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_integrations_endpoints.py
"""Integration tests for the /api/v1/integrations* routes.

Uses the project `incarnation_server` / `client` fixtures (which chdir to a tmp
dir) so config/secrets writes land under tmp_path, never the repo. The provider
seam is stubbed via registry.build_provider so no HTTP is needed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.clients.providers import registry
from backend.clients.providers.base import Item, CAP_PIP
from backend.clients.providers.fake import FakeProvider

pytestmark = pytest.mark.integration

AUTH = {"Authorization": "Bearer test-api-key-secret-1234"}
BASE = "/api/v1/integrations"


def test_set_config_persists_to_store(client, with_api_key, tmp_path):
    r = client.post(f"{BASE}/homeassistant/config",
                    json={"config": {"base_url": "http://ha.local:8123"}}, headers=AUTH)
    assert r.status_code == 200
    saved = json.loads((tmp_path / "config" / "integrations.json").read_text())
    assert saved["providers"]["homeassistant"]["config"]["base_url"] == "http://ha.local:8123"


def test_secret_endpoint_is_write_only(client, with_api_key, tmp_path):
    r = client.post(f"{BASE}/homeassistant/secret",
                    json={"key": "token", "value": "super-secret"}, headers=AUTH)
    assert r.status_code == 200
    assert "super-secret" not in r.text          # never echoed
    saved = json.loads((tmp_path / "config" / "secrets.json").read_text())
    assert saved["homeassistant"]["token"] == "super-secret"   # persisted server-side


def test_secret_requires_auth(client, with_api_key):
    r = client.post(f"{BASE}/homeassistant/secret", json={"key": "token", "value": "x"})
    assert r.status_code == 401


def test_put_and_get_mappings_roundtrip(client, with_api_key):
    mappings = {"launch_targets": [
        {"provider": "homeassistant", "entity": "media_player.tv", "label": "den"}]}
    r = client.put(f"{BASE}/homeassistant/mappings",
                   json={"mappings": mappings}, headers=AUTH)
    assert r.status_code == 200
    r2 = client.get(f"{BASE}/homeassistant/mappings", headers=AUTH)
    assert r2.json()["mappings"] == mappings


def test_scan_uses_provider_and_groups_by_domain(client, with_api_key, monkeypatch):
    fake = FakeProvider(items=[
        Item(id="camera.front", domain="camera", name="Front", capabilities=[CAP_PIP]),
        Item(id="script.greet", domain="script", name="Greet", capabilities=["scripts"]),
    ])
    monkeypatch.setattr(registry, "build_provider", lambda pid, **kw: fake)
    r = client.post(f"{BASE}/homeassistant/scan", headers=AUTH)
    assert r.status_code == 200
    grouped = r.json()["groups"]
    assert set(grouped) == {"camera", "script"}
    assert grouped["camera"][0]["id"] == "camera.front"


def test_invoke_delegates_to_provider(client, with_api_key, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(registry, "build_provider", lambda pid, **kw: fake)
    r = client.post(f"{BASE}/homeassistant/invoke",
                    json={"capability": "pip", "target": "camera.front"}, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert fake.invocations == [("pip", "camera.front", {})]


def test_health_reports_unknown_provider(client, with_api_key, monkeypatch):
    monkeypatch.setattr(registry, "build_provider", lambda pid, **kw: None)
    r = client.get(f"{BASE}/ghost/health", headers=AUTH)
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/integration/test_integrations_endpoints.py -v`
Expected: FAIL — routes 404 (router not mounted yet).

- [ ] **Step 3a: Write the router**

```python
# backend/api/integrations.py
"""Integrations console API — provider connect / configure / scan / map / invoke.

A self-contained APIRouter (no server-instance state) mounted by the app. All
routes sit behind require_api_key (router-level dependency). The HA token is
write-only: POSTed once, persisted, never returned.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import require_api_key
from backend.stores import config_store, secrets_store
from backend.clients.providers import registry

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["integrations"],
    dependencies=[Depends(require_api_key)],
)


class ConfigBody(BaseModel):
    config: dict = {}


class SecretBody(BaseModel):
    key: str
    value: str


class MappingsBody(BaseModel):
    mappings: dict = {}


class InvokeBody(BaseModel):
    capability: str
    target: str
    args: dict = {}


@router.get("")
async def list_integrations():
    store = config_store.load()
    providers = []
    for pid, pconf in (store.get("providers") or {}).items():
        providers.append({
            "id": pid,
            "kind": pconf.get("kind"),
            "enabled": pconf.get("enabled", True),
            "config": pconf.get("config", {}),  # never includes secrets
        })
    return {"providers": providers}


@router.post("/{provider_id}/config")
async def set_integration_config(provider_id: str, body: ConfigBody):
    store = config_store.load()
    prov = store.setdefault("providers", {}).setdefault(provider_id, {})
    prov.setdefault("kind", provider_id)
    prov.setdefault("enabled", True)
    prov["config"] = {**prov.get("config", {}), **body.config}
    config_store.save(store)
    return {"ok": True}


@router.post("/{provider_id}/secret")
async def set_integration_secret(provider_id: str, body: SecretBody):
    # Write-only: persist server-side, never echo the value back.
    secrets_store.set_secret(provider_id, body.key, body.value)
    return {"ok": True, "key": body.key}


@router.get("/{provider_id}/health")
async def integration_health(provider_id: str):
    provider = registry.build_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown or disabled provider")
    status = await asyncio.to_thread(provider.health)
    return {"ok": status.ok, "reason": status.reason}


@router.post("/{provider_id}/scan")
async def scan_integration(provider_id: str):
    provider = registry.build_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown or disabled provider")
    items = await asyncio.to_thread(provider.discover)
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it.domain, []).append({
            "id": it.id, "domain": it.domain, "name": it.name,
            "capabilities": it.capabilities,
        })
    return {"groups": groups}


@router.get("/{provider_id}/mappings")
async def get_integration_mappings(provider_id: str):
    store = config_store.load()
    return {"mappings": store.get("mappings", {})}


@router.put("/{provider_id}/mappings")
async def put_integration_mappings(provider_id: str, body: MappingsBody):
    store = config_store.load()
    store["mappings"] = body.mappings
    config_store.save(store)
    return {"ok": True}


@router.post("/{provider_id}/invoke")
async def invoke_integration(provider_id: str, body: InvokeBody):
    provider = registry.build_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown or disabled provider")
    return await asyncio.to_thread(provider.invoke, body.capability, body.target, body.args)
```

- [ ] **Step 3b: Mount the router + seed the store on startup**

In `incarnation_server.py`, add to the top-level imports (alongside the `from backend.api.deps import require_api_key` line added in Task 0):

```python
from backend.stores import config_store
from backend.api.integrations import router as integrations_router
```

In `IncarnationServer.__init__`, right after `os.makedirs("incarnation/public/vrma/animations", exist_ok=True)` (`incarnation_server.py:78`), add:

```python
        # One-time migration: seed the integrations store from today's hardcoded
        # values so the console has a starting point and the cutover is non-breaking.
        try:
            config_store.seed_if_absent()
        except Exception as e:  # never let a seed failure block server startup
            logger.warning("integrations store seed skipped: %s", e)
```

In `__init__`, immediately after the `self._setup_routes()` call (`incarnation_server.py:115`), mount the router:

```python
        self.app.include_router(integrations_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/integration/test_integrations_endpoints.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/api/integrations.py incarnation_server.py tests/integration/test_integrations_endpoints.py
git commit -m "feat(api): add /api/v1/integrations router + mount + startup seed"
```

---

## Task 10: Frontend — Vite MPA config + console logic modules

**Files:**
- Modify: `incarnation/package.json` (add React deps + plugin)
- Create: `incarnation/vite.config.js`
- Create: `incarnation/src/console/mappingsModel.js`
- Create: `incarnation/src/console/consoleApi.js`
- Test: `incarnation/src/console/mappingsModel.test.js`, `incarnation/src/console/consoleApi.test.js`

- [ ] **Step 1: Write the failing tests**

```js
// incarnation/src/console/mappingsModel.test.js
import { describe, it, expect } from 'vitest';
import {
  groupByDomain, setSingleMapping, setPipCameraSource, setPipUrlSource, isResolved,
} from './mappingsModel.js';

describe('mappingsModel', () => {
  it('groups discovered items by domain', () => {
    const items = [
      { id: 'camera.a', domain: 'camera', name: 'A', capabilities: ['pip'] },
      { id: 'script.b', domain: 'script', name: 'B', capabilities: ['scripts'] },
    ];
    const groups = groupByDomain(items);
    expect(Object.keys(groups).sort()).toEqual(['camera', 'script']);
    expect(groups.camera[0].id).toBe('camera.a');
  });

  it('sets a single-entity capability mapping (e.g. say_target) immutably', () => {
    const before = { mappings: {} };
    const after = setSingleMapping(before, 'say_target', 'homeassistant', 'media_player.tv');
    expect(after.mappings.say_target).toEqual({ provider: 'homeassistant', entity: 'media_player.tv' });
    expect(before.mappings.say_target).toBeUndefined();
  });

  it('sets a typed pip CAMERA source immutably', () => {
    const before = { mappings: {} };
    const after = setPipCameraSource(before, 'homeassistant', 'camera.a');
    expect(after.mappings.pip).toEqual({ kind: 'camera', provider: 'homeassistant', entity: 'camera.a' });
    expect(before.mappings.pip).toBeUndefined();
  });

  it('sets a typed pip URL source immutably', () => {
    const after = setPipUrlSource({ mappings: {} }, 'https://grafana.local/d/abc', 'dashboard');
    expect(after.mappings.pip).toEqual({ kind: 'url', url: 'https://grafana.local/d/abc', label: 'dashboard' });
  });

  it('resolves a camera-kind pip against discovered ids; url-kind never goes stale', () => {
    const cam = { kind: 'camera', provider: 'homeassistant', entity: 'camera.a' };
    expect(isResolved(cam, ['camera.a', 'camera.b'])).toBe(true);
    expect(isResolved(cam, ['camera.b'])).toBe(false);
    expect(isResolved({ kind: 'url', url: 'https://x' }, [])).toBe(true);
    expect(isResolved({ provider: 'homeassistant', entity: 'media_player.tv' }, ['media_player.tv'])).toBe(true);
  });
});
```

```js
// incarnation/src/console/consoleApi.test.js
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ConsoleApi } from './consoleApi.js';

describe('ConsoleApi', () => {
  beforeEach(() => { global.fetch = vi.fn(); });

  it('sends the bearer token and posts the secret write-only to /api/v1', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    const api = new ConsoleApi('the-key');
    await api.setSecret('homeassistant', 'token', 'shh');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/integrations/homeassistant/secret');
    expect(opts.method).toBe('POST');
    expect(opts.headers.Authorization).toBe('Bearer the-key');
    expect(JSON.parse(opts.body)).toEqual({ key: 'token', value: 'shh' });
  });

  it('scan returns the grouped payload', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ groups: { camera: [] } }) });
    const api = new ConsoleApi('k');
    const out = await api.scan('homeassistant');
    expect(out).toEqual({ groups: { camera: [] } });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test-js`
Expected: FAIL — cannot resolve `./mappingsModel.js` / `./consoleApi.js`.

- [ ] **Step 3a: Add React deps to `incarnation/package.json`**

Set the `dependencies` / `devDependencies` blocks to:

```json
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^7.3.1",
    "vitest": "^4.1.5"
  },
  "dependencies": {
    "@pixiv/three-vrm": "^3.4.5",
    "@pixiv/three-vrm-animation": "^3.4.5",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "three": "^0.182.0",
    "vrm-mixamo-retarget": "^1.0.3"
  }
```

Install into the JS test image's named volume:

```bash
docker compose -f docker-compose.test.yml run --rm --entrypoint /bin/sh js-tests -c "cd /app/incarnation && npm install"
```

- [ ] **Step 3b: Create the Vite MPA config**

```js
// incarnation/vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// Multi-page app: one entry per surface. Viewer/creator pages stay vanilla
// (perf-critical, Fire TV); the console is a React page. Without this explicit
// rollupOptions.input, `vite build` would only emit index.html.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        creator: resolve(__dirname, 'creator.html'),
        'design-preview': resolve(__dirname, 'design-preview.html'),
        console: resolve(__dirname, 'console.html'),
      },
    },
  },
});
```

- [ ] **Step 3c: Create the logic modules**

```js
// incarnation/src/console/mappingsModel.js
// Pure helpers for the console — framework-agnostic so they're unit-testable
// without React/jsdom (vitest include is src/**/*.test.js).

/** Group discovered items by their HA domain. */
export function groupByDomain(items) {
  const groups = {};
  for (const it of items) {
    (groups[it.domain] ??= []).push(it);
  }
  return groups;
}

/** Immutably set a single-entity capability (e.g. say_target). */
export function setSingleMapping(state, capability, provider, entity) {
  return {
    ...state,
    mappings: { ...state.mappings, [capability]: { provider, entity } },
  };
}

/** Immutably set the pip slot to a CAMERA source (a discovered HA entity). */
export function setPipCameraSource(state, provider, entity) {
  return {
    ...state,
    mappings: { ...state.mappings, pip: { kind: 'camera', provider, entity } },
  };
}

/** Immutably set the pip slot to a URL source (operator-entered website/doc link). */
export function setPipUrlSource(state, url, label) {
  return {
    ...state,
    mappings: { ...state.mappings, pip: { kind: 'url', url, label } },
  };
}

/** Resolution: a url-kind source never goes stale; everything else (camera-kind
 *  pip, or a plain single-entity mapping) is resolved iff its entity still exists. */
export function isResolved(mapping, discoveredIds) {
  if (!mapping) return false;
  if (mapping.kind === 'url') return !!mapping.url;
  return discoveredIds.includes(mapping.entity);
}
```

```js
// incarnation/src/console/consoleApi.js
// Thin fetch wrappers around the /api/v1/integrations* routes. All requests carry
// the API key; the secret POST is write-only (the value is never read back). This
// module is the console's slice of the frontend API client (the ICD's consumer side).

const BASE = '/api/v1/integrations';

export class ConsoleApi {
  constructor(apiKey, base = '') {
    this.apiKey = apiKey;
    this.base = base;
  }

  async _req(method, path, body) {
    const res = await fetch(`${this.base}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
    return res.json();
  }

  list() { return this._req('GET', BASE); }
  setConfig(id, config) { return this._req('POST', `${BASE}/${id}/config`, { config }); }
  setSecret(id, key, value) { return this._req('POST', `${BASE}/${id}/secret`, { key, value }); }
  health(id) { return this._req('GET', `${BASE}/${id}/health`); }
  scan(id) { return this._req('POST', `${BASE}/${id}/scan`); }
  getMappings(id) { return this._req('GET', `${BASE}/${id}/mappings`); }
  putMappings(id, mappings) { return this._req('PUT', `${BASE}/${id}/mappings`, { mappings }); }
  invoke(id, capability, target, args = {}) {
    return this._req('POST', `${BASE}/${id}/invoke`, { capability, target, args });
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test-js`
Expected: PASS (mappingsModel: 5, consoleApi: 2).

- [ ] **Step 5: Commit**

```bash
git add incarnation/package.json incarnation/package-lock.json incarnation/vite.config.js \
        incarnation/src/console/mappingsModel.js incarnation/src/console/mappingsModel.test.js \
        incarnation/src/console/consoleApi.js incarnation/src/console/consoleApi.test.js
git commit -m "feat(console): add Vite MPA config + console logic modules (React deps)"
```

---

## Task 11: Frontend — console page + React shell + backend `/console` route

**Files:**
- Create: `incarnation/console.html`
- Create: `incarnation/src/console/main.jsx`
- Create: `incarnation/src/console/App.jsx`
- Create: `incarnation/styles/console.css`
- Modify: `incarnation_server.py` (add the `/console` route inside the `if os.path.exists("incarnation/dist"):` block, beside the `/` route at `incarnation_server.py:101-104`)

No new automated test (frontend component tests are minimal for v1 — the logic is covered in Task 10; the JSX here is a thin view). Verification is a manual build + load (Step 4).

- [ ] **Step 1: Create the entry HTML**

```html
<!-- incarnation/console.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>playAIdes — Integrations Console</title>
    <link rel="stylesheet" href="/styles/tokens.css" />
    <link rel="stylesheet" href="/styles/console.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/console/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 2: Create the React mount + shell**

```jsx
// incarnation/src/console/main.jsx
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';

createRoot(document.getElementById('root')).render(<App />);
```

```jsx
// incarnation/src/console/App.jsx
import React, { useEffect, useState } from 'react';
import { ConsoleApi } from './consoleApi.js';
import { groupByDomain, setPipCameraSource, setPipUrlSource } from './mappingsModel.js';

// API key for local/dev use: pulled from the ?key= query param (kept out of source).
const API_KEY = new URLSearchParams(window.location.search).get('key') || '';
const PROVIDER = 'homeassistant';
const TABS = ['Connection', 'Discovered', 'Mappings'];

export function App() {
  const api = new ConsoleApi(API_KEY);
  const [tab, setTab] = useState('Connection');
  const [health, setHealth] = useState(null);
  const [groups, setGroups] = useState({});
  const [mappings, setMappings] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.health(PROVIDER).then(setHealth).catch(() => setHealth({ ok: false, reason: 'unreachable' }));
    api.getMappings(PROVIDER).then((r) => setMappings(r.mappings)).catch(() => {});
  }, []);

  async function savePip(nextState) {
    setMappings(nextState.mappings);
    await api.putMappings(PROVIDER, nextState.mappings);
  }

  async function onScan() {
    setBusy(true);
    try {
      const { groups } = await api.scan(PROVIDER);
      setGroups(groups);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="console">
      <aside className="console__sidebar">
        <h1 className="console__title">Integrations</h1>
        <button className="console__provider console__provider--active">Home Assistant</button>
      </aside>
      <main className="console__detail">
        <nav className="console__tabs">
          {TABS.map((t) => (
            <button
              key={t}
              className={`console__tab ${t === tab ? 'console__tab--active' : ''}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>

        {tab === 'Connection' && (
          <section className="console__panel">
            <p>Status: {health ? (health.ok ? 'connected ✓' : `offline — ${health.reason}`) : '…'}</p>
            <SecretForm api={api} onSaved={() => api.health(PROVIDER).then(setHealth)} />
          </section>
        )}

        {tab === 'Discovered' && (
          <section className="console__panel">
            <button onClick={onScan} disabled={busy}>{busy ? 'Scanning…' : 'Scan'}</button>
            {Object.entries(groupByDomain(Object.values(groups).flat())).map(([domain, items]) => (
              <div key={domain} className="console__group">
                <h3>{domain}</h3>
                <ul>{items.map((i) => <li key={i.id}>{i.name} <code>{i.id}</code></li>)}</ul>
              </div>
            ))}
          </section>
        )}

        {tab === 'Mappings' && (
          <section className="console__panel">
            <h3>PiP display source</h3>
            <p>
              Current: {mappings.pip
                ? (mappings.pip.kind === 'url'
                    ? `URL — ${mappings.pip.url}`
                    : `camera — ${mappings.pip.entity}`)
                : '(unset)'}
            </p>
            <PipSourceForm
              cameras={groups.camera || []}
              onPickCamera={(entity) => savePip(setPipCameraSource({ mappings }, PROVIDER, entity))}
              onPickUrl={(url, label) => savePip(setPipUrlSource({ mappings }, url, label))}
            />
            <p className="console__hint">
              say_target, launch_targets and scripts mappings follow the same pattern (single entity / lists).
            </p>
          </section>
        )}
      </main>
    </div>
  );
}

// PiP is a generic display slot: pick a discovered camera, OR enter a website/doc URL.
function PipSourceForm({ cameras, onPickCamera, onPickUrl }) {
  const [url, setUrl] = useState('');
  const [label, setLabel] = useState('');
  return (
    <div className="console__pip">
      <label>Camera source
        <select defaultValue="" onChange={(e) => e.target.value && onPickCamera(e.target.value)}>
          <option value="" disabled>Choose a discovered camera…</option>
          {cameras.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.id})</option>)}
        </select>
      </label>
      <form onSubmit={(e) => { e.preventDefault(); onPickUrl(url, label); setUrl(''); setLabel(''); }}>
        <label>URL source (website / document link)
          <input type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label>Label
          <input type="text" placeholder="dashboard" value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <button type="submit" disabled={!url}>Use this URL</button>
      </form>
    </div>
  );
}

function SecretForm({ api, onSaved }) {
  const [value, setValue] = useState('');
  return (
    <form
      className="console__secret"
      onSubmit={async (e) => {
        e.preventDefault();
        await api.setSecret(PROVIDER, 'token', value);
        setValue(''); // never keep the token in component state after save
        onSaved();
      }}
    >
      <label>HA token (write-only)
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <button type="submit" disabled={!value}>Save token</button>
    </form>
  );
}
```

- [ ] **Step 3: Create the stylesheet (uses the shared tokens)**

```css
/* incarnation/styles/console.css — master–detail console. Colors come from
   styles/tokens.css (the framework-agnostic theme layer). */
.console { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh;
  font-family: system-ui, sans-serif; color: var(--color-text, #e8e8e8);
  background: var(--color-bg, #14151a); }
.console__sidebar { border-right: 1px solid var(--color-border, #2a2c33); padding: 1rem; }
.console__title { font-size: 1rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--color-text-muted, #9aa0ab); }
.console__provider { display: block; width: 100%; text-align: left; padding: .5rem .75rem;
  margin-top: .5rem; border: 0; border-radius: 6px; cursor: pointer;
  background: transparent; color: inherit; }
.console__provider--active { background: var(--color-accent, #3b82f6); color: #fff; }
.console__detail { padding: 1.25rem 1.5rem; }
.console__tabs { display: flex; gap: .25rem; border-bottom: 1px solid var(--color-border, #2a2c33); }
.console__tab { padding: .5rem .9rem; border: 0; background: transparent; color: inherit;
  cursor: pointer; border-bottom: 2px solid transparent; }
.console__tab--active { border-bottom-color: var(--color-accent, #3b82f6); }
.console__panel { padding-top: 1rem; }
.console__group code, .console__panel code { color: var(--color-text-muted, #9aa0ab); }
.console__secret { display: flex; flex-direction: column; gap: .5rem; max-width: 360px; margin-top: 1rem; }
.console__secret input { width: 100%; padding: .4rem; }
.console__pip { display: flex; flex-direction: column; gap: 1rem; max-width: 420px; }
.console__pip label { display: flex; flex-direction: column; gap: .25rem; }
.console__pip select, .console__pip input { width: 100%; padding: .4rem; }
.console__hint { color: var(--color-text-muted, #9aa0ab); font-size: .85rem; margin-top: 1rem; }
```

- [ ] **Step 4: Add the backend route + build + manual verification**

In `incarnation_server.py`, inside the `if os.path.exists("incarnation/dist"):` block, right after the `@self.app.get("/")` / `serve_index` definition (`incarnation_server.py:104`), add:

```python
            @self.app.get("/console")
            async def serve_console():
                from fastapi.responses import FileResponse
                return FileResponse("incarnation/dist/console.html")
```

Build the MPA and confirm all four entries are emitted:

```bash
docker compose -f docker-compose.test.yml run --rm --entrypoint /bin/sh js-tests \
  -c "cd /app/incarnation && npm run build && ls dist/*.html"
```

Expected output includes: `dist/console.html  dist/creator.html  dist/design-preview.html  dist/index.html`
(confirms the MPA config built console **and** kept the existing pages — no regression).

- [ ] **Step 5: Commit**

```bash
git add incarnation/console.html incarnation/src/console/main.jsx incarnation/src/console/App.jsx \
        incarnation/styles/console.css incarnation_server.py
git commit -m "feat(console): add React console page + /console backend route"
```

---

## Task 12: Consume-refactor — `silver-launch.py` reads launch targets from the store

**Files:**
- Modify: `bin/silver-launch.py` (replace the module-level `BOXES` dict with store-aware resolution via `backend.stores.launch_targets`)
- Test: `tests/unit/test_silver_launch_targets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_silver_launch_targets.py
"""bin/silver-launch.py resolves its launch targets from the config store
(via backend.stores.launch_targets), falling back to the hardcoded defaults."""
import importlib.util
import os

from backend.stores import launch_targets

_SILVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "bin", "silver-launch.py")


def _load_silver_launch():
    spec = importlib.util.spec_from_file_location("silver_launch", _SILVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_silver_launch_exposes_fallback_defaults():
    mod = _load_silver_launch()
    assert mod._FALLBACK_BOXES == launch_targets.DEFAULT_LAUNCH_TARGETS


def test_silver_launch_resolves_targets_via_store(tmp_path):
    mod = _load_silver_launch()
    store = tmp_path / "integrations.json"
    store.write_text('{"mappings": {"launch_targets": '
                     '[{"entity": "media_player.x", "label": "den"}]}}')
    boxes = mod.resolve_boxes(store_path=str(store))
    assert boxes == {"den": "media_player.x"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test pytest tests/unit/test_silver_launch_targets.py -v`
Expected: FAIL — `AttributeError: module 'silver_launch' has no attribute '_FALLBACK_BOXES'` / `resolve_boxes`.

- [ ] **Step 3: Rewire `bin/silver-launch.py`**

Replace the `BOXES = {...}` block (`bin/silver-launch.py:35-39`) with:

```python
# Make the repo root importable so this script (run as bin/silver-launch.py,
# whose sys.path[0] is bin/) can import the shared backend.stores package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.stores import launch_targets  # noqa: E402

# Hardcoded fallback (the original BOXES) — used when the config store has no
# launch_targets mapping yet. Single source of truth lives in launch_targets.py.
_FALLBACK_BOXES = launch_targets.DEFAULT_LAUNCH_TARGETS


def resolve_boxes(store_path=None):
    """Resolve {label: entity} from the config store, falling back to the
    hardcoded defaults. Default store path is <repo>/config/integrations.json."""
    if store_path is None:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        store_path = os.path.join(repo, "config", "integrations.json")
    return launch_targets.load_launch_targets(store_path=store_path, fallback=_FALLBACK_BOXES)
```

Then in `main()`, compute the targets **before** building the parser, and use them for both the choices and the lookup. Replace the `ap.add_argument("box", …)` line and the `entity = BOXES[a.box]` lookup:

```python
    boxes = resolve_boxes()
    ap.add_argument("box", nargs="?", default="bedroom", choices=list(boxes),
                    help="which Fire TV (default: bedroom)")
```

and:

```python
    base, token = _creds()
    entity = boxes[a.box]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test pytest tests/unit/test_silver_launch_targets.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add bin/silver-launch.py tests/unit/test_silver_launch_targets.py
git commit -m "refactor(launch): silver-launch reads launch targets from the config store"
```

---

## Task 13: Gitignore the runtime config + full-suite gate

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the config files to `.gitignore`**

Append near the `.env` line:

```gitignore
# Backend-owned runtime config + secrets (written by the integrations console).
# Instance-specific; the secrets file holds the HA token — never commit either.
config/integrations.json
config/secrets.json
```

- [ ] **Step 2: Verify the files are ignored**

Run: `cd /home/bell/repo/ai_life/playAIdes && git check-ignore config/integrations.json config/secrets.json`
Expected: both paths echoed back (ignored).

- [ ] **Step 3: Run the full Python + JS suites (regression gate)**

Run: `bin/test` then `bin/test-js`
Expected: all Python tests pass (`-m "not live"`); all Vitest tests pass. No pre-existing test regressed (notably the Task 0 auth delegation and the new `backend.*` imports).

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore backend-owned runtime config + secrets"
```

---

## Deferred to a follow-up plan (flagged, not dropped)

This slice does the **`launch_targets`** consume-rewire (Task 12) because it's a genuinely isolated constant. The other two consume-rewirings from the console spec are **deliberately deferred** — they are not contained changes:

- **PiP-source rewire (incl. generic rendering)** — the camera entity flows dynamically through `skills/pip.py`, `skills/base.py`, `playAIdes.py`, and `data/control.html`. Rewiring those reads to consume `mappings.pip` — *and* extending the kiosk PiP overlay (`incarnation/src/pipOverlay.js`) to render a **url-kind** source (iframe) as well as a camera stream — touches the skill-dispatch path and the viewer. This slice delivers the **config model + console** for the generic PiP source; rendering the non-camera kinds is the follow-up.
- **Say-target rewire** — the "say-on-TV" target is the TTS playback `media_player`, next to the **TTS service being rebuilt in a concurrent session** ("stay clear of TTS"). Defer until that settles.

The migration seed (Task 7) provisions the store with the HA provider + launch targets, and the console lets the operator map `pip` (camera or URL) / `say_target` now — so the follow-up is purely additive (point existing reads at the store; teach the overlay to render a URL source) and non-breaking.

## Self-Review

**1. Spec coverage**

| Spec / architecture item | Task |
|---|---|
| `backend/` package scaffold + layer markers | 0 |
| `require_api_key` extracted to `backend/api/deps.py` (reusable, testable) | 0 |
| Generic provider seam (`health/discover/invoke`) + fake provider | 1 |
| Config store (atomic) + write-only secrets store + resolver | 2, 3 |
| HA `get_states`/`call_service`; HA provider discover/health/invoke | 4, 5 |
| Generic `pip` capability — typed source (camera / url) | 1 (key), 5 (camera caps), 10 (model), 11 (UI) |
| Launch-target defaults + store loader; migration seed | 6, 7 |
| Provider registry (build from store + token) | 8 |
| Console as an `APIRouter` under `/api/v1/integrations`, mounted; startup seed | 9 |
| Write-only secret endpoint (never echoed) | 9 (test asserts value absent) |
| Vite MPA config + React console (master–detail, shared tokens, `/api/v1` client) | 10, 11 |
| Contained consume-refactor (`silver-launch` → store) | 12 |
| PiP-source / say-target rewire | **Deferred** (flagged) |
| `config/*` gitignored; full-suite regression gate | 13 |
| TDD unit + integration + seam-contract coverage | 0–12 |
| Strangler-fig: new `backend/` alongside root modules; `ha_client.py` stays root | structure + 4, 5 |

**2. Architecture alignment**
- Layer rule honored: `backend/api/integrations.py` (router) → `backend/clients/providers` + `backend/stores`; the router holds **no** server-instance state (that's why it's a standalone `APIRouter`). `ha_client.py` stays at root and is imported by the HA provider — true strangler-fig.
- `/api/v1` prefix on the router; `{"detail": ...}` error shape (FastAPI default) on the 404s — matches the contract conventions.
- The `DisplayChannel` push port and the conversation/avatar services are **not** in this slice — they land in slice 2 (the conversation loop), per the architecture spec.

**3. Placeholder scan:** none — every code step contains complete content; no "TBD"/"add error handling"/"similar to Task N".

**4. Type consistency:** `Item{id, domain, name, capabilities}`, `Status{ok, reason}`, capability keys (`pip`/`say_target`/`launch_targets`/`scripts`), the typed pip source (`{kind:"camera", provider, entity}` / `{kind:"url", url, label}`), `build_provider(provider_id, store_path, secret_path)`, `load_launch_targets(store_path, fallback)`, and the router bodies (`ConfigBody`/`SecretBody`/`MappingsBody`/`InvokeBody`) are used identically across tasks. The `mappingsModel.js` helpers (`setPipCameraSource`/`setPipUrlSource`/`setSingleMapping`/`isResolved`) match between Task 10 (tests + module) and Task 11 (App.jsx imports). Imports use the `backend.*` namespace consistently; `ha_client` is the one intentional root import (re-homed in a later slice).
