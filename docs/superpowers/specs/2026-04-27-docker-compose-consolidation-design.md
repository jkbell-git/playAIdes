# Docker Compose Consolidation — Design Spec

**Date:** 2026-04-27
**Branch:** TBD (suggested: `compose_consolidation`)
**Status:** ready for implementation planning
**Scope:** Consolidate the scattered docker-compose configs and host processes into a single `docker compose up` for the runtime stack; replace Make with `bin/` shell scripts for tests; delete the duplicate TTS compose

---

## 1. Goals, scope, non-goals

### What this is

Today, getting a working playAIdes dev environment requires five separate steps across two compose files, one native daemon, and two host processes. The user wants a **single `docker compose up`** that brings up the runtime stack, with one optional external service (Ollama on the host, kept external so a future llama.cpp swap stays cheap). As part of the same cleanup, the project drops the Make abstraction (which is doing very little real work) in favor of `bin/` shell scripts that map directly to `docker compose` invocations.

### Non-goals (this spec)

- **No production mode.** This spec is dev-only — hot-reload everywhere, source bind-mounted, vite dev server. A future household-TV-server deployment with built images / nginx / gunicorn / systemd is a separate project.
- **No Ollama containerization.** The user wants Ollama to remain external so they can swap to llama.cpp (for MoE model support) without touching the docker stack. The compose's `backend` service points at `host.docker.internal:11434` via `extra_hosts`.
- **No test stack folding.** `docker-compose.test.yml` and `docker-compose.live.yml` stay separate from the new top-level `docker-compose.yml`. They have different lifecycle (one-shot pytest, read-only mounts), different volumes, and `bin/test*` targets keep them invocable. Mixing test + runtime in one compose file via profiles adds magic without ergonomic gain.
- **No fixture consolidation, no Docker-or-not architectural debate.** Both remain in the deferred testing-overhaul followup (`docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md`). Only the "Make abstraction" sub-project is pulled forward by this work.

### Tech stack

Docker, Docker Compose v2 (the `docker compose` CLI, not `docker-compose`), `bash` for `bin/` scripts. New Dockerfile bases: `python:3.12-slim` (backend) and `node:22-slim` (frontend) — same bases the project already uses for tests.

### Why now

The HA integration session surfaced two related pains:
1. The user has multiple services to bring up/down separately and wants one command.
2. Make is doing ~80% convention and ~20% real work; the testing-overhaul followup already flagged this.

Doing both at once means no half-state where some commands are Make and some are bare shell.

---

## 2. Architecture overview

```
                                 Host browser  (5173, 8765)
                                       │
            ┌──────────────────────────┼─────────────────────────┐
            ▼                          ▼                         │
       ┌─────────┐                ┌─────────┐                   │
       │frontend │                │ backend │── HA_URL ──────► (HA outside)
       │  Vite   │                │playAIdes│                   │
       │  5173   │                │  :8765  │                   │
       │ (HMR)   │                │(uvicorn │                   │
       │         │                │ --reload)                   │
       └────┬────┘                └────┬────┘                   │
            │                          │                         │
            │ (browser hits both       ├── OLLAMA_URL=          │
            │  via host ports)         │    host.docker.internal:11434  ──► host Ollama
            │                          │                         │           (or future llama.cpp)
            │                          │── TTS_URL=http://tts:8009 ──┐
            │                          │── WHISPER_URL=http://whisper:9000 ┘
            │                          ▼
            │                   ┌──────────────────────┐
            │                   │   internal network   │
            │                   ├──────┬───────────────┤
            │                   ▼      ▼
            │              ┌─────┐  ┌─────────┐
            │              │ tts │  │ whisper │
            │              │8009 │  │  9000   │
            │              │(GPU)│  │         │
            │              └─────┘  └─────────┘
            │                  (no host ports — only
            │                   reachable from `backend`)
            └──────────────────────────────────────────
```

**Containers**: 4 (backend, frontend, tts, whisper). **Host ports**: 5173 (frontend) and 8765 (backend) only. **External**: Ollama on host at `localhost:11434`. **Inter-container**: default bridge network, service-name DNS (`http://tts:8009`).

**Hot-reload everywhere**: backend bind-mounts `./` → `/app` and runs `main.py` under [`watchfiles`](https://watchfiles.helpmanual.io/) (whole-process restart on any `*.py` change — uvicorn's own `--reload` doesn't work in this codebase because the FastAPI app is launched inside a daemon thread by `IncarnationServer`, where uvicorn's reload watcher refuses to run); frontend bind-mounts `./incarnation/` → `/app/incarnation` and runs `vite dev --host 0.0.0.0` (HMR on save).

---

## 3. Components

Eight units of work. Two new Dockerfiles, one new top-level compose, one `.env.example`, eight `bin/` scripts, README updates, two file deletions, one followup-doc edit.

### 3.1 `Dockerfile.backend` *(new, ~25 lines)*

- Base: `python:3.12-slim`
- Install build deps + `pip install --no-cache-dir -r requirements.txt` (or `-e .` if pyproject.toml is the source of truth — confirm during impl). Make sure `watchfiles` is installed (it's already an indirect dep of uvicorn but pin it explicitly so the dev workflow doesn't break if uvicorn's deps change).
- Workdir: `/app`
- Default CMD: `["watchfiles", "--filter", "python", "python main.py --use_avatar", "/app"]` — the watchfiles wrapper restarts `python main.py` whenever any `*.py` file under `/app` changes. Overridable via compose `command:` for one-off scripts (`docker compose run --rm backend python -m foo.bar`).
- **No source COPY** — runtime mounts `./` from host so file changes are visible inside the container immediately, and watchfiles picks them up.

### 3.2 `Dockerfile.frontend` *(new, ~15 lines)*

- Base: `node:22-slim`
- Workdir: `/app/incarnation`
- COPY `package.json` + `package-lock.json`, then `npm ci`
- Default CMD: `["npm", "run", "dev", "--", "--host", "0.0.0.0"]` — the `--host 0.0.0.0` is critical so the container's Vite dev server is reachable from the host browser
- Source bind-mount + named volume for `node_modules` (mirrors the `js-tests` pattern)

### 3.3 `docker-compose.yml` *(new, top-level, ~80 lines)*

```yaml
services:
  backend:
    build: { context: ., dockerfile: Dockerfile.backend }
    image: playaides-backend:latest
    ports: ["8765:8765"]
    volumes: [".:/app:rw"]
    environment:
      - OLLAMA_URL=http://host.docker.internal:11434
      - TTS_URL=http://tts:8009
      - WHISPER_URL=http://whisper:9000
      - PLAYAIDES_API_KEY
      - HA_URL
      - HA_TOKEN
      - HA_DEFAULT_AGENT_ID
      - OLLAMA_MODEL=${OLLAMA_MODEL:-gemma3:4b}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      tts: { condition: service_started }
      whisper: { condition: service_healthy }
    command:
      - watchfiles
      - --filter
      - python
      - python main.py --use_avatar
      - /app

  frontend:
    build: { context: ., dockerfile: Dockerfile.frontend }
    image: playaides-frontend:latest
    ports: ["5173:5173"]
    volumes:
      - ./incarnation:/app/incarnation:rw
      - frontend_node_modules:/app/incarnation/node_modules
    command: ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

  tts:
    build:
      context: ./voice_generation/voice_server
      dockerfile: Dockerfile_streaming_tts
    image: playaides-tts:latest
    volumes:
      - ./voice_generation/voice_server/hf_models:/root/.cache/huggingface
      - ./voice_generation/voice_server/service:/app/Qwen3-TTS-streaming/service
    deploy:
      resources:
        reservations:
          devices: [{ driver: nvidia, capabilities: [gpu] }]

  whisper:
    image: onerahmet/openai-whisper-asr-webservice:latest
    environment:
      - ASR_MODEL=base
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/"]
      interval: 10s
      retries: 5

volumes:
  frontend_node_modules:
```

Network is the implicit default `playaides_default` — no explicit network definition needed; all four containers can reach each other by service name.

### 3.4 `.env.example` *(new, ~10 lines)*

Compose auto-loads `.env` from the working directory. The example is what users `cp .env.example .env` and edit:

```bash
# Required for any HA feature
HA_URL=
HA_TOKEN=
HA_DEFAULT_AGENT_ID=

# Optional
PLAYAIDES_API_KEY=
OLLAMA_MODEL=gemma3:4b
```

Confirm `.env` is in `.gitignore` during implementation (almost certainly already is).

### 3.5 `bin/` shell scripts *(new directory, 8 files)*

Each script is 1-5 lines of bash with `#!/usr/bin/env bash` + `set -euo pipefail`. All are `chmod +x`. Run from repo root as `bin/<name>`.

| Script | Replaces | Behavior |
|---|---|---|
| `bin/test` | `make test`, `make test-unit`, `make test-integration` | `docker compose -f docker-compose.test.yml run --rm tests "$@"` (extra args pass through to pytest) |
| `bin/test-js` | `make test-js` | `docker compose -f docker-compose.test.yml run --rm js-tests` |
| `bin/test-all` | `make test-all` | `bin/test && bin/test-js` |
| `bin/test-live` | `make test-live` | The 4-line live-stack incantation: `up -d ollama tts whisper` → pull model → run `pytest -m live` → `down` |
| `bin/coverage` | `make coverage` | `bin/test` + `cp .test-output/coverage.xml ./coverage.xml` |
| `bin/shell` | `make shell` | `docker compose -f docker-compose.test.yml run --rm --entrypoint /bin/bash tests` |
| `bin/js-shell` | `make js-shell` | Same but for `js-tests` |
| `bin/clean` | `make clean` | All three `docker compose down -v --remove-orphans` calls + `rm -rf .test-output coverage.xml .pytest_cache .coverage` |

Argument pass-through example: `bin/test pytest tests/unit/test_foo.py -k mytest -v` works because of `"$@"`.

### 3.6 Files to delete

- `Makefile` — entirely. Every target is replaced by a `bin/` script or a documented `docker compose` command.
- `docker-compose.dev.yml` — replaced by the new top-level `docker-compose.yml`.
- `voice_generation/voice_server/docker-compose.yml` — duplicate of the `tts` service in the new top-level compose.

### 3.7 `README.md` *(modified)*

Replace the "Running the test suite" section with a new "Running" section covering both runtime and tests:

````markdown
## Running

### Runtime stack (Ollama runs externally)

```bash
ollama serve                   # if not already running on the host
cp .env.example .env           # first time only; edit with your HA_TOKEN etc.
docker compose up -d           # backend + frontend + tts + whisper
docker compose logs -f         # tail all logs
docker compose down            # stop everything
```

Browser at `http://localhost:5173/`. Backend HTTP/WS at `http://localhost:8765/`.

To restart a single service: `docker compose restart backend`.
To bring up only some services: `docker compose up -d backend frontend whisper` (skips TTS — useful when your GPU is busy).

### Tests

```bash
bin/test                       # Python unit + integration
bin/test-js                    # Frontend Vitest
bin/test-all                   # both
bin/test-live                  # full E2E with real Ollama + TTS containers (GPU needed)
bin/shell                      # interactive shell in the test image
bin/clean                      # tear everything down + remove caches
```

`bin/test` passes extra args through to pytest: `bin/test pytest tests/unit -k mytest -v`.

See `bin/` for all scripts; each is a few lines of bash.
````

### 3.8 Update the deferred testing-overhaul followup

Edit `docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md`. The "Make abstraction" sub-project is now resolved by this work — note that inline. The other two sub-projects (fixture consolidation, Docker-or-not architectural question) remain deferred. Memory pointer (`memory/testing_infra_overhaul_deferred.md`) needs no changes; it points at the followup doc which captures the new state.

### Files NOT touched

- `docker-compose.test.yml`, `docker-compose.live.yml` — test stack stays separate.
- `Dockerfile.test`, `Dockerfile.test-js` — test images unchanged.
- `voice_generation/voice_server/Dockerfile_streaming_tts` — referenced by both the new compose and `live.yml`, leave it.
- All Python and JS source.

### Effort estimate

~1 day end-to-end. The 2 Dockerfiles are tiny. The compose file is the meatiest single artifact (~80 lines). The `bin/` scripts are 1-5 lines each. README + followup-doc edits are small.

---

## 4. Day-to-day usage flows

### 4.1 First-time setup (cold clone)

```bash
git clone <repo>
cd playAIdes
cp .env.example .env             # edit with HA_TOKEN etc.
ollama serve                     # if not already running
docker compose up -d             # ~5-10 min first run (image pulls + Dockerfile builds)
docker compose logs -f           # watch startup
```

When `whisper` reports healthy and `backend` logs `Loaded persona: …`, open `http://localhost:5173/`. After first run, subsequent `docker compose up -d` takes <10s.

### 4.2 Change Python code → watchfiles restarts the backend

Save `playAIdes.py` or any `*.py` under the bind mount. `watchfiles` (the same library uvicorn uses internally for `--reload`) detects the change and restarts `python main.py`. Logs show:
```
backend  | [watchfiles] file changed: /app/playAIdes.py
backend  | [watchfiles] restarting…
backend  | INFO: Loaded persona: Silver
backend  | INFO: Started server process […]
```
Whole-process restart means in-memory state (chat history, persona binding cache) is rebuilt from disk — fine for dev, expected. Browser reconnects via the existing WS reconnect logic.

Why `watchfiles` instead of uvicorn's `--reload`: in this codebase the FastAPI app is launched inside a daemon thread by `IncarnationServer._run_server()`, and uvicorn's reload feature only works in the main thread. Wrapping the whole `python main.py` invocation with `watchfiles` sidesteps that without restructuring the app.

If something wedges, `docker compose restart backend` (~2s) bounces just that service.

### 4.3 Change frontend code → Vite HMR

Save anything in `incarnation/src/`. Vite pushes the patch over HMR — no full reload, Three.js scene state preserved across most edits. CSS swaps even faster.

### 4.4 Tests

```bash
bin/test                                    # full suite (~25s wall, 1.8s pytest)
bin/test pytest tests/unit -k ha_client     # focused subset
bin/test-js                                 # Vitest
bin/shell                                   # then run `pytest tests/...` natively for sub-second feedback
```

Runtime and test stacks don't share containers (different compose project, different container names) — running `bin/test` while `docker compose up` is active is safe.

### 4.5 Debugging

| Symptom | What to check |
|---|---|
| Browser can't connect to backend | `docker compose ps`; `docker compose logs backend` |
| Persona LLM hangs | `curl localhost:11434/api/tags` — is Ollama running on the host? |
| TTS not working | `docker compose logs tts` — likely GPU busy (ComfyUI/etc. using the card) |
| Whisper STT fails | First-run model download takes ~60s; check `docker compose logs whisper` |
| HA delegation silently no-ops | `docker compose logs backend \| grep -i ha` — startup warning if HA env vars missing |
| One-off backend command | `docker compose run --rm backend python -m foo.bar` |
| Container in weird state | `docker compose down && docker compose up -d` (cheap full reset) |

### 4.6 Stopping work

```bash
docker compose down              # stops + removes containers; named volumes preserved
docker compose down -v           # also wipes named volumes
bin/clean                        # full nuke: down -v on all 3 compose files + delete caches
```

---

## 5. What this design does NOT change

- Iterating on a single test in `bin/shell` is still the fastest dev loop (sub-second pytest, no Docker overhead per change).
- TTS still requires NVIDIA GPU. If your GPU is saturated it fails to start; `docker compose up -d backend frontend whisper` brings up everything else.
- `bin/test-live` still spins up a separate live stack for full E2E.
- Ollama still runs on the host. Switching to llama.cpp later is a different codebase change; the compose stays the same (still points at `host.docker.internal:11434`).

---

## 6. Out of scope (deferred to future specs)

- **Production mode** — built images, nginx for the frontend, gunicorn-or-similar for the backend, possibly systemd unit files for a household-TV server. Big project; revisit when actually deploying.
- **Containerizing Ollama** — explicitly off the table per user direction (llama.cpp swap planned).
- **Folding tests into the main compose** — keeps separate; different lifecycle.
- **Fixture consolidation + Docker-or-not test architecture** — both stay in the deferred testing-overhaul followup. This work resolves only the "Make abstraction" piece of that.
- **Dev/prod profiles in one compose file** — explicitly skipped (dev-only per scope).
