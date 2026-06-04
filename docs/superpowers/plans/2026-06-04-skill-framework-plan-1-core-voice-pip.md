# Persona Skill Framework — Plan 1: Core + Deterministic Voice Router + PiP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first vertical slice of the persona skill+trigger framework — a deterministic voice phrase can fire an internal skill, and the first skill (`show_pip`/`dismiss_pip`) renders a picture-in-picture panel on the TV. Demo: configure Silver with a `show_pip` skill + a `"show the front door"` phrase trigger, say it, and a panel appears.

**Architecture:** Skills are sync Python objects behind a common interface, held in a `SkillRegistry`. A pure phrase-matcher (`match_phrase_trigger`) turns a post-wake utterance into a `(skill_name, params)` pair using the persona's `triggers` config; `PlayAIdes.chat()` checks it **before** `house_words` and conversation, and on a match dispatches the skill (silent unless it announces) instead of calling the LLM. Skills act through a `SkillContext` that wraps the existing `broadcast_to_persona` (WS push) and a new `speak_as_persona` helper. The frontend gains a `PipOverlay` driven by new `show_pip`/`dismiss_pip` WS messages.

**Tech Stack:** Python 3.12 + Pydantic + FastAPI (backend); vanilla ES modules + Vite + Vitest (frontend); pytest (backend tests).

**Spec:** [`../specs/2026-06-04-persona-skill-trigger-framework-design.md`](../specs/2026-06-04-persona-skill-trigger-framework-design.md). This plan covers spec §3.1, §3.3 (internal only), §3.4 (phrase), §3.5 (voice path), §3.7, §3.8 (`skills`/`triggers` fields), §3.10. Deferred to Plans 2–3: `bash`/`http`/provider kinds, global `skills/` loader, `POST /api/event`, `brain_model`, captions.

**Conventions:**
- All paths are under the git repo `/home/bell/repo/ai_life/playAIdes` (the parent `ai_life/` is NOT a repo). Run pytest and git from that root.
- Execute on a feature branch / worktree (the executor's git skill handles this).
- Skills are **synchronous** in v1 — `PlayAIdes.chat()` and `broadcast_to_persona` are synchronous (the latter schedules sends via `run_coroutine_threadsafe` internally), so introducing `async` here would force an event loop into the orchestrator. (Refines the spec's `async def execute` sketch.)
- For PiP, the skill carries a direct **`url`** (snapshot image or MJPEG stream). Resolving an HA camera *entity* → a `camera_proxy` URL is Plan 2.
- End every commit message with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.

---

## File structure

**Create (backend):**
- `skills/__init__.py` — package marker + public exports.
- `skills/base.py` — `SkillResult`, `SkillContext`, `Skill` base.
- `skills/registry.py` — `SkillRegistry`.
- `skills/pip.py` — `ShowPipSkill`, `DismissPipSkill`.
- `skills/router.py` — pure `match_phrase_trigger`.

**Create (backend tests):**
- `tests/unit/test_persona_triggers.py`, `tests/unit/test_skill_base.py`, `tests/unit/test_skill_registry.py`, `tests/unit/test_pip_skills.py`, `tests/unit/test_phrase_router.py`, `tests/unit/test_chat_skill_dispatch.py`.

**Modify (backend):**
- `persona.py` — add `TriggerOn`, `TriggerDo`, `Trigger`; add `skills`, `triggers` fields to `Persona`.
- `playAIdes.py` — build registry in `__init__`; add `speak_as_persona`, `_skill_send`, `_dispatch_skill`; hook `match_phrase_trigger` into `chat()`.

**Create (frontend):**
- `incarnation/src/pipOverlay.js` — pure `pipViewFromMessage` + `PipOverlay` class.
- `incarnation/src/pipOverlay.test.js` — tests for the pure function.

**Modify (frontend):**
- `incarnation/index.html` — add `#pip-overlay`.
- `incarnation/styles/viewer.css` — add `.pip-overlay` rules.
- `incarnation/src/viewer.js` — instantiate `PipOverlay`, wire `show_pip`/`dismiss_pip`, extend the catch-all exclude list.

---

## Task 1: Persona config — `Trigger` models + `skills`/`triggers` fields

**Files:**
- Modify: `persona.py` (add models near top; add fields to `Persona` at `persona.py:40-54`)
- Test: `tests/unit/test_persona_triggers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_persona_triggers.py
from persona import Persona, Trigger


def _base_persona_kwargs():
    return {
        "name": "Silver",
        "back_ground": "bg",
        "psyche": {"traits": ["loyal"]},
        "gender": "Female",
    }


def test_persona_defaults_have_empty_skills_and_triggers():
    p = Persona(**_base_persona_kwargs())
    assert p.skills == []
    assert p.triggers == []


def test_persona_parses_phrase_and_event_triggers():
    p = Persona(
        **_base_persona_kwargs(),
        skills=["show_pip", "dismiss_pip"],
        triggers=[
            {"on": {"phrase": "show the front door"},
             "do": {"skill": "show_pip", "params": {"url": "http://x/stream", "kind": "live"}}},
            {"on": {"event": "front_door_motion", "match": {"state": "on"}},
             "do": {"skill": "show_pip"}},
        ],
    )
    assert p.skills == ["show_pip", "dismiss_pip"]
    assert isinstance(p.triggers[0], Trigger)
    assert p.triggers[0].on.phrase == "show the front door"
    assert p.triggers[0].do.skill == "show_pip"
    assert p.triggers[0].do.params == {"url": "http://x/stream", "kind": "live"}
    assert p.triggers[1].on.event == "front_door_motion"
    assert p.triggers[1].do.params == {}


def test_existing_persona_json_without_skills_still_loads():
    # Back-compat: omitting the new fields must not break.
    p = Persona(**_base_persona_kwargs())
    assert isinstance(p, Persona)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_persona_triggers.py -v`
Expected: FAIL — `ImportError: cannot import name 'Trigger' from 'persona'`.

- [ ] **Step 3: Add the models and fields**

In `persona.py`, add these classes just above `class Persona` (after the `Memories` class, before line 39's comment):

```python
class TriggerOn(BaseModel):
    phrase: Optional[str] = None          # deterministic voice-phrase match
    event: Optional[str] = None           # inbound event name (Plan 2)
    match: Optional[dict] = None          # shallow payload conditions (Plan 2)

class TriggerDo(BaseModel):
    skill: str
    params: dict = {}

class Trigger(BaseModel):
    on: TriggerOn
    do: TriggerDo
```

Then add two fields to `class Persona` (after `house_words: List[str] = []` at `persona.py:52`):

```python
    skills: List[str] = []                # enabled skill names (the flat skill-tree)
    triggers: List[Trigger] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_persona_triggers.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add persona.py tests/unit/test_persona_triggers.py
git commit -m "feat(persona): add Trigger models and skills/triggers fields

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Skill base types — `SkillResult`, `SkillContext`, `Skill`

**Files:**
- Create: `skills/__init__.py`, `skills/base.py`
- Test: `tests/unit/test_skill_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_skill_base.py
from pydantic import BaseModel
from skills.base import Skill, SkillContext, SkillResult


def test_skill_result_defaults_ok():
    r = SkillResult()
    assert r.ok is True
    assert r.output is None and r.error is None


def test_skill_context_send_display_uses_target_id():
    sent = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda pid, t, p: sent.append((pid, t, p)),
        speak_fn=lambda pid, text: None,
    )
    ctx.send_display("show_pip", {"url": "http://x"})
    assert sent == [("silver", "show_pip", {"url": "http://x"})]


def test_skill_context_speak_uses_target_id():
    spoken = []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda *a: None,
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    ctx.speak("hello")
    assert spoken == [("silver", "hello")]


def test_skill_base_requires_execute():
    class Noop(Skill):
        name = "noop"
        class Params(BaseModel):
            pass
    s = Noop()
    assert s.name == "noop" and s.kind == "internal"
    try:
        s.execute(Noop.Params(), None)
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills'`.

- [ ] **Step 3: Create the package and base types**

```python
# skills/__init__.py
from skills.base import Skill, SkillContext, SkillResult
from skills.registry import SkillRegistry

__all__ = ["Skill", "SkillContext", "SkillResult", "SkillRegistry"]
```

```python
# skills/base.py
"""Common interface for persona skills (spec §3.1).

A Skill is a named capability behind one interface; the deterministic router
(now) and the future agentic router both dispatch the same Skill objects.
Skills are synchronous: PlayAIdes.chat() is synchronous and the WS broadcast
helper schedules sends on the WS loop internally, so no event loop is needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel


class SkillResult(BaseModel):
    ok: bool = True
    output: Optional[str] = None    # e.g. bash stdout / http body excerpt (Plan 2)
    error: Optional[str] = None


@dataclass
class SkillContext:
    """A skill's only door to the system, bound to one persona invocation."""
    persona: Any                                  # persona.Persona (Any to avoid import cycle)
    target_id: str                                # canonical persona id this turn routes to
    send: Callable[[str, str, dict], None]        # (persona_id, cmd_type, payload) -> WS push
    speak_fn: Callable[[str, str], None]          # (persona_id, text) -> subtitle + TTS

    def send_display(self, cmd_type: str, payload: Optional[dict] = None) -> None:
        self.send(self.target_id, cmd_type, payload or {})

    def speak(self, text: str) -> None:
        self.speak_fn(self.target_id, text)


class Skill:
    """Base for all skills. Subclasses set `name`, `Params`, and `execute`."""
    name: str
    Params: type[BaseModel]
    kind: str = "internal"

    def execute(self, params: BaseModel, ctx: SkillContext) -> SkillResult:
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_base.py -v`
Expected: PASS (4 passed). (`skills/registry.py` is imported by `__init__`; it's created in Task 3 — if running this task in isolation, temporarily comment the registry import. It is present by the time the suite runs end-to-end.)

> **Note for the executor:** to keep `skills/__init__.py` importable before Task 3, create a minimal `skills/registry.py` stub now (`class SkillRegistry: ...`) or run Task 3 immediately after. The full registry lands in Task 3.

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/__init__.py skills/base.py tests/unit/test_skill_base.py
git commit -m "feat(skills): add Skill/SkillContext/SkillResult base interface

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `SkillRegistry`

**Files:**
- Create: `skills/registry.py`
- Test: `tests/unit/test_skill_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_skill_registry.py
from pydantic import BaseModel
from skills.base import Skill, SkillResult
from skills.registry import SkillRegistry


class _Fake(Skill):
    name = "fake"
    class Params(BaseModel):
        pass
    def execute(self, params, ctx):
        return SkillResult()


def test_register_and_get():
    reg = SkillRegistry()
    reg.register(_Fake())
    assert reg.get("fake").name == "fake"
    assert reg.get("missing") is None


def test_duplicate_name_raises():
    reg = SkillRegistry()
    reg.register(_Fake())
    try:
        reg.register(_Fake())
        assert False, "expected ValueError on duplicate"
    except ValueError:
        pass


def test_is_enabled_checks_persona_list():
    reg = SkillRegistry()
    reg.register(_Fake())
    assert reg.is_enabled("fake", ["fake", "other"]) is True
    assert reg.is_enabled("fake", []) is False
    assert reg.is_enabled("missing", ["missing"]) is False   # not registered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_registry.py -v`
Expected: FAIL — `ImportError`/`AttributeError` (no real `SkillRegistry`).

- [ ] **Step 3: Implement the registry**

```python
# skills/registry.py
"""Name → Skill map. Internal skills register here at startup (spec §3.3).
Declarative (bash/http) and provider skills are added in Plan 2."""
from __future__ import annotations

from typing import Optional

from skills.base import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def is_enabled(self, name: str, enabled_skills: list[str]) -> bool:
        """True only if the skill is both registered AND enabled for the persona."""
        return name in self._skills and name in enabled_skills
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_skill_registry.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/registry.py tests/unit/test_skill_registry.py
git commit -m "feat(skills): add SkillRegistry with enable-gating

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: PiP skills — `ShowPipSkill`, `DismissPipSkill`

**Files:**
- Create: `skills/pip.py`
- Test: `tests/unit/test_pip_skills.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_pip_skills.py
from skills.base import SkillContext
from skills.pip import ShowPipSkill, DismissPipSkill


def _ctx():
    sent, spoken = [], []
    ctx = SkillContext(
        persona=None, target_id="silver",
        send=lambda pid, t, p: sent.append((pid, t, p)),
        speak_fn=lambda pid, text: spoken.append((pid, text)),
    )
    return ctx, sent, spoken


def test_show_pip_sends_show_message():
    ctx, sent, spoken = _ctx()
    skill = ShowPipSkill()
    skill.execute(skill.Params(url="http://x/stream", kind="live"), ctx)
    assert sent == [("silver", "show_pip",
                     {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}})]
    assert spoken == []   # silent: no announce


def test_show_pip_announce_speaks():
    ctx, sent, spoken = _ctx()
    skill = ShowPipSkill()
    skill.execute(skill.Params(url="http://x.jpg", announce="Someone's at the door."), ctx)
    assert sent[0][1] == "show_pip"
    assert spoken == [("silver", "Someone's at the door.")]


def test_dismiss_pip_sends_dismiss_message():
    ctx, sent, spoken = _ctx()
    skill = DismissPipSkill()
    skill.execute(skill.Params(), ctx)
    assert sent == [("silver", "dismiss_pip", {})]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_pip_skills.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.pip'`.

- [ ] **Step 3: Implement the PiP skills**

```python
# skills/pip.py
"""Internal (hard-typed) PiP skills (spec §3.10). v1 takes a direct url;
HA-entity → camera_proxy resolution is Plan 2."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from skills.base import Skill, SkillContext, SkillResult


class ShowPipSkill(Skill):
    name = "show_pip"
    kind = "internal"

    class Params(BaseModel):
        url: str
        kind: Literal["live", "snapshot"] = "snapshot"
        dismiss: dict = {"type": "until_dismissed"}
        announce: Optional[str] = None

    def execute(self, params: "ShowPipSkill.Params", ctx: SkillContext) -> SkillResult:
        ctx.send_display("show_pip", {
            "url": params.url,
            "kind": params.kind,
            "dismiss": params.dismiss,
        })
        if params.announce:
            ctx.speak(params.announce)
        return SkillResult(ok=True)


class DismissPipSkill(Skill):
    name = "dismiss_pip"
    kind = "internal"

    class Params(BaseModel):
        pass

    def execute(self, params: "DismissPipSkill.Params", ctx: SkillContext) -> SkillResult:
        ctx.send_display("dismiss_pip", {})
        return SkillResult(ok=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_pip_skills.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/pip.py tests/unit/test_pip_skills.py
git commit -m "feat(skills): add show_pip/dismiss_pip internal skills

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Phrase router — pure `match_phrase_trigger`

**Files:**
- Create: `skills/router.py`
- Test: `tests/unit/test_phrase_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_phrase_router.py
from persona import Trigger
from skills.router import match_phrase_trigger


def _t(phrase, skill, params=None):
    return Trigger(on={"phrase": phrase}, do={"skill": skill, "params": params or {}})


def test_matches_enabled_phrase_trigger():
    triggers = [_t("show the front door", "show_pip", {"url": "http://x"})]
    out = match_phrase_trigger("Show the front door", triggers, ["show_pip"])
    assert out == ("show_pip", {"url": "http://x"})


def test_skips_disabled_skill():
    triggers = [_t("show the front door", "show_pip")]
    assert match_phrase_trigger("show the front door", triggers, []) is None


def test_no_match_returns_none():
    triggers = [_t("show the front door", "show_pip")]
    assert match_phrase_trigger("what time is it", triggers, ["show_pip"]) is None


def test_first_match_wins():
    triggers = [
        _t("dismiss", "dismiss_pip"),
        _t("dismiss", "show_pip"),
    ]
    out = match_phrase_trigger("dismiss", triggers, ["dismiss_pip", "show_pip"])
    assert out[0] == "dismiss_pip"


def test_word_boundary_no_partial_match():
    # "show" must not match inside "showcase" (match_keyword_prefix semantics).
    triggers = [_t("show", "show_pip")]
    assert match_phrase_trigger("showcase the art", triggers, ["show_pip"]) is None


def test_event_triggers_are_ignored_by_phrase_router():
    triggers = [Trigger(on={"event": "motion"}, do={"skill": "show_pip"})]
    assert match_phrase_trigger("motion", triggers, ["show_pip"]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_phrase_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skills.router'`.

- [ ] **Step 3: Implement the matcher**

```python
# skills/router.py
"""Deterministic router — pure matchers (spec §3.5). No LLM in the loop.
v1: the voice (phrase) path. The event path lands in Plan 2."""
from __future__ import annotations

from typing import Optional

from match_keywords import match_keyword_prefix


def match_phrase_trigger(text, triggers, enabled_skills) -> Optional[tuple[str, dict]]:
    """First enabled phrase-trigger whose phrase prefixes `text` wins.

    Returns (skill_name, params) or None. Reuses match_keyword_prefix's
    case-insensitive, word-boundary, prefix-only semantics. Event triggers
    (no `on.phrase`) are ignored here.
    """
    for trig in triggers:
        phrase = trig.on.phrase
        if not phrase:
            continue
        matched, _residual = match_keyword_prefix(text, [phrase])
        if matched and trig.do.skill in enabled_skills:
            return (trig.do.skill, dict(trig.do.params))
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_phrase_router.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add skills/router.py tests/unit/test_phrase_router.py
git commit -m "feat(skills): add deterministic phrase-trigger matcher

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Extract `speak_as_persona` from `chat()` (refactor)

This makes the "broadcast subtitle + TTS lip-sync" logic reusable by skills (`ctx.speak`) without duplicating it. Behavior-preserving.

**Files:**
- Modify: `playAIdes.py` (`chat()` broadcast/TTS block at `playAIdes.py:794-824`; add new method)
- Test: `tests/unit/test_speak_as_persona.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_speak_as_persona.py
import types
from unittest.mock import MagicMock


def _make_ai():
    # Build a PlayAIdes-like object with just the attributes speak_as_persona needs.
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)            # skip __init__
    ai.incarnation_server = MagicMock()
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.tts = MagicMock()
    # current_persona with a valid voice
    ai.current_persona = types.SimpleNamespace(
        persona_voice=types.SimpleNamespace(speaker_uuid="uuid-1"),
        language="English",
    )
    return ai


def test_speak_broadcasts_assistant_message():
    ai = _make_ai()
    ai.speak_as_persona("silver", "hello there")
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "assistant_message", {"text": "hello there", "persona_id": "silver"},
    )


def test_speak_sends_lip_sync_when_voice_and_avatar_on():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = True
    ai.speak_as_persona("silver", "hi")
    calls = [c.args[1] for c in ai.incarnation_server.broadcast_to_persona.call_args_list]
    assert "start_lip_sync" in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_speak_as_persona.py -v`
Expected: FAIL — `AttributeError: 'PlayAIdes' object has no attribute 'speak_as_persona'`.

- [ ] **Step 3: Add `speak_as_persona` and call it from `chat()`**

Add this method to the `PlayAIdes` class (e.g. just above `chat`):

```python
    def speak_as_persona(self, target_id: str, text: str) -> None:
        """Broadcast `text` as the persona's reply (subtitle) and trigger TTS
        lip-sync on the persona's bound displays. Extracted from chat() so
        skills can reuse it via SkillContext.speak. No-op pieces degrade
        gracefully in CLI-only mode."""
        if self.incarnation_server is not None:
            self.incarnation_server.broadcast_to_persona(
                target_id, "assistant_message", {"text": text, "persona_id": target_id},
            )
        if not self.args.use_voice:
            return
        voice = getattr(self.current_persona, "persona_voice", None)
        if not (voice and voice.speaker_uuid):
            logger.warning(
                "Persona %s has no voice config; skipping lip_sync",
                self.current_persona.name,
            )
            return
        if self.args.use_avatar and self.incarnation_server:
            import urllib.parse
            safe_text = urllib.parse.quote(text)
            proxy_url = (
                f"http://localhost:8765/api/tts/proxy?text={safe_text}"
                f"&speaker_id={voice.speaker_uuid}"
            )
            if self.current_persona.language:
                proxy_url += f"&language={urllib.parse.quote(self.current_persona.language)}"
            logger.info(f"Sending start_lip_sync: {proxy_url}")
            self.incarnation_server.broadcast_to_persona(
                target_id, "start_lip_sync", {"url": proxy_url},
            )
        else:
            from model_interfaces import SpeechGenerationRequest  # local import; matches chat()
            self.tts.generate_speech_stream(SpeechGenerationRequest(
                text=text,
                speaker_id=voice.speaker_uuid,
                language=self.current_persona.language or "English",
            ))
```

Now replace the broadcast+TTS block in `chat()` (the code from `playAIdes.py:794` `if self.incarnation_server is not None:` through `playAIdes.py:824`, ending before `history.append({"role": "assistant", ...})`) with a single call:

```python
        # Broadcast the reply to the persona's displays + TTS lip-sync.
        self.speak_as_persona(target_id, response)
```

> Verify the `SpeechGenerationRequest` import: `chat()` currently imports it inline in the no-avatar branch. Confirm the symbol name/module against the original (`from model_interfaces import SpeechGenerationRequest` — adjust if the original used a different module path).

- [ ] **Step 4: Run tests to verify they pass (and nothing regressed)**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_speak_as_persona.py -v && python -m pytest tests/ -q`
Expected: new tests PASS; the broader suite has no new failures attributable to this change.

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add playAIdes.py tests/unit/test_speak_as_persona.py
git commit -m "refactor(playaides): extract speak_as_persona from chat()

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Build the registry + `_dispatch_skill` + `_skill_send` in `PlayAIdes`

**Files:**
- Modify: `playAIdes.py` (`__init__` around `playAIdes.py:99-154`; add two methods)
- Test: `tests/unit/test_chat_skill_dispatch.py` (dispatch half)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_chat_skill_dispatch.py
import types
from unittest.mock import MagicMock

from skills.registry import SkillRegistry
from skills.pip import ShowPipSkill


def _make_ai():
    from playAIdes import PlayAIdes
    ai = PlayAIdes.__new__(PlayAIdes)
    ai.incarnation_server = MagicMock()
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.current_persona = types.SimpleNamespace(name="Silver", persona_voice=None, language="English")
    reg = SkillRegistry()
    reg.register(ShowPipSkill())
    ai.skill_registry = reg
    return ai


def test_dispatch_skill_runs_skill_and_sends_ws():
    ai = _make_ai()
    ai._dispatch_skill("silver", "show_pip", {"url": "http://x/stream", "kind": "live"})
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )


def test_dispatch_unknown_skill_is_noop():
    ai = _make_ai()
    ai._dispatch_skill("silver", "nope", {})       # must not raise
    ai.incarnation_server.broadcast_to_persona.assert_not_called()


def test_dispatch_bad_params_is_noop():
    ai = _make_ai()
    ai._dispatch_skill("silver", "show_pip", {})    # missing required `url`; must not raise
    ai.incarnation_server.broadcast_to_persona.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_chat_skill_dispatch.py -v`
Expected: FAIL — `AttributeError: 'PlayAIdes' object has no attribute '_dispatch_skill'`.

- [ ] **Step 3: Add registry construction + dispatch methods**

In `PlayAIdes.__init__` (after `self.incarnation_server` is assigned, near `playAIdes.py:100-110`), build the registry:

```python
        from skills.registry import SkillRegistry
        from skills.pip import ShowPipSkill, DismissPipSkill
        self.skill_registry = SkillRegistry()
        self.skill_registry.register(ShowPipSkill())
        self.skill_registry.register(DismissPipSkill())
```

Add these two methods to the `PlayAIdes` class:

```python
    def _skill_send(self, persona_id: str, cmd_type: str, payload: dict) -> None:
        """SkillContext.send backing — push a WS frame to the persona's displays."""
        if self.incarnation_server is not None:
            self.incarnation_server.broadcast_to_persona(persona_id, cmd_type, payload)

    def _dispatch_skill(self, target_id: str, skill_name: str, raw_params: dict) -> None:
        """Validate params and run a skill. Never raises into the caller."""
        from skills.base import SkillContext
        skill = self.skill_registry.get(skill_name)
        if skill is None:
            logger.warning("Skill %r not registered; ignoring.", skill_name)
            return
        try:
            params = skill.Params(**(raw_params or {}))
        except Exception as e:
            logger.warning("Skill %r param validation failed: %s", skill_name, e)
            return
        ctx = SkillContext(
            persona=self.current_persona,
            target_id=target_id,
            send=self._skill_send,
            speak_fn=self.speak_as_persona,
        )
        try:
            skill.execute(params, ctx)
        except Exception as e:
            logger.exception("Skill %r execute failed: %s", skill_name, e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_chat_skill_dispatch.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add playAIdes.py tests/unit/test_chat_skill_dispatch.py
git commit -m "feat(playaides): register skills and add _dispatch_skill

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Hook the phrase router into `chat()`

**Files:**
- Modify: `playAIdes.py` (`chat()` at `playAIdes.py:720-726`)
- Test: extend `tests/unit/test_chat_skill_dispatch.py`

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
# append to tests/unit/test_chat_skill_dispatch.py
from persona import Trigger


def _make_chat_ai():
    ai = _make_ai()
    ai.llm = MagicMock()
    ai.llm.chat.return_value = "LLM REPLY"
    ai.ha_client = None
    ai.args = types.SimpleNamespace(use_voice=False, use_avatar=False, ha_default_agent_id=None)
    ai._load_history = lambda tid: []
    ai._save_history = lambda tid: None
    ai.current_persona = types.SimpleNamespace(
        name="Silver", persona_voice=None, language="English",
        psyche=None, memories=None, back_ground="bg", house_words=[],
        skills=["show_pip"],
        triggers=[Trigger(on={"phrase": "show the front door"},
                          do={"skill": "show_pip", "params": {"url": "http://x/stream", "kind": "live"}})],
    )
    return ai


def test_phrase_trigger_short_circuits_llm():
    ai = _make_chat_ai()
    out = ai.chat("show the front door")
    ai.llm.chat.assert_not_called()                       # conversation skipped
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "show_pip",
        {"url": "http://x/stream", "kind": "live", "dismiss": {"type": "until_dismissed"}},
    )
    assert out == ""


def test_non_trigger_input_falls_through_to_llm():
    ai = _make_chat_ai()
    out = ai.chat("how are you")
    ai.llm.chat.assert_called()                           # normal conversation
    assert out == "LLM REPLY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_chat_skill_dispatch.py -v -k phrase_trigger_short_circuits or fall`
Expected: FAIL — `show the front door` still reaches `llm.chat` (router not wired).

- [ ] **Step 3: Insert the phrase-trigger check at the top of `chat()`**

In `chat()`, immediately after `target_id` is resolved (`playAIdes.py:725`) and before `history = self._load_history(target_id)`:

```python
        # ─ Deterministic skill triggers (phrase path) ──────────────────
        # Precedence: phrase-trigger → house_words → conversation (spec §3.5).
        from skills.router import match_phrase_trigger
        matched = match_phrase_trigger(
            user_input, self.current_persona.triggers, self.current_persona.skills,
        )
        if matched is not None:
            skill_name, params = matched
            self._dispatch_skill(target_id, skill_name, params)
            return ""   # silent unless the skill spoke an announce (spec Q2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/unit/test_chat_skill_dispatch.py -v`
Expected: PASS (5 passed total in the file).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add playAIdes.py tests/unit/test_chat_skill_dispatch.py
git commit -m "feat(playaides): route voice phrase-triggers before conversation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Frontend — `pipOverlay.js` pure resolver + class

**Files:**
- Create: `incarnation/src/pipOverlay.js`, `incarnation/src/pipOverlay.test.js`

- [ ] **Step 1: Write the failing test**

```javascript
// incarnation/src/pipOverlay.test.js
import { describe, it, expect } from 'vitest';
import { pipViewFromMessage } from './pipOverlay.js';

describe('pipViewFromMessage', () => {
    it('show_pip live → visible live view with url', () => {
        expect(pipViewFromMessage('show_pip', { url: 'http://x/stream', kind: 'live' }))
            .toEqual({ visible: true, url: 'http://x/stream', kind: 'live' });
    });

    it('show_pip defaults kind to snapshot', () => {
        expect(pipViewFromMessage('show_pip', { url: 'http://x.jpg' }))
            .toEqual({ visible: true, url: 'http://x.jpg', kind: 'snapshot' });
    });

    it('dismiss_pip → hidden', () => {
        expect(pipViewFromMessage('dismiss_pip', {}))
            .toEqual({ visible: false, url: '', kind: null });
    });

    it('show_pip with no url → hidden (nothing to show)', () => {
        expect(pipViewFromMessage('show_pip', {}))
            .toEqual({ visible: false, url: '', kind: null });
    });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run src/pipOverlay.test.js`
Expected: FAIL — cannot resolve `./pipOverlay.js`.

- [ ] **Step 3: Implement the module**

```javascript
// incarnation/src/pipOverlay.js
/**
 * pipOverlay.js — picture-in-picture panel (spec §3.10).
 *
 * `pipViewFromMessage` is the pure decision function (unit-tested); the
 * `PipOverlay` class is the thin DOM glue (untested, per repo convention —
 * there is no jsdom harness). Driven by `show_pip` / `dismiss_pip` WS messages.
 */

/** Pure: compute the desired overlay view from an inbound WS message. */
export function pipViewFromMessage(type, payload = {}) {
    if (type === 'show_pip' && payload.url) {
        return {
            visible: true,
            url: payload.url,
            kind: payload.kind === 'live' ? 'live' : 'snapshot',
        };
    }
    // dismiss_pip, or show_pip with no url, or anything else → hidden.
    return { visible: false, url: '', kind: null };
}

export class PipOverlay {
    /** @param {Document|HTMLElement} root */
    constructor(root) {
        this.el = root.querySelector('#pip-overlay');
        this.img = root.querySelector('#pip-image');
    }

    /** @param {{visible:boolean,url:string,kind:string|null}} view */
    apply(view) {
        if (!this.el) return;
        if (view.visible && view.url) {
            if (this.img) this.img.src = view.url;
            this.el.classList.add('visible');
        } else {
            this.el.classList.remove('visible');
            // Drop the src so an MJPEG stream stops fetching when hidden.
            if (this.img) this.img.removeAttribute('src');
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npx vitest run src/pipOverlay.test.js`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/pipOverlay.js incarnation/src/pipOverlay.test.js
git commit -m "feat(viewer): add PipOverlay + pure pipViewFromMessage

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Frontend — `#pip-overlay` markup + CSS

**Files:**
- Modify: `incarnation/index.html` (after the `#nameplate` block, `index.html:27-31`)
- Modify: `incarnation/styles/viewer.css` (append a new section)

- [ ] **Step 1: Add the markup**

In `incarnation/index.html`, after the `#nameplate` `<div>` (closes at `index.html:31`) and before the chat-panel block:

```html
    <!-- Picture-in-picture panel (spec §3.10). Hidden until a show_pip WS
         message; command-driven, so no config-flag gate. -->
    <div id="pip-overlay" class="pip-overlay">
      <img id="pip-image" class="pip-image" alt="" />
    </div>
```

- [ ] **Step 2: Add the styles**

Append to `incarnation/styles/viewer.css` (after the kiosk block, `viewer.css:413-421`):

```css
/* ── Picture-in-picture panel (?show_pip) ──────────────────────
   Top-right, inside the TV title-safe area. Sits above mic/subtitle
   (z 70/80) and below the chat panel (z 90) and wipe (z 200). It is
   command-driven (only visible while a show_pip is active), so unlike
   the mic/subtitle/nameplate overlays it has no config-flag gate. */
.pip-overlay {
    position: fixed;
    top: 6%;
    right: 5%;
    width: min(28vw, 380px);
    aspect-ratio: 16 / 9;
    border: var(--hair) solid var(--gold);
    background: rgba(10, 8, 18, .9);
    box-shadow: 0 8px 32px rgba(0, 0, 0, .5);
    overflow: hidden;
    opacity: 0;
    transition: opacity .35s var(--ease-snap);
    z-index: 85;
    pointer-events: none;
}

.pip-overlay.visible { opacity: 1; }

.pip-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}
```

- [ ] **Step 3: Verify it builds**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npm run build`
Expected: build succeeds (no template/CSS errors).

- [ ] **Step 4: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/index.html incarnation/styles/viewer.css
git commit -m "feat(viewer): add #pip-overlay markup and styles

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Frontend — wire `PipOverlay` into `viewer.js`

**Files:**
- Modify: `incarnation/src/viewer.js` (boot wiring `viewer.js:45-66`; add listeners; extend catch-all exclude at `viewer.js:475-485`)

- [ ] **Step 1: Import and instantiate**

At the top of `viewer.js`, add to the imports:

```javascript
import { PipOverlay, pipViewFromMessage } from './pipOverlay.js';
```

In the boot wiring (near `const overlays = new ViewerOverlays(document, config, stateMachine);` at `viewer.js:46`):

```javascript
const pip = new PipOverlay(document);
```

- [ ] **Step 2: Add the WS listeners**

Near the other `connection.addEventListener('<type>', ...)` handlers (e.g. after the `stop_lip_sync` handler at `viewer.js:241-244`):

```javascript
connection.addEventListener('show_pip', (e) => {
    pip.apply(pipViewFromMessage('show_pip', e.detail || {}));
});
connection.addEventListener('dismiss_pip', () => {
    pip.apply(pipViewFromMessage('dismiss_pip', {}));
});
```

- [ ] **Step 3: Exclude the new types from the catch-all forwarder**

The catch-all `'message'` handler (`viewer.js:475-485`) forwards unknown types into `incarnation.handleCommand`. Add `show_pip`/`dismiss_pip` to its exclusion list so they don't double-dispatch:

```javascript
connection.addEventListener('message', (e) => {
    const msg = e.detail;
    if (msg.type
        && !msg.type.startsWith('load_')
        && msg.type !== 'play_animation'
        && msg.type !== 'start_lip_sync'
        && msg.type !== 'stop_lip_sync'
        && msg.type !== 'assistant_message'
        && msg.type !== 'show_pip'
        && msg.type !== 'dismiss_pip') {
        incarnation.handleCommand(msg.type, withResolvedUrl(msg.payload || {}));
    }
});
```

- [ ] **Step 4: Verify build + existing frontend tests pass**

Run: `cd /home/bell/repo/ai_life/playAIdes/incarnation && npm run build && npm test`
Expected: build succeeds; `vitest run` shows all suites green (incl. the new `pipOverlay.test.js`).

- [ ] **Step 5: Commit**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add incarnation/src/viewer.js
git commit -m "feat(viewer): wire show_pip/dismiss_pip to PipOverlay

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: End-to-end verification

**Files:** none (manual + suite run).

- [ ] **Step 1: Add a demo skill + trigger to Silver**

Edit `personas/silver/persona.json` — add (use a reachable test image/MJPEG URL on your LAN; an HA `camera_proxy` URL works if you paste a tokenized one):

```json
  "skills": ["show_pip", "dismiss_pip"],
  "triggers": [
    { "on": { "phrase": "show the front door" },
      "do": { "skill": "show_pip", "params": { "url": "http://192.168.0.7:8123/local/test.jpg", "kind": "snapshot" } } },
    { "on": { "phrase": "dismiss that" },
      "do": { "skill": "dismiss_pip" } }
  ]
```

- [ ] **Step 2: Run the full backend + frontend suites**

Run: `cd /home/bell/repo/ai_life/playAIdes && bin/test ; cd incarnation && bin/../? `
Concretely: `cd /home/bell/repo/ai_life/playAIdes && python -m pytest tests/ -q` and `cd /home/bell/repo/ai_life/playAIdes/incarnation && npm test`.
Expected: backend unit tests green (the six new files); frontend green (incl. `pipOverlay.test.js`). Note: pre-existing Python suite areas that were red before this work (e.g. voicebox test-image) remain out of scope — confirm no *new* failures.

- [ ] **Step 3: Manual smoke (dev server + a TV/browser)**

1. Start the backend + Vite dev server; open `http://192.168.0.7:5173/?persona=silver&kiosk=1`.
2. Wake Silver, say **"show the front door"** → the PiP panel appears top-right with the image; the utterance does **not** produce an LLM reply.
3. Say **"dismiss that"** → the panel fades out.
4. Confirm the panel coexists with the subtitle band (no overlap/clipping) and is inside the TV title-safe area.

- [ ] **Step 4: Commit the demo persona config (optional)**

```bash
cd /home/bell/repo/ai_life/playAIdes
git add personas/silver/persona.json
git commit -m "chore(persona): add demo show_pip trigger to Silver

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Spec coverage map (self-review)

| Spec section | Covered by |
|---|---|
| §3.1 `Skill`/`SkillContext`/`SkillResult` | Task 2 |
| §3.3 registry (internal) | Task 3, Task 7 |
| §3.4 trigger model (phrase) | Task 1 (`Trigger`), Task 5 |
| §3.5 deterministic router (voice path) + precedence | Task 5, Task 8 |
| §3.7 dispatch + `SkillContext` wiring | Task 6 (`speak`), Task 7 |
| §3.8 persona `skills`/`triggers` | Task 1 |
| §3.10 PiP overlay + skills | Task 4 (skills), Tasks 9–11 (frontend) |
| §6 error handling (unknown/bad-params no-op) | Task 7 |
| §7 testing (pure matchers, fake ctx, frontend pure fn) | Tasks 1–9 |

**Deferred (not in this plan, by design):** `bash`/`http`/provider kinds, global `skills/` loader (Plan 2); `POST /api/event` + event router (Plan 2); `brain_model` (Plan 3); captions mode (Plan 3); HA-entity→`camera_proxy` URL resolution (Plan 2).

**Self-review notes:** No placeholders. Type/name consistency checked across tasks — `match_phrase_trigger(text, triggers, enabled_skills) → (skill_name, params)|None`; `SkillContext(persona, target_id, send, speak_fn)` with `send_display`/`speak`; `ShowPipSkill.Params(url, kind, dismiss, announce)`; WS messages `show_pip {url,kind,dismiss}` / `dismiss_pip {}`; frontend `pipViewFromMessage(type, payload) → {visible,url,kind}` consumed by `PipOverlay.apply`. One executor caveat flagged inline: `skills/__init__.py` imports `SkillRegistry` (Task 3), so create Task 3 (or a stub) alongside Task 2.
