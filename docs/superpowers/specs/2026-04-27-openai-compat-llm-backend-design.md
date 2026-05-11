# OpenAI-Compatible LLM Backend — Design Spec

**Date:** 2026-04-27
**Branch:** TBD (suggested: `openai_compat_llm`)
**Status:** ready for implementation planning
**Scope:** Replace the Ollama-native `OllamaLLM` client with a single `OpenAICompatLLM` client that talks to any OpenAI-compatible `/v1/chat/completions` endpoint. Switching backends (Ollama, llamacpp-wrapper, vLLM, OpenAI itself, etc.) becomes a `.env` change.

---

## 1. Goals, scope, non-goals

### What this is

The user runs a `llamacpp-wrapper` service alongside Ollama and wants the project to be able to talk to either backend. Both backends speak OpenAI-compatible HTTP at `/v1/chat/completions`. By converging on that one shape, the project gets:

- A single LLM client class instead of two parallel ones
- Backend choice as a deployment / config decision, not a code decision
- Free compatibility with anything else OpenAI-shaped (vLLM, LM Studio, OpenAI itself, Together AI, Groq, OpenRouter)

The project's two existing LLM call sites (primary `chat()` and HA-rephrase branch in `playAIdes.py`) stay **literally unchanged** — they keep calling `self.llm.chat(messages, system_prompt)`. The class behind `self.llm` swaps from `OllamaLLM` to `OpenAICompatLLM`. Internally, that class hits `/v1/chat/completions` instead of Ollama's native `/api/chat`. Ollama serves both endpoints identically; the live tests against real Ollama keep passing.

### Why not "two parallel classes" (the original brief)

The user's original task brief asked for `OllamaLLM` to stay untouched and a new `LlamaCppWrapperLLM` added beside it. We pivoted because:

1. **Ollama itself speaks OpenAI-compat.** It exposes `/v1/chat/completions` since 0.1.30 (late 2023). So one OpenAI-compat client serves both backends — no two-class duplication needed.
2. **Zero functional loss.** The project doesn't use any Ollama-native features missing from OpenAI-compat (verified by survey — see § 2.1 of `model_interfaces.py`'s historical state). No embeddings, no model-listing, no vision, no `format: json`, no `keep_alive` — none of it is in current code.
3. **Higher-layer code becomes truly backend-agnostic.** Per-call-site routing knobs would leak backend awareness into application code; a single `self.llm` keeps PlayAIdes innocent of the backend choice.
4. **Smaller diff.** ~30 lines of meaningful change vs ~80-100 for the parallel-classes route.

The "don't modify the existing Ollama integration" constraint is interpreted as "don't break Ollama" rather than "don't touch the file." Ollama deployments keep working — they just hit the `/v1` route under the hood.

### Non-goals (this spec)

- **No per-workload routing.** Both call sites currently want the same backend. No `LLM_CHAT_BACKEND` / `LLM_REPHRASE_BACKEND` knobs, no `_llm_for(workload)` indirection, no router class. If a future workload (e.g. embeddings) needs a different backend, that's a new `self.embeddings_llm` slot at that time — additive, not architectural.
- **No streaming.** No current call site needs it. Adding streaming later means a new `chat_stream()` method on `LLMInterface`.
- **No embeddings or vision.** No current call sites. Future work, future spec.
- **No auto-detection / failover.** Backend choice is explicit `.env` config. No probing at startup, no fallback.
- **No backwards-compat aliases for `OLLAMA_URL` / `OLLAMA_MODEL`.** Clean rename, documented in README + commit message. Solo project, simpler is better.
- **No per-request backend kwarg on `chat()`.** Application is agnostic; deployment picks the backend.
- **No API-key / auth header handling.** Local network only for v1. If pointing at OpenAI itself becomes a real use case, add an optional `LLM_API_KEY` env var then.

### Tech stack

Same as today — Python 3.12, `requests` for HTTP, the existing `LLMInterface` ABC. No new dependencies.

---

## 2. Architecture overview

```
   PlayAIdes.chat()                  HA rephrase branch
        │                                    │
        └────────────┬───────────────────────┘
                     ▼
                 self.llm.chat(messages, system_prompt)   ← unchanged
                     │
                     ▼
         ┌────────────────────────┐
         │  OpenAICompatLLM       │   single class, ~40 lines
         │                        │
         │  POST {LLM_URL}/chat/  │
         │       completions      │
         └───────────┬────────────┘
                     │
              .env LLM_URL points at:
                     │
       ┌─────────────┼─────────────────────────┐
       ▼             ▼                         ▼
   Ollama        llamacpp-wrapper        future backends
   :11434/v1    :8081/v1                (vLLM, LM Studio,
                                         OpenAI, etc.)
```

**Key invariants:**

- `LLMInterface` ABC unchanged — same `chat(messages, system_prompt) -> str` contract.
- `MockLLM` for tests unchanged — it doesn't care about HTTP shape; all unit/integration tests using `MockLLM` (every test in `tests/unit/` and `tests/integration/` that touches PlayAIdes) need zero changes.
- `LLMError` exception class unchanged.
- The two `chat()` call sites in `playAIdes.py` (lines 779, 789) are unchanged.
- The HA integration code (`ha_client.py`, persona schema, etc.) is unchanged — agnostic of LLM backend.
- The frontend, TTS, Whisper services are unchanged.
- Backend choice = `.env` change.

---

## 3. Components

Eleven units. One real refactor (`model_interfaces.py`); the rest are mechanical config + import updates.

### 3.1 `model_interfaces.py` — the actual refactor

Three changes:

1. Rename `OllamaLLM` → `OpenAICompatLLM`.
2. Rewrite `chat()` to use OpenAI-compat shape (`POST {base_url}/chat/completions`, parse `choices[0].message.content`).
3. Add `timeout=120.0` constructor default so first-hit cold starts (~25-30s on llamacpp Q4) don't time out.

Concrete shape:

```python
class OpenAICompatLLM(LLMInterface):
    def __init__(self, base_url=None, model=None, timeout=120.0):
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

`LLMInterface`, `LLMError`, `MockLLM` — all unchanged. Total file size after refactor: roughly the same as today.

### 3.2 `playAIdes.py` — one-line import + one-line construction update

```python
# Line 3 today:   from model_interfaces import LLMInterface, OllamaLLM
# Becomes:        from model_interfaces import LLMInterface, OpenAICompatLLM

# Line 99 today:  self.llm: Optional[LLMInterface] = args.llm if args.llm else OllamaLLM()
# Becomes:        self.llm: Optional[LLMInterface] = args.llm if args.llm else OpenAICompatLLM()
```

Two `chat()` call sites at lines 779 and 789 are **unchanged**.

### 3.3 `main.py` — clean up stale import

Line 5 currently imports `OllamaLLM` but never uses it. Delete the import (it's dead code; the default `OllamaLLM()` was always constructed inside `PlayAIdes.__init__`). Documented in commit message.

### 3.4 `docker-compose.yml` — env var rename

```yaml
# Today:
- OLLAMA_URL=http://host.docker.internal:11434
- OLLAMA_MODEL=${OLLAMA_MODEL:-gemma3:4b}

# Becomes:
- LLM_URL=${LLM_URL:-http://host.docker.internal:11434/v1}
- LLM_MODEL=${LLM_MODEL:-gemma3:4b}
```

`${LLM_URL:-...}` form passes through from host shell / `.env` if set, else uses the default. This lets the user point at llamacpp-wrapper purely via `.env` without editing compose.

### 3.5 `docker-compose.test.yml` — env var rename

```yaml
# Today: - OLLAMA_URL=
# Becomes: - LLM_URL=
```

Empty value still disables LLM access for offline test runs — same semantics, new name.

### 3.6 `docker-compose.live.yml` — env var rename in the `tests` service

```yaml
# Today (in tests service):
- OLLAMA_URL=http://ollama:11434
- OLLAMA_MODEL=${OLLAMA_MODEL:-gemma3:4b}

# Becomes:
- LLM_URL=http://ollama:11434/v1
- LLM_MODEL=${LLM_MODEL:-gemma3:4b}
```

The `ollama-model-pull` sidecar still uses `OLLAMA_MODEL` for its own `ollama pull` CLI invocation (Ollama-CLI flag, not playAIdes config) — leave that alone.

### 3.7 `.env.example` — rename + document llamacpp option

Replace the existing `OLLAMA_MODEL=gemma3:4b` line with a documented LLM section:

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

### 3.8 `tests/conftest.py` — fixture rename

The existing `ollama_url` session fixture (line 163) reads `OLLAMA_URL` and skips live tests if unreachable. Rename to `llm_url`, read `LLM_URL`:

```python
@pytest.fixture(scope="session")
def llm_url() -> str:
    url = os.environ.get("LLM_URL", "")
    if not url or not _endpoint_reachable(url):
        pytest.skip(f"LLM_URL not reachable: {url!r}")
    return url
```

### 3.9 Live tests — class + fixture rename

`tests/live/test_ollama_live.py` and `tests/live/test_chat_end_to_end.py` both construct `OllamaLLM(base_url=..., model=...)` directly. Become `OpenAICompatLLM(base_url=..., model=...)`. Same constructor signature, just import + class name change.

The test filename `test_ollama_live.py` stays — it still tests against the Ollama service in `docker-compose.live.yml`. The class change is the only diff inside.

`bin/test-live` script untouched.

### 3.10 `README.md` — Running section updates + backend-switching docs

Two edits:

1. Replace `OLLAMA_URL` / `OLLAMA_MODEL` references with `LLM_URL` / `LLM_MODEL`.
2. Add a small subsection documenting backend selection:

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

See `.env.example` for more options.
```

### 3.11 Memory + commit cross-references

After the work merges, add a memory pointer for "LLM backend agnostic" so future sessions know the abstraction is OpenAI-compat (not Ollama-native). The HA integration spec (`docs/superpowers/specs/2026-04-26-ha-integration-design.md`) mentions `OllamaLLM` as historical context — leave it unchanged.

### Files NOT touched

- HA integration code (`ha_client.py`, `match_keywords.py`, persona schema)
- Frontend (`incarnation/`)
- TTS / Whisper services
- All unit + integration tests using `MockLLM`
- `Dockerfile.backend` (no LLM-related env vars)
- `docs/superpowers/specs/2026-04-26-ha-integration-design.md` (historical)

### Effort estimate

~½ day end-to-end. The refactor is ~15 lines of meaningful code change. Everything else is rename-and-update across 8-10 small files.

---

## 4. Operational notes

Things the implementer / future readers should know when running this against the real backends.

### 4.1 Cold start

First request to a llamacpp-wrapper model takes ~25-30s (Q4) or ~5-8s (Q8) while llama-swap spawns the llama-server child. `timeout=120.0` default in `OpenAICompatLLM.__init__` covers this comfortably. Subsequent requests are sub-second.

Ollama is fast on cold start (model already loaded by the daemon) — the 120s timeout is harmless slack.

### 4.2 Idle eviction (llamacpp-wrapper only)

The wrapper unloads models after the entry's `ttl` (currently 600s). If a session is paused for >10 minutes, the next request pays cold-start again. This is a wrapper-side config, not anything the project handles.

### 4.3 Gemma 4 reasoning mode

Gemma 4 models may emit thinking tokens in `choices[0].message.reasoning_content` instead of (or in addition to) `.content`. The implementation in §3.1 reads `content` first, falls back to `reasoning_content` with a warning log. If both are present, `content` wins (it's the post-reasoning answer).

If you see frequent fallback warnings, bump `max_tokens` in the request payload so the model has room to finish reasoning + answer. Not a parameter today; can be added later if it becomes a problem.

### 4.4 Q8 concurrency cap (llamacpp-wrapper only)

`gemma4-26b-q8` will hard-crash if two requests hit it simultaneously (known llama.cpp `--n-cpu-moe` race). The single-LLM design naturally serializes — `PlayAIdes.chat()` is synchronous and only one call-in-flight per process. As long as you don't run multiple concurrent backend processes against Q8, you're fine.

If you ever need true concurrency on llamacpp-wrapper, use Q4 (verified ~2× aggregate throughput at `--parallel 2`) or fall back to Ollama.

### 4.5 Streaming / parallelism / embeddings / vision

None of these are wired today. When they're needed, they're additive — new methods on `LLMInterface`, new `self.embeddings_llm` slot, etc. The OpenAI-compat shape supports all of them via the same `/v1/...` URL family.

### 4.6 API key / auth (future, if needed)

No auth header today. If pointing at OpenAI itself or a hosted provider becomes a real use case, add an optional `LLM_API_KEY` env var and an `Authorization: Bearer ${LLM_API_KEY}` header in `OpenAICompatLLM.chat()`. Few lines of code, no architecture impact.

---

## 5. Migration

Existing deployments (Ollama on host) need a one-line `.env` update:

```bash
# OLD                              # NEW
OLLAMA_URL=...                     LLM_URL=http://...:11434/v1   # add /v1
OLLAMA_MODEL=...                   LLM_MODEL=...                  # rename
```

Note the `/v1` suffix — Ollama serves both `/api/chat` (native) and `/v1/chat/completions` (OpenAI-compat); after the rename, the project hits the `/v1` path so the URL needs the `/v1` suffix.

Document this in:
- `README.md` (the new Switching LLM backends subsection makes the format obvious)
- `.env.example` (the new file shows the format; existing users `cp` and adapt)
- The merge commit message (one-line migration note)

No code-side backwards compat for `OLLAMA_URL` / `OLLAMA_MODEL`. Solo project; acceptable to rename cleanly.

---

## 6. Out of scope (deferred to future specs)

These are intentionally not part of this spec. Pick up later if a real use case emerges.

- **Per-workload routing** — both call sites currently want the same backend. If a future call site (e.g. an embedding lookup, a structured-output extraction) wants a different backend, add a new `self.<workload>_llm` slot and a new `<WORKLOAD>_LLM_URL` env var at that time. Don't pre-build it.
- **Streaming responses** — adding `chat_stream()` to `LLMInterface` later is a small additive change. No call site needs it today.
- **Embeddings** — when added, will be a new `EmbeddingsInterface` ABC + `OpenAICompatEmbeddings` class + new env var pair (`EMBEDDINGS_URL`, `EMBEDDINGS_MODEL`). No impact on this spec.
- **Vision / multimodal** — same shape as embeddings: separate interface, separate env vars when needed.
- **API-key auth** — optional `LLM_API_KEY` header injection. ~3 lines when needed.
- **Request retry / failover** — explicit no. If `LLM_URL` is wrong or unreachable, raise `LLMError` and let the caller deal.
- **Auto-detection of backend at startup** — explicit no. Backend is `.env` config.
- **Tool-calling support in `LLMInterface`** — the HA integration spec deferred this; still deferred.
- **Backwards-compat alias for `OLLAMA_URL` / `OLLAMA_MODEL`** — solo project, clean rename.

---

## 7. Free-text notes (append over time)

Use this section to capture stray thoughts about future LLM-related work. Notes here persist in git and survive session resets.

(Empty — add as ideas arise.)
