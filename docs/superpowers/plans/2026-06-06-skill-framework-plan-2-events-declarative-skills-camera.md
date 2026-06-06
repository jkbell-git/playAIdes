# Persona Skill Framework — Plan 2: Events + Declarative Skills + Camera Resolution

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the deterministic skill+trigger framework — add `bash`/`http` declarative skill kinds loaded from disk, the `SkillProvider` interface (defined, not auto-loaded), inbound-event intake (`POST /api/event` + an event router that gates on the persona enable-list), and HA-camera-entity → `camera_proxy` URL resolution so a `show_pip` trigger can name a camera entity instead of a raw URL.

**Architecture:** Builds on Plan 1's `Skill`/`SkillRegistry`/`SkillContext`/`_dispatch_skill`. Declarative skills are `Skill` *instances* built from JSON pack specs (per-instance `name`/`Params`), so the registry treats them identically to internal skills. The event path mirrors the existing `on_message_callback` pattern: `POST /api/event` (uvicorn thread) hands off to a synchronous orchestrator method `handle_event` via `asyncio.to_thread` (so a blocking `bash`/`http` skill never stalls the WS loop); `handle_event` matches the active persona's event triggers with a pure matcher, **gates via `SkillRegistry.is_enabled`**, then dispatches. Camera resolution lives in `HAClient.camera_url` and reaches skills through a new `SkillContext.resolve_camera_url` door.

**Tech Stack:** Python 3.12 + Pydantic v2 (`model_validator`, `create_model`) + FastAPI/Starlette + httpx + `subprocess` (stdlib); `requests` (existing, in `ha_client`); pytest + FastAPI `TestClient` (backend tests). No new third-party dependencies.

**Spec:** [`../specs/2026-06-04-persona-skill-trigger-framework-design.md`](../specs/2026-06-04-persona-skill-trigger-framework-design.md). This plan covers spec §3.2 (`bash`/`http`/`provider` kinds), §3.3 (declarative + provider loading), §3.4 (`event` trigger), §3.5 (event path), §3.6 (`POST /api/event`), and the §3.10 "HA-entity → `camera_proxy`" item deferred from Plan 1. **Deferred to Plan 3:** `brain_model` load-on-activation, `captions` persona-mode. **Still deferred (spec §10):** external-pack *discovery*/auto-load (only the Protocol + a manual `register_provider` here), phrase slot-extraction, the agentic router, timer/cron triggers, pack sandboxing.

---

## Conventions (read once)

- All paths are under the git repo `/home/bell/repo/ai_life/playAIdes` (the parent `ai_life/` is **not** a repo). Run pytest and git from that root. Work on branch `feat/persona-skill-framework` (already current) or a worktree off it.
- **Skills are synchronous** (Plan 1 contract): `_dispatch_skill`, `SkillContext`, and `broadcast_to_persona` are sync; the latter schedules WS sends threadsafe internally. `bash`/`http` skills block their calling thread — that is fine on the chat thread (phrase path) and is kept off the WS loop on the event path via `asyncio.to_thread` (Task 9).
- **Declarative-pack directory is `skill_packs/`**, NOT the spec's bare `skills/` — `skills/` is already the Python package. JSON packs only in v1 (no YAML dependency); YAML is a trivial future add.
- **Gating contract (the carried-forward footgun):** `_dispatch_skill` checks *registration only*. The phrase matcher checks the enable-list inline (Plan 1). The **event path must gate via `SkillRegistry.is_enabled` before `_dispatch_skill`** — done in `handle_event` (Task 8), with a test proving a registered-but-not-enabled skill cannot fire from an event (Task 8).
- **Camera tokens rotate.** `HAClient.camera_url` resolves a fresh proxy URL on every call (HA rotates the entity `access_token`, notably on restart; stream tokens expire in minutes). Never cache resolved URLs.
- End every commit message with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

## File structure

**Create (backend):**
- `skills/declarative.py` — `build_params_model`, `BashSkill`, `HttpSkill`, `_interpolate_body`.
- `skills/provider.py` — `SkillProvider` Protocol.
- `skills/loader.py` — `load_skill_packs(directory)`.
- `skill_packs/` — directory for declarative JSON packs (created in Task 4; a demo pack lands in Task 10).

**Create (backend tests):**
- Unit: `tests/unit/test_bash_skill.py`, `tests/unit/test_http_skill.py`, `tests/unit/test_skill_provider.py`, `tests/unit/test_skill_loader.py`, `tests/unit/test_ha_camera_url.py`, `tests/unit/test_event_router.py`, `tests/unit/test_handle_event.py`.
- Integration: `tests/integration/test_event_endpoint.py` (FastAPI `TestClient` — the repo keeps server-route tests under `tests/integration/`, marked `@pytest.mark.integration`, with the uvicorn thread monkeypatched to a no-op; see Task 9).

**Modify (backend):**
- `skills/base.py` — add `resolve_camera` field + `resolve_camera_url` method to `SkillContext`.
- `skills/registry.py` — add `register_all` + `register_provider`.
- `skills/router.py` — add `match_event_trigger` + `_interpolate_params`.
- `skills/pip.py` — `ShowPipSkill`: `url` becomes optional, add `source` (camera entity) + resolution + a url-or-source validator.
- `ha_client.py` — add `HAClient.camera_url`.
- `playAIdes.py` — load packs in `__init__`; add `_resolve_camera_url`; wire `resolve_camera` into the `_dispatch_skill` context; add `handle_event`; pass `event_handler=self.handle_event` to the server.
- `incarnation_server.py` — `__init__` gains `event_handler=None`; add `POST /api/event`.
- `tests/unit/test_pip_skills.py` — extend for `source` resolution (Task 6).

**No frontend changes.** Plan 1's `PipOverlay` already renders both a snapshot (`<img src>`) and a live MJPEG stream from a `show_pip` `{url, kind}` message; camera resolution only changes *how the url is produced* (backend), not the message shape.

---
---

# PART A — Declarative skills, loader, provider interface (spec §3.2, §3.3)

## Task 1: `bash` skill kind — `BashSkill` + `build_params_model`

**Files:**
- Create: `skills/declarative.py`
- Test: `tests/unit/test_bash_skill.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_bash_skill.py
from skills.base import SkillContext
from skills.declarative import BashSkill, build_params_model


def _ctx():
    spoken = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda *a: None,
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    return ctx, spoken


def test_build_params_model_validates_types():
    M = build_params_model("demo", {"name": "str", "count": "int"})
    m = M(name="x", count="3")          # pydantic coerces "3" -> 3
    assert m.name == "x" and m.count == 3


def test_build_params_model_rejects_unknown_type():
    try:
        build_params_model("demo", {"bad": "datetime"})
        assert False, "expected ValueError on unknown type"
    except ValueError:
        pass


def test_bash_skill_runs_echo_and_returns_output():
    spec = {"name": "say_hi", "kind": "bash",
            "command": ["echo", "hi {who}"], "params": {"who": "str"}}
    skill = BashSkill(spec)
    assert skill.name == "say_hi" and skill.kind == "bash"
    ctx, spoken = _ctx()
    res = skill.execute(skill.Params(who="bell"), ctx)
    assert res.ok is True
    assert res.output == "hi bell"
    assert spoken == []                 # announce_output defaults False


def test_bash_skill_announces_output_when_configured():
    spec = {"name": "say", "kind": "bash", "command": ["echo", "done"],
            "params": {}, "announce_output": True}
    ctx, spoken = _ctx()
    BashSkill(spec).execute(BashSkill(spec).Params(), ctx)
    assert spoken == [("silver", "done")]


def test_bash_skill_no_shell_injection():
    # A param value that WOULD be dangerous in a shell is passed as one argv
    # element, never interpreted. `echo` prints it literally; nothing executes.
    spec = {"name": "danger", "kind": "bash",
            "command": ["echo", "{arg}"], "params": {"arg": "str"}}
    ctx, _ = _ctx()
    res = BashSkill(spec).execute(BashSkill(spec).Params(arg="; rm -rf /"), ctx)
    assert res.ok is True
    assert res.output == "; rm -rf /"   # literal — the `;` did nothing


def test_bash_skill_nonzero_exit_marks_failure():
    spec = {"name": "fail", "kind": "bash", "command": ["false"], "params": {}}
    ctx, _ = _ctx()
    res = BashSkill(spec).execute(BashSkill(spec).Params(), ctx)
    assert res.ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_bash_skill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.declarative'`.

- [ ] **Step 3: Implement `build_params_model` + `BashSkill`**

```python
# skills/declarative.py
"""Declarative skill kinds — bash (argv) and http (request), built from pack
specs (spec §3.2). These are Skill *instances* whose `name` and `Params` come
from the spec at load time, so the registry treats them like internal skills.

Security: bash runs an argv array with shell=False — params are substituted as
discrete argv elements, never concatenated into a shell, so no user value can
reach a shell. http percent-encodes url values and JSON-encodes body values.
"""
from __future__ import annotations

import logging
import subprocess
import urllib.parse
from typing import Any

import httpx
from pydantic import BaseModel, create_model

from skills.base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

_TYPE_MAP = {"str": str, "int": int, "float": float, "bool": bool}


def build_params_model(skill_name: str, params_spec: dict) -> type[BaseModel]:
    """Build a Pydantic model from a {param_name: type_string} spec. All declared
    params are required. Unknown type strings fail-fast (raise ValueError)."""
    fields: dict[str, tuple] = {}
    for pname, type_str in (params_spec or {}).items():
        if type_str not in _TYPE_MAP:
            raise ValueError(
                f"skill {skill_name!r}: param {pname!r} has unknown type {type_str!r} "
                f"(allowed: {sorted(_TYPE_MAP)})"
            )
        fields[pname] = (_TYPE_MAP[type_str], ...)
    return create_model(f"{skill_name}_Params", **fields)


class BashSkill(Skill):
    # Class-level placeholders satisfy Skill.__init_subclass__ (which requires a
    # str `name` and a `Params` attr at subclass-definition time). The real
    # per-instance name/Params are set in __init__ from the pack spec.
    name = "bash"
    kind = "bash"
    Params = BaseModel

    def __init__(self, spec: dict) -> None:
        self.name = spec["name"]
        self.kind = "bash"
        self.command: list[str] = list(spec["command"])
        if not self.command:
            raise ValueError(f"bash skill {self.name!r}: 'command' must be a non-empty argv list")
        self.timeout_s: float = float(spec.get("timeout_s", 10))
        self.announce_output: bool = bool(spec.get("announce_output", False))
        self.Params = build_params_model(self.name, spec.get("params", {}))

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        values = params.model_dump()
        try:
            # Per-element .format on the argv template; values are inserted as
            # whole, discrete argv elements (shell=False below) — no injection.
            argv = [part.format(**values) for part in self.command]
        except (KeyError, IndexError) as e:
            logger.warning("bash skill %r: template references unknown param: %s", self.name, e)
            return SkillResult(ok=False, error=f"bad template: {e}")
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True,
                timeout=self.timeout_s, shell=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("bash skill %r timed out after %ss", self.name, self.timeout_s)
            return SkillResult(ok=False, error="timeout")
        except Exception as e:
            logger.exception("bash skill %r failed to run", self.name)
            return SkillResult(ok=False, error=str(e))
        out = (proc.stdout or "").strip()
        if self.announce_output and out:
            ctx.speak(out)
        return SkillResult(
            ok=(proc.returncode == 0),
            output=out or None,
            error=((proc.stderr or "").strip() or None) if proc.returncode else None,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_bash_skill.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/declarative.py tests/unit/test_bash_skill.py
git commit -m "feat(skills): add bash declarative skill kind (argv, no shell)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `http` skill kind — `HttpSkill` + `_interpolate_body`

**Files:**
- Modify: `skills/declarative.py` (append `HttpSkill` + `_interpolate_body`)
- Test: `tests/unit/test_http_skill.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_http_skill.py
import httpx
import pytest

from skills.base import SkillContext
from skills.declarative import HttpSkill, _interpolate_body


def _ctx():
    spoken = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda *a: None,
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    return ctx, spoken


def test_interpolate_body_whole_token_keeps_type():
    body = {"brightness": "{level}", "name": "fixed", "nested": {"id": "{eid}"}}
    out = _interpolate_body(body, {"level": 80, "eid": "light.x"})
    assert out == {"brightness": 80, "name": "fixed", "nested": {"id": "light.x"}}


def test_http_skill_get_interpolates_and_encodes_url(monkeypatch):
    captured = {}

    def fake_request(self, method, url, headers=None, json=None):
        captured["method"], captured["url"] = method, url
        return httpx.Response(200, text="OK")

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    spec = {"name": "weather", "kind": "http", "method": "GET",
            "url": "https://api.test/q?city={city}", "params": {"city": "str"}}
    ctx, spoken = _ctx()
    res = HttpSkill(spec).execute(HttpSkill(spec).Params(city="São Paulo"), ctx)
    assert res.ok is True and res.output == "OK"
    assert captured["method"] == "GET"
    # Space + non-ASCII percent-encoded, never raw-concatenated.
    assert captured["url"] == "https://api.test/q?city=S%C3%A3o%20Paulo"
    assert spoken == []


def test_http_skill_announces_response_when_configured(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request",
                        lambda self, m, u, headers=None, json=None: httpx.Response(200, text="72F"))
    spec = {"name": "temp", "kind": "http", "url": "https://api.test/t",
            "params": {}, "announce_output": True}
    ctx, spoken = _ctx()
    HttpSkill(spec).execute(HttpSkill(spec).Params(), ctx)
    assert spoken == [("silver", "72F")]


def test_http_skill_non_2xx_marks_failure(monkeypatch):
    monkeypatch.setattr(httpx.Client, "request",
                        lambda self, m, u, headers=None, json=None: httpx.Response(500, text="boom"))
    spec = {"name": "x", "kind": "http", "url": "https://api.test/x", "params": {}}
    ctx, _ = _ctx()
    res = HttpSkill(spec).execute(HttpSkill(spec).Params(), ctx)
    assert res.ok is False and res.error == "http_500"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_http_skill.py -v`
Expected: FAIL — `ImportError: cannot import name 'HttpSkill' from 'skills.declarative'`.

- [ ] **Step 3: Append `HttpSkill` + `_interpolate_body` to `skills/declarative.py`**

```python
def _interpolate_body(template: Any, values: dict) -> Any:
    """Deep-substitute into a JSON body template. A string of the exact form
    '{pname}' becomes the raw (typed) value so ints/bools survive JSON encoding;
    other strings go through str.format; dicts/lists recurse. httpx JSON-encodes
    the result, so no manual escaping is needed."""
    if isinstance(template, str):
        if template.startswith("{") and template.endswith("}") and template[1:-1] in values:
            return values[template[1:-1]]
        try:
            return template.format(**values)
        except (KeyError, IndexError):
            return template
    if isinstance(template, dict):
        return {k: _interpolate_body(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [_interpolate_body(v, values) for v in template]
    return template


class HttpSkill(Skill):
    name = "http"          # class-level placeholder (see BashSkill note)
    kind = "http"
    Params = BaseModel

    def __init__(self, spec: dict) -> None:
        self.name = spec["name"]
        self.kind = "http"
        self.method: str = str(spec.get("method", "GET")).upper()
        self.url: str = spec["url"]
        self.headers: dict = dict(spec.get("headers", {}) or {})
        self.body: Any = spec.get("body")          # dict/list template or None
        self.timeout_s: float = float(spec.get("timeout_s", 10))
        self.announce_output: bool = bool(spec.get("announce_output", False))
        self.Params = build_params_model(self.name, spec.get("params", {}))

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        values = params.model_dump()
        try:
            # URL values percent-encoded before interpolation (no raw concat).
            enc = {k: urllib.parse.quote(str(v), safe="") for k, v in values.items()}
            url = self.url.format(**enc)
            headers = {k: str(v).format(**values) for k, v in self.headers.items()}
        except (KeyError, IndexError) as e:
            logger.warning("http skill %r: template references unknown param: %s", self.name, e)
            return SkillResult(ok=False, error=f"bad template: {e}")
        json_body = _interpolate_body(self.body, values) if self.body is not None else None
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.request(self.method, url, headers=headers, json=json_body)
        except Exception as e:
            logger.warning("http skill %r request failed: %s", self.name, e)
            return SkillResult(ok=False, error=str(e))
        out = (resp.text or "")[:500] or None
        if self.announce_output and out:
            ctx.speak(out)
        return SkillResult(
            ok=resp.is_success,
            output=out,
            error=None if resp.is_success else f"http_{resp.status_code}",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_http_skill.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/declarative.py tests/unit/test_http_skill.py
git commit -m "feat(skills): add http declarative skill kind (safe interpolation)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `SkillProvider` Protocol + registry `register_all`/`register_provider`

**Files:**
- Create: `skills/provider.py`
- Modify: `skills/registry.py` (add two methods after `register`)
- Test: `tests/unit/test_skill_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_skill_provider.py
from pydantic import BaseModel

from skills.base import Skill, SkillResult
from skills.provider import SkillProvider
from skills.registry import SkillRegistry


class _Fake(Skill):
    name = "p_skill"
    class Params(BaseModel):
        pass
    def execute(self, params, ctx):
        return SkillResult()


class _Provider:
    def skills(self):
        return [_Fake()]


def test_provider_satisfies_protocol():
    assert isinstance(_Provider(), SkillProvider)   # runtime_checkable structural check


def test_register_provider_registers_each_skill():
    reg = SkillRegistry()
    reg.register_provider(_Provider())
    assert reg.get("p_skill").name == "p_skill"


def test_register_all_registers_iterable():
    reg = SkillRegistry()
    reg.register_all([_Fake()])
    assert reg.get("p_skill") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.provider'`.

- [ ] **Step 3: Create `skills/provider.py` and extend the registry**

```python
# skills/provider.py
"""External-pack contribution point (spec §3.2). A SkillProvider supplies a list
of Skills via skills(). v1 defines the Protocol and lets the registry accept
provider-sourced skills (SkillRegistry.register_provider); automatic discovery /
loading of providers is deferred (spec §10)."""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from skills.base import Skill


@runtime_checkable
class SkillProvider(Protocol):
    def skills(self) -> List[Skill]: ...
```

In `skills/registry.py`, add these two methods to `SkillRegistry` (after `register`):

```python
    def register_all(self, skills) -> None:
        """Register every skill in an iterable (fail-fast on duplicates)."""
        for skill in skills:
            self.register(skill)

    def register_provider(self, provider) -> None:
        """Register every skill a SkillProvider supplies (spec §3.3 step 3)."""
        self.register_all(provider.skills())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_provider.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/provider.py skills/registry.py tests/unit/test_skill_provider.py
git commit -m "feat(skills): define SkillProvider protocol + registry register_all/provider

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Pack loader `load_skill_packs` + wire into `PlayAIdes.__init__`

**Files:**
- Create: `skills/loader.py`
- Modify: `playAIdes.py` (`__init__`, after the internal-skill registration at `playAIdes.py:130-132`)
- Test: `tests/unit/test_skill_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_skill_loader.py
import json

import pytest

from skills.loader import load_skill_packs


def _write_pack(tmp_path, fname, obj):
    p = tmp_path / fname
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


def test_missing_directory_returns_empty(tmp_path):
    assert load_skill_packs(str(tmp_path / "nope")) == []


def test_loads_bash_and_http_skills(tmp_path):
    _write_pack(tmp_path, "pack.json", {"skills": [
        {"name": "a", "kind": "bash", "command": ["echo", "hi"], "params": {}},
        {"name": "b", "kind": "http", "url": "https://x/y", "params": {}},
    ]})
    skills = load_skill_packs(str(tmp_path))
    by_name = {s.name: s for s in skills}
    assert set(by_name) == {"a", "b"}
    assert by_name["a"].kind == "bash" and by_name["b"].kind == "http"


def test_unknown_kind_fails_fast(tmp_path):
    _write_pack(tmp_path, "bad.json", {"skills": [{"name": "x", "kind": "telepathy"}]})
    with pytest.raises(ValueError, match="unknown kind"):
        load_skill_packs(str(tmp_path))


def test_missing_name_fails_fast(tmp_path):
    _write_pack(tmp_path, "bad.json", {"skills": [{"kind": "bash", "command": ["echo"]}]})
    with pytest.raises(ValueError, match="missing 'name'"):
        load_skill_packs(str(tmp_path))


def test_duplicate_name_across_packs_fails_fast(tmp_path):
    _write_pack(tmp_path, "a.json", {"skills": [{"name": "dup", "kind": "bash", "command": ["echo"]}]})
    _write_pack(tmp_path, "b.json", {"skills": [{"name": "dup", "kind": "bash", "command": ["echo"]}]})
    with pytest.raises(ValueError, match="duplicate"):
        load_skill_packs(str(tmp_path))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.loader'`.

- [ ] **Step 3: Implement the loader**

```python
# skills/loader.py
"""Load declarative (bash/http) skills from JSON packs in a global directory
(spec §3.3 step 2). Each pack file is {"skills": [ {name, kind, ...}, ... ]}.
Fail-fast (raise) on unknown kind, missing name, malformed JSON, or a duplicate
name across packs — registry/load errors must surface at startup (spec §6)."""
from __future__ import annotations

import json
import logging
import os
from typing import List

from skills.base import Skill
from skills.declarative import BashSkill, HttpSkill

logger = logging.getLogger(__name__)

_KINDS = {"bash": BashSkill, "http": HttpSkill}


def load_skill_packs(directory: str) -> List[Skill]:
    skills: List[Skill] = []
    seen: set[str] = set()
    if not os.path.isdir(directory):
        logger.info("skill pack dir %r not present; no declarative skills loaded.", directory)
        return skills
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(directory, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)                         # JSONDecodeError → fail-fast
        for spec in data.get("skills", []):
            name = spec.get("name")
            kind = spec.get("kind")
            if not name:
                raise ValueError(f"{path}: a skill spec is missing 'name'")
            if kind not in _KINDS:
                raise ValueError(
                    f"{path}: skill {name!r} has unknown kind {kind!r} "
                    f"(allowed: {sorted(_KINDS)})"
                )
            if name in seen:
                raise ValueError(f"duplicate declarative skill name {name!r} (in {path})")
            seen.add(name)
            skills.append(_KINDS[kind](spec))           # spec-validation errors fail-fast too
    logger.info("Loaded %d declarative skill(s) from %s", len(skills), directory)
    return skills
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_loader.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Wire pack loading into `PlayAIdes.__init__`**

In `playAIdes.py`, immediately after the internal-skill registration block (`playAIdes.py:130-132`, the three `self.skill_registry...` lines), add:

```python
        from skills.loader import load_skill_packs
        # Declarative (bash/http) skills from the global pack dir. Fail-fast:
        # a malformed pack should crash startup with a clear message (spec §6).
        self.skill_registry.register_all(load_skill_packs("skill_packs"))
```

- [ ] **Step 6: Verify the suite still imports/loads cleanly**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -c "import playAIdes" && python -m pytest tests/unit/test_skill_loader.py -v`
Expected: import succeeds (no `skill_packs/` dir yet → loader logs and returns `[]`); loader tests still PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/loader.py playAIdes.py tests/unit/test_skill_loader.py
git commit -m "feat(skills): load declarative packs from skill_packs/ at startup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---
---

# PART B — HA camera-entity → camera_proxy resolution (spec §3.10 Plan-2 item)

## Task 5: `HAClient.camera_url`

**Files:**
- Modify: `ha_client.py` (add a method to `HAClient`, after `converse`)
- Test: `tests/unit/test_ha_camera_url.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ha_camera_url.py
from unittest.mock import patch

from ha_client import HAClient


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
    def json(self):
        return self._payload


def _client():
    return HAClient("http://ha.local:8123/", "tok")


def test_snapshot_url_built_from_access_token():
    payload = {"attributes": {"access_token": "ABC", "entity_picture": "/api/camera_proxy/camera.fd?token=ABC"}}
    with patch("ha_client.requests.get", return_value=_Resp(200, payload)):
        url = _client().camera_url("camera.fd", stream=False)
    assert url == "http://ha.local:8123/api/camera_proxy/camera.fd?token=ABC"


def test_stream_url_uses_stream_segment():
    payload = {"attributes": {"access_token": "ABC"}}
    with patch("ha_client.requests.get", return_value=_Resp(200, payload)):
        url = _client().camera_url("camera.fd", stream=True)
    assert url == "http://ha.local:8123/api/camera_proxy_stream/camera.fd?token=ABC"


def test_falls_back_to_entity_picture_for_snapshot():
    payload = {"attributes": {"entity_picture": "/api/camera_proxy/camera.fd?token=XYZ"}}
    with patch("ha_client.requests.get", return_value=_Resp(200, payload)):
        url = _client().camera_url("camera.fd", stream=False)
    assert url == "http://ha.local:8123/api/camera_proxy/camera.fd?token=XYZ"


def test_returns_none_on_non_200():
    with patch("ha_client.requests.get", return_value=_Resp(404, {})):
        assert _client().camera_url("camera.fd") is None


def test_returns_none_on_no_token_no_picture():
    with patch("ha_client.requests.get", return_value=_Resp(200, {"attributes": {}})):
        assert _client().camera_url("camera.fd") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_ha_camera_url.py -v`
Expected: FAIL — `AttributeError: 'HAClient' object has no attribute 'camera_url'`.

- [ ] **Step 3: Add `camera_url` to `HAClient`**

In `ha_client.py`, add this method to `HAClient` (after `converse`, before `health_check`):

```python
    def camera_url(self, entity_id: str, stream: bool = False) -> Optional[str]:
        """Resolve an HA camera entity to a browser-loadable proxy URL.

        Reads the entity's rotating ``access_token`` from GET /api/states/<id>
        and builds {base}/api/camera_proxy[_stream]/<id>?token=<token>. A browser
        <img> cannot send an Authorization header, so the signed ?token= query
        param is the only way the frontend can load the feed directly. Resolve
        FRESH per use — HA rotates the token (notably on restart) and stream
        tokens expire within minutes; never cache the returned URL. Returns None
        on any error (unreachable, non-200, no token)."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/states/{entity_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout, ConnectionError) as e:
            logger.warning("HA states unreachable for %s: %s", entity_id, e)
            return None
        if resp.status_code != 200:
            logger.warning("HA states returned %s for %s", resp.status_code, entity_id)
            return None
        try:
            attrs = (resp.json() or {}).get("attributes", {}) or {}
        except ValueError:
            logger.warning("HA states returned non-JSON for %s", entity_id)
            return None
        token = attrs.get("access_token")
        if token:
            seg = "camera_proxy_stream" if stream else "camera_proxy"
            return f"{self.base_url}/api/{seg}/{entity_id}?token={token}"
        # Fallback: entity_picture is the still-image proxy path (no stream form).
        ep = attrs.get("entity_picture")
        if ep and not stream:
            return f"{self.base_url}{ep}"
        logger.warning("Camera %s exposes no access_token/entity_picture", entity_id)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_ha_camera_url.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add ha_client.py tests/unit/test_ha_camera_url.py
git commit -m "feat(ha): resolve camera entity to camera_proxy URL (fresh token)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `SkillContext.resolve_camera` + `ShowPipSkill` `source` + orchestrator backing

**Files:**
- Modify: `skills/base.py` (`SkillContext` — add field + method)
- Modify: `skills/pip.py` (`ShowPipSkill` — `url` optional, add `source`, resolve, validator)
- Modify: `playAIdes.py` (add `_resolve_camera_url`; pass `resolve_camera` into the `_dispatch_skill` context at `playAIdes.py:797-802`)
- Test: extend `tests/unit/test_pip_skills.py`

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
# append to tests/unit/test_pip_skills.py
import pytest
from pydantic import ValidationError


def _ctx_with_camera(resolved):
    sent, spoken = [], []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda pid, t, p: sent.append((pid, t, p)),
        speak_fn=lambda pid, text: spoken.append((pid, text)),
        resolve_camera=lambda entity_id, live: resolved,
    )
    return ctx, sent, spoken


def test_show_pip_resolves_camera_source_to_url():
    ctx, sent, _ = _ctx_with_camera("http://ha/api/camera_proxy_stream/camera.fd?token=T")
    ShowPipSkill().execute(ShowPipSkill().Params(source="camera.fd", kind="live"), ctx)
    assert sent[0][1] == "show_pip"
    assert sent[0][2]["url"] == "http://ha/api/camera_proxy_stream/camera.fd?token=T"
    assert sent[0][2]["kind"] == "live"


def test_show_pip_unresolved_source_is_failure_no_send():
    ctx, sent, _ = _ctx_with_camera(None)        # resolution returned None
    res = ShowPipSkill().execute(ShowPipSkill().Params(source="camera.fd"), ctx)
    assert res.ok is False
    assert sent == []                            # nothing shown


def test_show_pip_requires_url_or_source():
    with pytest.raises(ValidationError):
        ShowPipSkill().Params()                  # neither url nor source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_pip_skills.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'resolve_camera'` (and the validator test errors because `url` is currently required, not optional).

- [ ] **Step 3a: Extend `SkillContext` in `skills/base.py`**

Add a field to the `@dataclass SkillContext` (after `speak_fn`, so it stays last with its default) and a method:

```python
    resolve_camera: Optional[Callable[[str, bool], Optional[str]]] = None  # (entity_id, live) -> url | None
```

```python
    def resolve_camera_url(self, entity_id: str, live: bool = False) -> Optional[str]:
        """Resolve an HA camera entity to a proxy URL, or None if HA is not
        configured / unavailable. The skill's only door to camera resolution."""
        if self.resolve_camera is None:
            return None
        return self.resolve_camera(entity_id, live)
```

- [ ] **Step 3b: Update `ShowPipSkill` in `skills/pip.py`**

Replace the file's imports + `ShowPipSkill` with:

```python
"""Internal (hard-typed) PiP skills (spec §3.10). A trigger supplies either a
direct `url` or an HA camera `source` (entity_id) that is resolved to a fresh
camera_proxy URL via the SkillContext (Plan 2)."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel, model_validator

from skills.base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class ShowPipSkill(Skill):
    name = "show_pip"
    kind = "internal"

    class Params(BaseModel):
        url: Optional[str] = None
        source: Optional[str] = None          # HA camera entity_id (resolved at dispatch)
        kind: Literal["live", "snapshot"] = "snapshot"
        dismiss: dict = {"type": "until_dismissed"}
        announce: Optional[str] = None

        @model_validator(mode="after")
        def require_url_or_source(self) -> "ShowPipSkill.Params":
            if not self.url and not self.source:
                raise ValueError("show_pip requires either 'url' or 'source' (camera entity)")
            return self

    def execute(self, params: "ShowPipSkill.Params", ctx: SkillContext) -> SkillResult:
        url = params.url
        if not url and params.source:
            url = ctx.resolve_camera_url(params.source, live=(params.kind == "live"))
        if not url:
            logger.warning("show_pip: could not resolve a url (source=%r)", params.source)
            return SkillResult(ok=False, error="unresolved camera source")
        ctx.send_display("show_pip", {
            "url": url,
            "kind": params.kind,
            "dismiss": params.dismiss,
        })
        if params.announce:
            ctx.speak(params.announce)
        return SkillResult()
```

(Leave `DismissPipSkill` unchanged.)

- [ ] **Step 3c: Add `_resolve_camera_url` and wire it into the dispatch context in `playAIdes.py`**

Add this method to the `PlayAIdes` class (e.g. just above `_dispatch_skill` at `playAIdes.py:777`):

```python
    def _resolve_camera_url(self, entity_id: str, live: bool = False) -> Optional[str]:
        """SkillContext.resolve_camera backing — HA camera entity → fresh proxy
        URL. None when HA isn't configured."""
        if not self.ha_client:
            return None
        return self.ha_client.camera_url(entity_id, stream=live)
```

Then in `_dispatch_skill`, extend the `SkillContext(...)` construction (`playAIdes.py:797-802`) to pass the resolver:

```python
        ctx = SkillContext(
            persona=self.current_persona,
            target_id=target_id,
            send=self._skill_send,
            speak_fn=self.speak_as_persona,
            resolve_camera=self._resolve_camera_url,
        )
```

- [ ] **Step 4: Run tests to verify they pass (and nothing regressed)**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_pip_skills.py tests/unit/test_skill_base.py tests/unit/test_chat_skill_dispatch.py -v`
Expected: PASS — the new source tests, plus the Plan-1 PiP/base/dispatch tests still green (url-only path unchanged; `Params()` with neither url nor source still fails validation, so `test_dispatch_bad_params_is_noop` still holds).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/base.py skills/pip.py playAIdes.py tests/unit/test_pip_skills.py
git commit -m "feat(skills): show_pip resolves HA camera 'source' via ctx.resolve_camera_url

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---
---

# PART C — Inbound events: router, handler, endpoint (spec §3.4 event, §3.5 event path, §3.6)

## Task 7: Pure event matcher — `match_event_trigger` + `_interpolate_params`

**Files:**
- Modify: `skills/router.py` (append)
- Test: `tests/unit/test_event_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_event_router.py
from persona import Trigger
from skills.router import match_event_trigger, _interpolate_params


def _et(event, skill, match=None, params=None):
    on = {"event": event}
    if match is not None:
        on["match"] = match
    return Trigger(on=on, do={"skill": skill, "params": params or {}})


def test_matches_event_by_name():
    triggers = [_et("front_door_motion", "show_pip", params={"source": "camera.fd"})]
    out = match_event_trigger("front_door_motion", {}, triggers)
    assert out == ("show_pip", {"source": "camera.fd"})


def test_match_conditions_must_all_hold():
    triggers = [_et("motion", "show_pip", match={"state": "on"}, params={"x": 1})]
    assert match_event_trigger("motion", {"state": "off"}, triggers) is None
    assert match_event_trigger("motion", {"state": "on"}, triggers) == ("show_pip", {"x": 1})


def test_payload_interpolation_preserves_type():
    triggers = [_et("ev", "show_pip", params={"source": "{payload.entity_id}", "n": "{payload.count}"})]
    out = match_event_trigger("ev", {"entity_id": "camera.fd", "count": 3}, triggers)
    assert out == ("show_pip", {"source": "camera.fd", "n": 3})


def test_phrase_triggers_ignored_by_event_matcher():
    triggers = [Trigger(on={"phrase": "show the door"}, do={"skill": "show_pip", "params": {"url": "u"}})]
    assert match_event_trigger("show the door", {}, triggers) is None


def test_first_match_wins():
    triggers = [_et("ev", "first"), _et("ev", "second")]
    assert match_event_trigger("ev", {}, triggers)[0] == "first"


def test_interpolate_params_unmatched_field_becomes_none():
    assert _interpolate_params({"a": "{payload.missing}"}, {}) == {"a": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_event_router.py -v`
Expected: FAIL — `ImportError: cannot import name 'match_event_trigger' from 'skills.router'`.

- [ ] **Step 3: Append the event matcher to `skills/router.py`**

```python
def _interpolate_params(params: dict, payload: dict) -> dict:
    """Replace a param value of the exact form '{payload.<field>}' with the raw
    (typed) value from the event payload; missing fields resolve to None. Other
    values pass through unchanged. (Partial/templated interpolation is deferred.)"""
    out: dict = {}
    for k, v in (params or {}).items():
        if isinstance(v, str) and v.startswith("{payload.") and v.endswith("}"):
            out[k] = (payload or {}).get(v[len("{payload."):-1])
        else:
            out[k] = v
    return out


def match_event_trigger(
    name: str,
    payload: dict,
    triggers: Iterable[Trigger],
) -> Optional[tuple[str, dict]]:
    """First event-trigger whose `on.event` equals `name` and whose `on.match`
    (shallow equality vs payload) holds wins. Returns (skill_name, interpolated
    params) or None.

    Enablement is NOT checked here — by design. The caller MUST gate via
    SkillRegistry.is_enabled before dispatch (spec §3.5): the phrase matcher
    gates inline, but _dispatch_skill checks only *registration*, so the event
    path's enable-gate lives in PlayAIdes.handle_event (Task 8)."""
    payload = payload or {}
    for trig in triggers:
        if not trig.on.event or trig.on.event != name:
            continue
        match = trig.on.match or {}
        if all(payload.get(k) == v for k, v in match.items()):
            return (trig.do.skill, _interpolate_params(dict(trig.do.params), payload))
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_event_router.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/router.py tests/unit/test_event_router.py
git commit -m "feat(skills): add pure event-trigger matcher with payload interpolation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Orchestrator `handle_event` — match, **gate via `is_enabled`**, dispatch

**Files:**
- Modify: `playAIdes.py` (add `handle_event`, e.g. just below `_dispatch_skill`)
- Test: `tests/unit/test_handle_event.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_handle_event.py
import types
from unittest.mock import MagicMock

from persona import Trigger
from skills.registry import SkillRegistry
from skills.pip import ShowPipSkill


def _make_ai(skills, triggers):
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.incarnation_server = MagicMock()
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.ha_client = None
    reg = SkillRegistry()
    reg.register(ShowPipSkill())
    ai.skill_registry = reg
    ai.current_persona = types.SimpleNamespace(
        name="Silver", persona_voice=None, language="English",
        skills=skills, triggers=triggers,
    )
    return ai


def test_event_fires_enabled_skill():
    triggers = [Trigger(on={"event": "motion", "match": {"state": "on"}},
                        do={"skill": "show_pip", "params": {"url": "http://x/s", "kind": "live"}})]
    ai = _make_ai(["show_pip"], triggers)
    result = ai.handle_event("motion", {"state": "on"})
    assert result == {"matched": True, "skill": "show_pip"}
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/s", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )


def test_event_registered_but_not_enabled_does_not_fire():
    # show_pip is registered AND a trigger references it, but it is NOT in the
    # persona's enable-list. The event path must NOT dispatch it. (The footgun.)
    triggers = [Trigger(on={"event": "motion"}, do={"skill": "show_pip", "params": {"url": "u"}})]
    ai = _make_ai([], triggers)                       # empty enable-list
    result = ai.handle_event("motion", {})
    assert result == {"matched": False}
    ai.incarnation_server.broadcast_to_persona.assert_not_called()


def test_event_no_matching_trigger():
    ai = _make_ai(["show_pip"], [])
    assert ai.handle_event("nothing", {}) == {"matched": False}


def test_event_no_persona():
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.current_persona = None
    assert ai.handle_event("motion", {}) == {"matched": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_handle_event.py -v`
Expected: FAIL — `AttributeError: 'PlayAIdes' object has no attribute 'handle_event'`.

- [ ] **Step 3: Add `handle_event` to `PlayAIdes`**

```python
    def handle_event(self, name: str, payload: dict) -> dict:
        """Inbound-event intake (spec §3.6). Resolve the active persona, match its
        event triggers, GATE via SkillRegistry.is_enabled, then dispatch. Returns
        {"matched": bool, "skill"?: str}. Never raises into the caller (the HTTP
        endpoint awaits this off the event loop)."""
        if not getattr(self, "current_persona", None):
            return {"matched": False}
        target_id = self.current_persona.name.strip().lower().replace(" ", "_")
        from skills.router import match_event_trigger
        matched = match_event_trigger(name, payload or {}, self.current_persona.triggers)
        if matched is None:
            return {"matched": False}
        skill_name, params = matched
        # ⚠️ Event-path enable-gate. The matcher does NOT check the enable-list and
        # _dispatch_skill checks only *registration*, so without this a registered-
        # but-not-enabled skill could fire from an inbound event (the carried-
        # forward contract: the event path must gate via SkillRegistry.is_enabled).
        if not self.skill_registry.is_enabled(skill_name, self.current_persona.skills):
            logger.info(
                "Event %r matched skill %r but it is not enabled for %s; ignoring.",
                name, skill_name, target_id,
            )
            return {"matched": False}
        self._dispatch_skill(target_id, skill_name, params)
        return {"matched": True, "skill": skill_name}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_handle_event.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add playAIdes.py tests/unit/test_handle_event.py
git commit -m "feat(playaides): handle_event gates via is_enabled before dispatch

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `POST /api/event` endpoint + server wiring

**Files:**
- Modify: `incarnation_server.py` (`__init__` signature at `incarnation_server.py:39-44`; add the endpoint in `_setup_routes`, after the `/api/dismiss` route at `incarnation_server.py:127-132`)
- Modify: `playAIdes.py` (pass `event_handler=self.handle_event` to the `IncarnationServer(...)` construction at `playAIdes.py:102-110`)
- Test: `tests/integration/test_event_endpoint.py`

- [ ] **Step 1: Write the failing test**

> **Why integration, not unit:** `IncarnationServer.__init__` normally spawns a daemon uvicorn thread that binds a real port. The repo's convention (see `tests/integration/conftest.py` and `test_persona_routing.py`) is to monkeypatch `threading` to a `_NoopThread` so the app is built but no thread/port is used, then drive the ASGI app with `TestClient`. These are marked `@pytest.mark.integration` (the project sets `--strict-markers`, so the marker is mandatory).

```python
# tests/integration/test_event_endpoint.py
"""Integration test (FastAPI TestClient, no external services): POST /api/event
routes to the orchestrator's event_handler; bearer auth gates it when set."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


class _NoopThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):  # pragma: no cover
        pass


def _build_server(monkeypatch, tmp_path, handler):
    """Build an IncarnationServer with no real uvicorn thread (repo convention)."""
    import incarnation_server as mod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "threading", type("m", (), {"Thread": _NoopThread}))
    return mod.IncarnationServer(host="127.0.0.1", port=18767, event_handler=handler)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PLAYAIDES_API_KEY", raising=False)   # dev mode: no auth
    calls: list = []

    def handler(name, payload):
        calls.append((name, payload))
        return {"matched": True, "skill": "show_pip"} if name == "motion" else {"matched": False}

    srv = _build_server(monkeypatch, tmp_path, handler)
    c = TestClient(srv.app)
    c.calls = calls
    return c


def test_event_routes_to_handler(client):
    r = client.post("/api/event", json={"name": "motion", "payload": {"state": "on"}})
    assert r.status_code == 200
    assert r.json() == {"matched": True, "skill": "show_pip"}
    assert client.calls == [("motion", {"state": "on"})]


def test_event_unmatched_returns_matched_false(client):
    r = client.post("/api/event", json={"name": "nope", "payload": {}})
    assert r.status_code == 200
    assert r.json() == {"matched": False}


def test_event_missing_name_is_422(client):
    r = client.post("/api/event", json={"payload": {}})
    assert r.status_code == 422       # pydantic body validation (FastAPI default)


def test_event_requires_bearer_when_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYAIDES_API_KEY", "secret")
    srv = _build_server(monkeypatch, tmp_path, lambda n, p: {"matched": False})
    c = TestClient(srv.app)
    assert c.post("/api/event", json={"name": "x", "payload": {}}).status_code == 401
    ok = c.post("/api/event", json={"name": "x", "payload": {}},
                headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/integration/test_event_endpoint.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'event_handler'` (raised in the fixture).

- [ ] **Step 3a: Add `event_handler` to the server constructor**

In `incarnation_server.py`, extend `IncarnationServer.__init__` (`incarnation_server.py:39-40`):

```python
    def __init__(self, host="0.0.0.0", port=8765, on_message_callback=None,
                 state_provider=None, event_handler=None):
```

And store it alongside the other callbacks (after `self.state_provider = state_provider` at `incarnation_server.py:44`):

```python
        # (name, payload) -> {"matched": bool, "skill"?: str}; the orchestrator's
        # PlayAIdes.handle_event. Called off the event loop (POST /api/event).
        self.event_handler = event_handler
```

- [ ] **Step 3b: Add the `POST /api/event` route**

In `_setup_routes`, after the `/api/dismiss` route (`incarnation_server.py:127-132`) and before `/api/state`, add:

```python
        class EventBody(BaseModel):
            name: str
            payload: dict = {}

        @self.app.post("/api/event")
        async def post_event(body: EventBody, _auth=Depends(require_api_key)):
            """Generic inbound-event intake (spec §3.6) — anything that can POST
            (HA automation, email watcher, n8n, a cron elsewhere) wires a trigger.
            Routes to the active persona's event triggers via the orchestrator.
            Run off the event loop (asyncio.to_thread) so a blocking bash/http
            skill never stalls the WS loop; _dispatch_skill's WS sends are still
            scheduled threadsafe back onto this loop."""
            if self.event_handler is None:
                raise HTTPException(status_code=503, detail="event handling unavailable")
            return await asyncio.to_thread(self.event_handler, body.name, body.payload)
```

(`asyncio`, `Depends`, `HTTPException`, and `BaseModel` are already imported at the top of `incarnation_server.py`.)

- [ ] **Step 3c: Pass `event_handler` from the orchestrator**

In `playAIdes.py`, extend the `IncarnationServer(...)` construction (`playAIdes.py:102-110`) to pass the handler:

```python
        self.incarnation_server: Optional[IncarnationServer] = IncarnationServer(
            on_message_callback=self._handle_incarnation_message,
            event_handler=self.handle_event,
            state_provider=lambda: {
                "active_persona_id": (
                    self.current_persona.name.strip().lower().replace(" ", "_")
                    if self.current_persona else None
                ),
            },
        ) if args.use_avatar else None
```

- [ ] **Step 4: Run test to verify it passes (and the existing server suite is green)**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/integration/test_event_endpoint.py -v`
Expected: PASS (4 passed).
Then confirm no regression in the existing integration server tests: `python -m pytest tests/integration -q`.
Expected: no new failures.

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation_server.py playAIdes.py tests/integration/test_event_endpoint.py
git commit -m "feat(server): add POST /api/event routed to handle_event off the WS loop

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: End-to-end verification

**Files:** `skill_packs/demo.json` (new); `personas/silver/persona.json` (edit, untracked); otherwise manual + suite run.

- [ ] **Step 1: Add a demo declarative pack**

Create `skill_packs/demo.json`:

```json
{
  "skills": [
    { "name": "ping_host", "kind": "bash",
      "command": ["ping", "-c", "1", "{host}"],
      "params": { "host": "str" }, "timeout_s": 5, "announce_output": false },
    { "name": "say_weather", "kind": "http", "method": "GET",
      "url": "https://wttr.in/{city}?format=3",
      "params": { "city": "str" }, "announce_output": true }
  ]
}
```

- [ ] **Step 2: Add an event trigger + camera source + the demo skills to Silver**

Edit `personas/silver/persona.json` — extend `skills` and `triggers` (Silver already has `show_pip`/`dismiss_pip` from Plan 1). Use a real camera entity_id from your HA if available; otherwise the phrase-with-url trigger from Plan 1 still demos the panel:

```json
  "skills": ["show_pip", "dismiss_pip", "ping_host", "say_weather"],
  "triggers": [
    { "on": { "event": "front_door_motion", "match": { "state": "on" } },
      "do": { "skill": "show_pip",
              "params": { "source": "camera.front_door", "kind": "live",
                          "announce": "Someone's at the front door." } } },
    { "on": { "phrase": "what's the weather" },
      "do": { "skill": "say_weather", "params": { "city": "Portland" } } }
  ]
```

- [ ] **Step 3: Run the full backend suite**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/ -q`
Expected: all new Plan-2 unit files green (`test_bash_skill`, `test_http_skill`, `test_skill_provider`, `test_skill_loader`, `test_ha_camera_url`, `test_event_router`, `test_handle_event`, `test_event_endpoint`) and Plan-1 files still green. Pre-existing unrelated red areas (e.g. voicebox test-image) are out of scope — confirm **no new** failures vs. the branch baseline.

- [ ] **Step 4: Manual smoke — declarative skill (no HA needed)**

1. Start backend + Vite dev server (the harness compose, or `--use_voice`/`--use_avatar` as configured). Confirm startup logs `Loaded 2 declarative skill(s) from skill_packs`.
2. Open the viewer, wake Silver, say **"what's the weather"** → Silver speaks the wttr.in one-liner (the `http` skill's `announce_output`). The utterance does **not** hit the LLM.

- [ ] **Step 5: Manual smoke — inbound event → camera PiP (HA)**

With `PLAYAIDES_API_KEY` set and a real `camera.front_door` entity (adjust the entity_id), from any host on the LAN:

```bash
curl -sS -X POST http://192.168.0.7:8765/api/event \
  -H "Authorization: Bearer $PLAYAIDES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"front_door_motion","payload":{"state":"on"}}'
```

Expected: response `{"matched":true,"skill":"show_pip"}`; the PiP panel appears on the TV showing the live camera feed; Silver says "Someone's at the front door." Then `curl ... -d '{"name":"front_door_motion","payload":{"state":"off"}}'` → `{"matched":false}` (the `match:{state:"on"}` condition fails) and nothing happens.

> The `PLAYAIDES_API_KEY` value lives in your `.env` / secret store and is read from the environment — do not paste it into chat. Use the `read -s` idiom if invoking curl interactively.

- [ ] **Step 6: Commit the demo artifacts**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skill_packs/demo.json
git commit -m "chore(skills): add demo bash/http skill pack

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(`personas/silver/persona.json` stays untracked by convention — do not commit it.)

---

## Spec coverage map (self-review)

| Spec section | Covered by |
|---|---|
| §3.2 `bash` kind (argv, no shell) | Task 1 |
| §3.2 `http` kind (safe interpolation) | Task 2 |
| §3.2 `provider` interface (defined, not auto-loaded) | Task 3 |
| §3.3 declarative loading from global pack dir + fail-fast validation | Task 4 |
| §3.3 provider registration ability | Task 3 |
| §3.4 `event` trigger (`name` + `match`) | Task 7 (matcher uses `Trigger.on.event/match` — model already in `persona.py`) |
| §3.5 event path (deterministic, no LLM) | Tasks 7–8 |
| §3.5 **enable-gate on the event path** (`is_enabled`) | Task 8 (+ negative test) |
| §3.6 `POST /api/event` (bearer auth, `{matched, skill?}`) | Task 9 |
| §3.10 HA-entity → `camera_proxy` URL resolution | Tasks 5–6 |
| §5 security: `bash` argv-only; `http` url/JSON-encoded; event bearer auth | Tasks 1, 2, 9 |
| §6 error handling: bad pack → fail-fast; unknown/disabled skill no-op; unreachable camera → None | Tasks 4, 8, 5 |
| §7 testing: pure matchers, declarative skills, fake ctx, endpoint via TestClient | Tasks 1–9 |

**Deferred (by design, not in this plan):** `brain_model` + `captions` (Plan 3); external-pack *discovery*/auto-load, phrase slot-extraction, agentic router, timer/cron triggers, pack sandboxing, partial/templated param interpolation (spec §10). The spec's bare "`skills/`" pack dir is realized as **`skill_packs/`** to avoid colliding with the `skills/` Python package.

**Self-review notes (run after drafting):**
- *Placeholder scan:* every code step shows complete code; no TBD/TODO.
- *Type consistency:* `match_event_trigger(name, payload, triggers) -> (skill, params)|None`; `_interpolate_params(params, payload)`; `BashSkill(spec)`/`HttpSkill(spec)` set instance `name`/`kind`/`Params`; `build_params_model(name, spec) -> type[BaseModel]`; `load_skill_packs(dir) -> list[Skill]`; `SkillRegistry.register_all/register_provider`; `SkillContext.resolve_camera`/`resolve_camera_url(entity_id, live)`; `HAClient.camera_url(entity_id, stream)`; `PlayAIdes._resolve_camera_url(entity_id, live)`/`handle_event(name, payload)`; `IncarnationServer(..., event_handler)` + `POST /api/event {name, payload}` → `{matched, skill?}`. Names align across tasks.
- *Gating contract:* the event path's enable-gate is `SkillRegistry.is_enabled` in `handle_event` (Task 8), with Task 8's `test_event_registered_but_not_enabled_does_not_fire` proving the footgun is closed. The pure event matcher deliberately does **not** check enablement, so the gate is exercised at the dispatch boundary.
- *Back-compat:* `SkillContext.resolve_camera` defaults `None` (Plan-1 positional constructions unaffected); `ShowPipSkill.url` becomes optional but the url-or-source validator keeps `Params()`-with-nothing a validation failure, so Plan-1's `test_dispatch_bad_params_is_noop` still holds.
