# OpenAI-Compatible LLM Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `OllamaLLM` (Ollama-native `/api/chat`) with `OpenAICompatLLM` (any OpenAI-compatible `/v1/chat/completions` endpoint). Switching backends — Ollama, llamacpp-wrapper, vLLM, OpenAI itself, etc. — becomes a `.env` change.

**Architecture:** A single `OpenAICompatLLM(LLMInterface)` class talks to whatever URL `LLM_URL` points at. PlayAIdes call sites stay literally unchanged (`self.llm.chat(...)`). Renames `OLLAMA_URL`/`OLLAMA_MODEL` env vars to `LLM_URL`/`LLM_MODEL` cleanly (no backwards-compat aliases — solo project).

**Tech Stack:** Python 3.12 / `requests` for HTTP / `responses>=0.25` for unit-test HTTP mocking (already a dev dep). No new dependencies.

**Spec:** [docs/superpowers/specs/2026-04-27-openai-compat-llm-backend-design.md](../specs/2026-04-27-openai-compat-llm-backend-design.md)

**Branch:** create `openai_compat_llm` from `main` (no worktrees per project preference). Current `main` tip is `430af42` (`spec: OpenAI-compat LLM backend`) — verify with `git log --oneline -1`.

## Conventions for this plan

- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.
- Backend uses TDD via `bin/test` (Dockerized — do not call `pytest` directly on the host).
- Each task ends with a commit. Conventional Commits prefixes (`feat:`, `refactor:`, `chore:`, `docs:`, `test:`).
- The atomic rename refactor (Task 2) touches several files at once — that's intentional. Splitting it would create broken intermediate states. Live tests (`bin/test-live`) will be exercised manually in Task 5; the unit + integration suite via `bin/test` remains green between every task.

## Baseline going in

- Branch: `main` at HEAD = `430af42` — verify with `git log --oneline -1`.
- `bin/test` → 174 passed, 4 deselected.
- `bin/test-js` → 89 passed.

## File structure

| File | Status | Responsibility |
|---|---|---|
| `tests/unit/test_openai_compat_llm.py` | **Create** | Unit tests for the new HTTP shape + reasoning_content fallback (mocked with `responses`) |
| `model_interfaces.py` | Modify | Rename `OllamaLLM` → `OpenAICompatLLM`, switch to `/v1/chat/completions`, add reasoning_content fallback, bump default timeout to 120s |
| `playAIdes.py` | Modify | Import + construction line — two single-line edits |
| `main.py` | Modify | Delete the stale `OllamaLLM` import (it's never used) |
| `tests/conftest.py` | Modify | Rename `ollama_url` session fixture to `llm_url`, update env-var read |
| `tests/live/test_ollama_live.py` | Modify | Update import + class name + fixture reference |
| `tests/live/test_chat_end_to_end.py` | Modify | Same — import + class + fixture |
| `docker-compose.yml` | Modify | `OLLAMA_URL` → `LLM_URL` (with `/v1` suffix), `OLLAMA_MODEL` → `LLM_MODEL` |
| `docker-compose.test.yml` | Modify | `OLLAMA_URL=` → `LLM_URL=` (still empty — disables LLM access for offline tests) |
| `docker-compose.live.yml` | Modify | Same rename in the `tests` service env block (leave `ollama-model-pull` sidecar's `OLLAMA_MODEL` — it's an Ollama-CLI flag, not playAIdes config) |
| `.env.example` | Modify | Replace `OLLAMA_MODEL` line with documented `LLM_URL` / `LLM_MODEL` block plus llamacpp examples |
| `README.md` | Modify | Update env-var references in the Running section + add a "Switching LLM backends" subsection |

---

## Task 0: Branch creation + baseline verification

**Files:** none (git only).

- [ ] **Step 1: Verify baseline + create branch**

```bash
cd /home/bell/repo/ai_life/playAIdes
git log --oneline -1                     # expect: 430af42 spec: OpenAI-compat LLM backend ...
git checkout -b openai_compat_llm main
bin/test 2>&1 | grep -E "^==.*passed" | tail -1   # expect: 174 passed, 4 deselected
```

If the baseline doesn't match, STOP and report.

---

## Task 1: TDD — failing unit tests for `OpenAICompatLLM`

**Files:**
- Create: `tests/unit/test_openai_compat_llm.py`

The new behaviors to lock in: OpenAI-compat HTTP shape, response parsing of `choices[0].message.content`, reasoning_content fallback for Gemma 4, error handling. The existing `OllamaLLM` has no unit tests; we're adding them as part of the new class.

- [ ] **Step 1: Create the failing tests**

Create `tests/unit/test_openai_compat_llm.py`:

```python
"""Unit tests for OpenAICompatLLM (HTTP mocked with `responses`)."""
import pytest
import responses
from model_interfaces import OpenAICompatLLM, LLMError


BASE_URL = "http://llm.test/v1"


@responses.activate
def test_chat_returns_message_content_on_success():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={
            "choices": [
                {"message": {"role": "assistant", "content": "Hello there"}}
            ]
        },
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="test-model")
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result == "Hello there"


@responses.activate
def test_chat_prepends_system_prompt_when_provided():
    captured = {}

    def callback(request):
        import json as _json
        captured["body"] = _json.loads(request.body)
        return (200, {}, '{"choices":[{"message":{"role":"assistant","content":"ok"}}]}')

    responses.add_callback(
        responses.POST, f"{BASE_URL}/chat/completions", callback=callback,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="test-model")
    llm.chat(
        [{"role": "user", "content": "hi"}],
        system_prompt="You are helpful.",
    )
    msgs = captured["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": "You are helpful."}
    assert msgs[1] == {"role": "user", "content": "hi"}
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["stream"] is False


@responses.activate
def test_chat_falls_back_to_reasoning_content_when_content_empty():
    """Gemma 4 may put thinking tokens in reasoning_content with empty content."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={
            "choices": [
                {"message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "Let me think about this...",
                }}
            ]
        },
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result == "Let me think about this..."


@responses.activate
def test_chat_prefers_content_over_reasoning_content_when_both_present():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={
            "choices": [
                {"message": {
                    "role": "assistant",
                    "content": "The answer is 42",
                    "reasoning_content": "Let me think...",
                }}
            ]
        },
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    assert llm.chat([{"role": "user", "content": "hi"}]) == "The answer is 42"


@responses.activate
def test_chat_returns_empty_string_when_both_fields_empty():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={"choices": [{"message": {"role": "assistant", "content": ""}}]},
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    assert llm.chat([{"role": "user", "content": "hi"}]) == ""


@responses.activate
def test_chat_raises_llmerror_on_http_500():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={"error": "internal"}, status=500,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


@responses.activate
def test_chat_raises_llmerror_on_connection_error():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        body=ConnectionError("simulated"),
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m", timeout=1.0)
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


@responses.activate
def test_chat_raises_llmerror_on_non_json_response():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        body="not json", status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_constructor_strips_trailing_slash_from_base_url():
    llm = OpenAICompatLLM(base_url=f"{BASE_URL}/", model="m")
    assert llm.base_url == BASE_URL


def test_constructor_reads_env_vars_when_args_omitted(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://from-env.test/v1")
    monkeypatch.setenv("LLM_MODEL", "from-env-model")
    llm = OpenAICompatLLM()
    assert llm.base_url == "http://from-env.test/v1"
    assert llm.model == "from-env-model"


def test_constructor_uses_defaults_when_no_args_no_env(monkeypatch):
    monkeypatch.delenv("LLM_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = OpenAICompatLLM()
    assert llm.base_url == "http://localhost:11434/v1"
    assert llm.model == "gemma3:4b"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
bin/test pytest tests/unit/test_openai_compat_llm.py 2>&1 | grep -E "FAILED|ImportError|ModuleNotFoundError|collected" | head
```

Expected: `ImportError: cannot import name 'OpenAICompatLLM' from 'model_interfaces'` (collection error on all 11 tests).

- [ ] **Step 3: Commit (failing tests committed first per TDD discipline)**

```bash
git add tests/unit/test_openai_compat_llm.py
git commit -m "test: failing unit tests for OpenAICompatLLM (TDD pre-refactor)"
```

---

## Task 2: Atomic refactor — rename + new HTTP shape + consumer updates

**Files:**
- Modify: `model_interfaces.py` (the meat — rename + new HTTP shape + reasoning_content fallback)
- Modify: `playAIdes.py` (line 3 import + line 99 construction)
- Modify: `main.py` (delete stale `OllamaLLM` import on line 5)
- Modify: `tests/conftest.py` (rename `ollama_url` fixture → `llm_url`, read `LLM_URL` env)
- Modify: `tests/live/test_ollama_live.py` (import + class + fixture references)
- Modify: `tests/live/test_chat_end_to_end.py` (import + class + fixture references)

The renames must happen in one atomic commit — splitting them creates a broken intermediate state where `playAIdes.py` imports a class that no longer exists.

- [ ] **Step 1: Refactor `model_interfaces.py`**

Open `model_interfaces.py`. Replace the entire `OllamaLLM` class (lines 28-63) with `OpenAICompatLLM`:

```python
class OpenAICompatLLM(LLMInterface):
    """OpenAI-compatible chat completions client.

    Talks to any /v1/chat/completions endpoint — Ollama (which serves
    OpenAI-compat at /v1 since 0.1.30), llamacpp-wrapper, vLLM, OpenAI
    itself, etc. Backend choice is a deployment decision: set LLM_URL
    to the right /v1 base URL.

    Default timeout is 120s to cover llamacpp-wrapper cold-start
    (~25-30s for Q4 models when llama-swap spawns the llama-server
    child). Harmless slack for warm Ollama.
    """
    def __init__(self, base_url=None, model=None, timeout=120.0):
        import os
        self.base_url = (
            base_url or os.environ.get("LLM_URL", "http://localhost:11434/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "gemma3:4b")
        self.timeout = timeout

    def chat(self, messages, system_prompt=None) -> str:
        url = f"{self.base_url}/chat/completions"
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        payload = {"model": self.model, "messages": msgs, "stream": False}
        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.error("Error communicating with LLM at %s: %s", url, e)
            raise LLMError(f"LLM request failed: {e}") from e
        except ValueError as e:
            logger.error("Malformed JSON from LLM: %s", e)
            raise LLMError(f"LLM returned non-JSON response: {e}") from e
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        if content:
            return content
        # Gemma 4 may put thinking tokens in reasoning_content when content
        # is empty (e.g. truncated mid-reasoning). Surface that rather than
        # returning an empty string.
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            logger.warning(
                "LLM returned only reasoning_content; using as fallback"
            )
            return reasoning
        return ""
```

The `LLMInterface`, `LLMError`, `MockLLM` classes stay unchanged. The top-of-file imports stay unchanged (`requests` is already imported).

- [ ] **Step 2: Update `playAIdes.py`**

Two single-line edits:

```python
# Line 3 — change the import:
# Before:  from model_interfaces import LLMInterface, OllamaLLM
# After:   from model_interfaces import LLMInterface, OpenAICompatLLM
```

```python
# Line 99 — change the construction:
# Before:  self.llm: Optional[LLMInterface] = args.llm if args.llm else OllamaLLM() # Default to Ollama
# After:   self.llm: Optional[LLMInterface] = args.llm if args.llm else OpenAICompatLLM() # Default to LLM_URL (Ollama by default)
```

The two `chat()` call sites at lines 779 and 789 are **unchanged**.

- [ ] **Step 3: Clean up `main.py`**

Open `main.py`. Line 5 currently reads:

```python
from model_interfaces import OllamaLLM
```

Delete that line entirely. (It's never used — `PlayAIdesArgs` is constructed without `llm=` and the default `OllamaLLM()` was always built inside `PlayAIdes.__init__`.)

- [ ] **Step 4: Rename the `ollama_url` fixture in `tests/conftest.py`**

Find the `ollama_url` session fixture (around line 163). Rename to `llm_url` and read `LLM_URL`:

```python
@pytest.fixture(scope="session")
def llm_url() -> str:
    """Skip live tests if LLM_URL isn't reachable."""
    url = os.environ.get("LLM_URL", "")
    if not url or not _endpoint_reachable(url):
        pytest.skip(f"LLM_URL not reachable: {url!r}")
    return url
```

(The `_endpoint_reachable` helper just below it stays unchanged.)

- [ ] **Step 5: Update `tests/live/test_ollama_live.py`**

Open the file. Two changes:

```python
# Replace the import:
# Before:  from model_interfaces import OllamaLLM
# After:   from model_interfaces import OpenAICompatLLM
```

Find every `ollama_url` parameter in test function signatures and rename to `llm_url`. Find every `OllamaLLM(...)` constructor and rename to `OpenAICompatLLM(...)`. Same constructor signature, just the class name changes.

Per the survey, the only construction is at line 19. Final shape:

```python
def test_xxx(llm_url):
    llm = OpenAICompatLLM(base_url=llm_url, model=os.environ.get("LLM_MODEL", "gemma3:4b"))
    # ... rest of test ...
```

(Update the env-var read inside the test from `OLLAMA_MODEL` to `LLM_MODEL` too.)

- [ ] **Step 6: Update `tests/live/test_chat_end_to_end.py`**

Same pattern: import + class name + fixture name + env var name. Per the survey, line 25 has the construction. Match the shape from Step 5.

- [ ] **Step 7: Run unit + integration tests to verify nothing regressed**

```bash
bin/test 2>&1 | grep -E "^==.*passed" | tail -1
```

Expected: `185 passed, 4 deselected, 2 warnings` — the existing 174 passed + the 11 new OpenAICompatLLM unit tests from Task 1 = 185.

(Live tests are not exercised by `bin/test`; they run via `bin/test-live` which needs the live stack. Live verification is in Task 5.)

- [ ] **Step 8: Commit**

```bash
git add model_interfaces.py playAIdes.py main.py \
        tests/conftest.py \
        tests/live/test_ollama_live.py tests/live/test_chat_end_to_end.py
git commit -m "refactor: OllamaLLM → OpenAICompatLLM (OpenAI-compat /v1/chat/completions)

Single LLM client class hits any OpenAI-compatible endpoint. Ollama
serves /v1 too (since 0.1.30), so existing Ollama deployments work
unchanged after the .env URL gets a /v1 suffix.

- model_interfaces.py: rewrite chat() body, add reasoning_content fallback
  for Gemma 4, bump default timeout to 120s for llamacpp cold-start
- playAIdes.py: 2-line import/construction update; call sites unchanged
- main.py: delete stale OllamaLLM import (was never used)
- tests/conftest.py: ollama_url fixture → llm_url, reads LLM_URL env
- tests/live/*.py: update imports + class name + fixture references"
```

---

## Task 3: Rename env vars across docker compose files + `.env.example`

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.test.yml`
- Modify: `docker-compose.live.yml`
- Modify: `.env.example`

The code now reads `LLM_URL` / `LLM_MODEL`. The compose files still pass `OLLAMA_URL` / `OLLAMA_MODEL`. Until this task lands, the runtime stack would be using the code's defaults instead of compose values. Tests are unaffected (`bin/test` uses MockLLM throughout).

- [ ] **Step 1: Update `docker-compose.yml`**

In the `backend` service's `environment:` block (around lines 24 and 34), replace the two Ollama env-var lines:

```yaml
# Before:
- OLLAMA_URL=http://host.docker.internal:11434
- OLLAMA_MODEL=${OLLAMA_MODEL:-gemma3:4b}

# After:
- LLM_URL=${LLM_URL:-http://host.docker.internal:11434/v1}
- LLM_MODEL=${LLM_MODEL:-gemma3:4b}
```

Note the **`/v1` suffix** on the URL — Ollama serves OpenAI-compat at that path. The `${LLM_URL:-...}` form lets the user override via `.env` without editing compose.

- [ ] **Step 2: Update `docker-compose.test.yml`**

Find the existing `OLLAMA_URL=` line (around line 24) and rename:

```yaml
# Before: - OLLAMA_URL=
# After:  - LLM_URL=
```

Empty value still disables LLM access for offline tests — same semantics, new name.

- [ ] **Step 3: Update `docker-compose.live.yml`**

In the `tests` service's `environment:` block, rename two lines:

```yaml
# Before:
- OLLAMA_URL=http://ollama:11434
- OLLAMA_MODEL=${OLLAMA_MODEL:-gemma3:4b}

# After:
- LLM_URL=http://ollama:11434/v1
- LLM_MODEL=${LLM_MODEL:-gemma3:4b}
```

**Leave the `ollama-model-pull` sidecar alone.** Its `OLLAMA_MODEL` env var feeds an `ollama pull "$OLLAMA_MODEL"` shell command — that's an Ollama-CLI flag, not playAIdes config.

- [ ] **Step 4: Update `.env.example`**

Replace the existing OLLAMA_MODEL section with a documented LLM block. The current block (around line 14-19):

```bash
# ─ Ollama (external — not in docker compose) ─────────────────────────────
# Backend reaches Ollama via http://host.docker.internal:11434
# (configured in docker-compose.yml, not here). Only override OLLAMA_MODEL
# below if you want a different model than the default.
OLLAMA_MODEL=gemma3:4b
```

Becomes:

```bash
# ─ LLM backend ──────────────────────────────────────────────────────────
# Any OpenAI-compatible /v1 endpoint works. Defaults below point at host
# Ollama; uncomment a different LLM_URL to switch backends.

LLM_URL=http://host.docker.internal:11434/v1     # host Ollama
LLM_MODEL=gemma3:4b

# Examples (uncomment to use):
# LLM_URL=http://host.docker.internal:8081/v1    # llamacpp-wrapper
# LLM_MODEL=gemma4-26b-q4                         # llamacpp Q4 — daily driver
# LLM_MODEL=gemma4-26b-q8                         # llamacpp Q8 — quality (single-concurrency only)
```

- [ ] **Step 5: Verify `bin/test` still passes** (proves the test compose rename didn't break anything)

```bash
bin/test 2>&1 | grep -E "^==.*passed" | tail -1
```

Expected: `185 passed, 4 deselected`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml docker-compose.test.yml docker-compose.live.yml .env.example
git commit -m "chore: rename OLLAMA_URL/OLLAMA_MODEL env vars to LLM_URL/LLM_MODEL

URL now needs the /v1 suffix because the code uses OpenAI-compat
endpoints. Existing Ollama deployments need a one-line .env update
(URL gets /v1 suffix, OLLAMA_* vars renamed to LLM_*)."
```

---

## Task 4: Update `README.md` — env var rename + backend-switching docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find env var references in the README**

```bash
grep -nE "OLLAMA_URL|OLLAMA_MODEL" README.md || echo "(none — only need to add the new subsection)"
```

The README's "Running" section was added in the docker-compose-consolidation work; verify whether it mentions the old env vars. If it does, update each match to the new names + `/v1` suffix on the URL.

- [ ] **Step 2: Add a "Switching LLM backends" subsection**

Find the "## Running" section, then within it find the "### Runtime stack" subsection. After that subsection (and before "### Tests"), add:

```markdown
### Switching LLM backends

The backend is just a `.env` change. The project doesn't know or care
which OpenAI-compatible API serves it.

```bash
# host Ollama (default)
LLM_URL=http://host.docker.internal:11434/v1
LLM_MODEL=gemma3:4b

# llamacpp-wrapper (better MoE control, faster on supported models)
LLM_URL=http://host.docker.internal:8081/v1
LLM_MODEL=gemma4-26b-q4
```

Then `docker compose down && docker compose up -d` to pick up the change.

See `.env.example` for more options. The backend default timeout is
120s to cover llamacpp-wrapper cold-start (~25-30s on Q4 first hit
while llama-swap spawns the llama-server child).
```

- [ ] **Step 3: Verify nothing else in the README references the old env var names**

```bash
grep -n "OLLAMA_URL\|OLLAMA_MODEL\|OllamaLLM" README.md || echo "(clean)"
```

Expected: `(clean)`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README — document LLM backend switching via LLM_URL .env"
```

---

## Task 5: End-of-pass verification + manual live smoke

**Files:** none (verification only).

- [ ] **Step 1: Final test pass**

```bash
bin/test 2>&1 | grep -E "^==.*passed" | tail -1
bin/test-js 2>&1 | grep -E "Tests " | tail -1
docker ps --filter "ancestor=playaides-tests:latest" -q | wc -l
```

Expected:
- `185 passed, 4 deselected`
- `Tests 89 passed (89)`
- Container count: `0` (or `1` if a slow-exit container is from a previous run — see followup doc; not a regression from this work)

- [ ] **Step 2: Verify branch summary**

```bash
git log --oneline main..openai_compat_llm
```

Expected: 5 commits (Task 1 test-add, Task 2 atomic refactor, Task 3 env rename, Task 4 README, plus any small fixups).

- [ ] **Step 3: No new TODO/FIXME/TBD strings**

```bash
grep -nE "TODO|FIXME|TBD" $(git diff --name-only main..HEAD | grep -E "\\.(py|md|yml|yaml|toml)$") 2>/dev/null \
  | grep -v "Dockerfile" | grep -v "spec\|plan" || echo "(clean)"
```

Expected: `(clean)`.

- [ ] **Step 4: Self-review checklist**

- [ ] All 11 spec § 3 components implemented (3.1 model_interfaces, 3.2 playAIdes, 3.3 main, 3.4-3.6 compose, 3.7 .env.example, 3.8 conftest, 3.9 live tests, 3.10 README, 3.11 deferred to merge).
- [ ] No backwards-compat code for `OLLAMA_URL` / `OLLAMA_MODEL` (clean rename per spec).
- [ ] No per-workload routing knobs introduced (deferred per spec § 6).
- [ ] No streaming, embeddings, vision, auto-detection, or tool-calling (all deferred per spec § 6).
- [ ] `chat()` call sites at `playAIdes.py` lines 779/789 are byte-identical to before.
- [ ] HA integration code untouched (`ha_client.py`, `match_keywords.py`, persona schema).
- [ ] Frontend, TTS, Whisper services untouched.

- [ ] **Step 5: Manual live smoke (user-driven, NOT a subagent task)**

This is for the user to run after subagents finish. It needs Ollama running on the host AND/OR llamacpp-wrapper running on the host. Do NOT have a subagent automate this — it's a live-network test.

Document for the user:

```bash
# With Ollama running on the host (default config — should already work):
docker compose down
docker compose up -d
docker compose logs -f backend     # watch for "Loaded persona: ..."
                                   # then talk to a persona via the viewer

# Switch to llamacpp-wrapper:
# 1. Edit .env:
#    LLM_URL=http://host.docker.internal:8081/v1
#    LLM_MODEL=gemma4-26b-q4
# 2. Restart:
docker compose down
docker compose up -d
# 3. First persona reply will be slow (~25-30s cold start); subsequent replies sub-second.
# 4. If the llamacpp-wrapper logs show the model loading and playAIdes logs show the response,
#    the new code path is working end-to-end.

# Optional: full live test suite if you have a GPU + the live compose setup running:
bin/test-live
```

If anything fails in this manual smoke, file a fix as a separate small task — don't try to fix mid-plan.

- [ ] **Step 6: No commit (process marker)**

---

## Self-review checklist (run before marking implementation done)

- [ ] **Spec coverage**: every section of the spec maps to a Task above.
  - §3.1 (model_interfaces.py refactor) → Task 2 Step 1
  - §3.2 (playAIdes.py) → Task 2 Step 2
  - §3.3 (main.py cleanup) → Task 2 Step 3
  - §3.4 (docker-compose.yml) → Task 3 Step 1
  - §3.5 (docker-compose.test.yml) → Task 3 Step 2
  - §3.6 (docker-compose.live.yml) → Task 3 Step 3
  - §3.7 (.env.example) → Task 3 Step 4
  - §3.8 (conftest.py fixture rename) → Task 2 Step 4
  - §3.9 (live tests) → Task 2 Steps 5-6
  - §3.10 (README) → Task 4
  - §3.11 (memory pointer) → deferred to post-merge (not a code task)
  - Plus: TDD pre-tests for the new behavior (Task 1) and end-of-pass verification (Task 5).
- [ ] **No placeholders**: no TBD/TODO/FIXME in any plan task.
- [ ] **Type / name consistency**: `OpenAICompatLLM`, `LLM_URL`, `LLM_MODEL`, `llm_url` (fixture), `openai_compat_llm` (branch) — same names everywhere they appear.
- [ ] **No silent scope creep**: every task is a fix/feature/refactor that maps directly to a spec component or to TDD discipline.
- [ ] **Backwards compat preserved at the application level**: existing `chat()` call sites unchanged; HA integration untouched; Ollama deployments still work after a one-line `.env` update.
