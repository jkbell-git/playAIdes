# Docker Compose Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the scattered docker-compose configs and host processes into a single `docker compose up`; replace Make with `bin/` shell scripts; delete the duplicate TTS compose file.

**Architecture:** New top-level `docker-compose.yml` runs four services (backend, frontend, tts, whisper) with hot-reload everywhere via bind-mounts (`watchfiles` for Python, Vite HMR for JS). Ollama remains external on the host (preserves the future llama.cpp swap). Test stack (`docker-compose.test.yml`, `docker-compose.live.yml`) stays separate but invoked via `bin/test*` scripts instead of `make test*`.

**Tech Stack:** Docker Compose v2, `python:3.12-slim`, `node:22-slim`, `watchfiles` (Python file watcher), bash for `bin/` scripts.

**Spec:** [docs/superpowers/specs/2026-04-27-docker-compose-consolidation-design.md](../specs/2026-04-27-docker-compose-consolidation-design.md)

**Branch:** create `compose_consolidation` from `main` (no worktrees per project preference). Current `main` tip is `767fb61` (`spec: docker compose consolidation + Make removal`) — verify with `git log --oneline -1`.

## Conventions for this plan

- All paths relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.
- No new Python tests required (this is infra, not application code). Existing test suite (174 Python / 89 Vitest) must still pass at the end.
- Each task ends with a commit. Conventional Commits prefixes (`feat:`, `chore:`, `docs:`, `refactor:`).
- The runtime stack's full smoke test (`docker compose up` end-to-end) requires Ollama on the host AND GPU available; do that smoke in Task 12, not in earlier tasks.

## Baseline going in

- Branch: `main` at HEAD = `767fb61` — verify with `git log --oneline -1`.
- `bin/test` doesn't exist yet — `make test` is the current invocation; expect `174 passed, 4 deselected`.
- `make test-js` → 89 passed.

## File structure

| File | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Add `watchfiles>=0.21` to `[project.optional-dependencies] dev` |
| `Dockerfile.backend` | **Create** | Python 3.12 image; installs project + dev deps; default CMD wraps `python main.py` with `watchfiles` |
| `Dockerfile.frontend` | **Create** | Node 22 image; runs Vite dev server on `0.0.0.0:5173` |
| `docker-compose.yml` | **Create** (top-level) | 4-service runtime stack (backend, frontend, tts, whisper) |
| `.env.example` | **Create** | Documents env vars users should set |
| `bin/test` | **Create** | Wraps `docker compose -f docker-compose.test.yml run --rm tests "$@"` |
| `bin/test-js` | **Create** | Wraps `docker compose -f docker-compose.test.yml run --rm js-tests` |
| `bin/test-all` | **Create** | Runs `bin/test && bin/test-js` |
| `bin/test-live` | **Create** | Live-stack incantation (up → pull-model → live tests → down) |
| `bin/coverage` | **Create** | `bin/test` + copy `coverage.xml` to repo root |
| `bin/shell` | **Create** | Interactive bash in test image |
| `bin/js-shell` | **Create** | Interactive bash in js-tests image |
| `bin/clean` | **Create** | `down -v --remove-orphans` on all 3 compose files + delete caches |
| `Makefile` | **Delete** | Replaced by `bin/` scripts |
| `docker-compose.dev.yml` | **Delete** | Replaced by top-level `docker-compose.yml` |
| `voice_generation/voice_server/docker-compose.yml` | **Delete** | TTS now lives in top-level compose |
| `README.md` | Modify | Replace "Running the test suite" section with "Running" (runtime + tests) |
| `docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md` | Modify | Mark "Make abstraction" sub-project as resolved |

---

## Task 0: Branch creation + baseline verification

**Files:** none (git only).

- [ ] **Step 1: Verify baseline + create branch**

```bash
cd /home/bell/repo/ai_life/playAIdes
git log --oneline -1                     # expect: 767fb61 spec: docker compose consolidation + Make removal
git checkout -b compose_consolidation main
make test 2>&1 | tail -3                 # expect: 174 passed, 4 deselected
```

If the baseline doesn't match, STOP and report.

---

## Task 1: Add `watchfiles` to dev dependencies

**Files:**
- Modify: `pyproject.toml`

`watchfiles` ships transitively with uvicorn but pin it explicitly so the dev hot-reload workflow doesn't break if uvicorn's deps change.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, find the `[project.optional-dependencies]` block (around line 25). Update the `dev` list to add `"watchfiles>=0.21",` after the existing `"respx>=0.21",`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "responses>=0.25",        # requests mocking
    "respx>=0.21",            # httpx mocking
    "watchfiles>=0.21",       # backend hot-reload in docker compose
]
```

- [ ] **Step 2: Verify nothing breaks**

```bash
make test 2>&1 | tail -3
```

Expected: `174 passed, 4 deselected` (count unchanged — pyproject change doesn't affect test discovery).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add watchfiles to dev deps for backend hot-reload"
```

---

## Task 2: `Dockerfile.backend`

**Files:**
- Create: `Dockerfile.backend`

Python 3.12 runtime image. Installs project + dev deps (which now includes `watchfiles`). The default CMD wraps `python main.py` with `watchfiles` so any `*.py` change in the bind-mounted `/app` triggers a process restart.

- [ ] **Step 1: Create the file**

Create `Dockerfile.backend`:

```dockerfile
# Backend runtime image — playAIdes + incarnation_server.
#
# Source is bind-mounted from the host at runtime (see docker-compose.yml),
# so this image only carries Python + deps. `watchfiles` wraps the entrypoint
# so any *.py change in /app triggers a whole-process restart (uvicorn's own
# --reload doesn't work because IncarnationServer launches uvicorn in a
# daemon thread — see spec § 4.2).
FROM python:3.12-slim

# Install minimal build deps. portaudio is intentionally absent — the backend
# container doesn't do live speaker playback (TTS proxies stream audio to the
# browser instead).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata only, install deps. Source is bind-mounted at runtime
# so we don't COPY the rest of the repo into the image.
COPY pyproject.toml /app/pyproject.toml

# Editable install picks up the bind-mounted source. `[dev]` brings in
# watchfiles + pytest (pytest is unused at runtime but harmless and keeps
# the dependency set predictable).
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8765

# `watchfiles --filter python` watches only *.py files in /app. The command
# string `python main.py --use_avatar` is a single argv arg (watchfiles
# parses it as a shell command).
CMD ["watchfiles", "--filter", "python", "python main.py --use_avatar", "/app"]
```

- [ ] **Step 2: Build the image**

```bash
docker build -f Dockerfile.backend -t playaides-backend:latest .
```

Expected: build succeeds (~2-3 min first time, faster on rebuild). No errors.

- [ ] **Step 3: Quick sanity check**

```bash
docker run --rm playaides-backend:latest python --version
docker run --rm --entrypoint python playaides-backend:latest -c "import watchfiles; print(watchfiles.__version__)"
```

Expected: Python 3.12.x version string + a watchfiles version like `0.21.0` (or higher).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile.backend
git commit -m "feat: Dockerfile.backend — Python 3.12 + watchfiles entrypoint"
```

---

## Task 3: `Dockerfile.frontend`

**Files:**
- Create: `Dockerfile.frontend`

Tiny Node image. `node_modules` lives in a named volume at runtime so the bind-mounted host source doesn't shadow the baked install (mirrors the `js-tests` pattern in `docker-compose.test.yml`).

- [ ] **Step 1: Create the file**

Create `Dockerfile.frontend`:

```dockerfile
# Frontend dev image — Vite dev server for incarnation/.
#
# Source is bind-mounted from the host at runtime; node_modules lives in a
# named volume (see docker-compose.yml) so the baked install isn't shadowed
# by the bind-mount. Vite's HMR pushes patches to the open browser tab.
FROM node:22-slim

WORKDIR /app/incarnation

# Copy lockfiles only, install deps. Source is bind-mounted at runtime.
COPY incarnation/package.json incarnation/package-lock.json* /app/incarnation/

RUN npm ci

EXPOSE 5173

# `--host 0.0.0.0` is critical so the container's Vite dev server is
# reachable from the host browser, not just from inside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

- [ ] **Step 2: Build the image**

```bash
docker build -f Dockerfile.frontend -t playaides-frontend:latest .
```

Expected: build succeeds. If `incarnation/package-lock.json` doesn't exist, the wildcard handles it gracefully — `npm ci` will then fail with a clear message (in which case run `cd incarnation && npm install` once on the host first to generate the lockfile, commit it, and rebuild).

- [ ] **Step 3: Quick sanity check**

```bash
docker run --rm playaides-frontend:latest node --version
```

Expected: a Node version string (e.g., `v22.x.x`).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile.frontend
git commit -m "feat: Dockerfile.frontend — Node 22 + Vite dev server"
```

---

## Task 4: `.env.example`

**Files:**
- Create: `.env.example`

Documents env vars users should set. Compose auto-loads `.env` (gitignored) from the working directory.

- [ ] **Step 1: Verify `.env` is gitignored**

```bash
grep -E "^\.env$" .gitignore || echo "MISSING — need to add"
```

If `MISSING`, add `.env` on its own line in `.gitignore` (don't add `.env*` — that would also gitignore `.env.example`).

- [ ] **Step 2: Create the file**

Create `.env.example`:

```bash
# Copy this to .env and edit the values you need. Compose auto-loads .env.
# Do NOT commit .env (already gitignored).

# ─ Home Assistant integration ────────────────────────────────────────────
# Required for any HA feature. Leave empty to disable HA.
HA_URL=
HA_TOKEN=
HA_DEFAULT_AGENT_ID=

# ─ Bearer token HA must send to playAIdes endpoints ──────────────────────
# Unset = dev mode (no auth check, with startup warning). Set to anything
# random in shared deployments.
PLAYAIDES_API_KEY=

# ─ Ollama (external — not in docker compose) ─────────────────────────────
# Backend reaches Ollama via http://host.docker.internal:11434
# (configured in docker-compose.yml, not here). Only override OLLAMA_MODEL
# below if you want a different model than the default.
OLLAMA_MODEL=gemma3:4b
```

- [ ] **Step 3: Commit**

```bash
git add .env.example .gitignore  # .gitignore only if you modified it
git commit -m "feat: .env.example — documents HA + API key env vars"
```

(If `.gitignore` was already correct, omit it from `git add`.)

---

## Task 5: `docker-compose.yml` (top-level)

**Files:**
- Create: `docker-compose.yml` (at repo root)

Four services (backend, frontend, tts, whisper). Backend reaches host-side Ollama via `host.docker.internal` (Linux requires the `extra_hosts` entry). TTS + Whisper have no host ports — only reachable from `backend` over the default docker network.

- [ ] **Step 1: Create the file**

Create `docker-compose.yml` at the repo root:

```yaml
# Runtime stack for playAIdes — single source of truth for `docker compose up`.
#
# Brings up backend (Python + incarnation_server), frontend (Vite dev),
# tts (Qwen3 streaming TTS, GPU required), and whisper (STT). Ollama is
# intentionally NOT in this file — it stays external on the host so a
# future llama.cpp swap doesn't touch the docker stack.
#
# See spec: docs/superpowers/specs/2026-04-27-docker-compose-consolidation-design.md

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: playaides-backend:latest
    container_name: playaides-backend
    ports:
      - "8765:8765"
    volumes:
      - .:/app:rw                 # bind-mount whole repo for hot-reload
    environment:
      # External Ollama on the host. extra_hosts below makes
      # host.docker.internal resolve to the host gateway on Linux.
      - OLLAMA_URL=http://host.docker.internal:11434
      # Internal services reachable by docker-network DNS (service name).
      - TTS_URL=http://tts:8009
      - WHISPER_URL=http://whisper:9000
      # Pass-through from host shell / .env file. Empty = disabled (with
      # a startup log warning per the HA-integration spec).
      - PLAYAIDES_API_KEY
      - HA_URL
      - HA_TOKEN
      - HA_DEFAULT_AGENT_ID
      - OLLAMA_MODEL=${OLLAMA_MODEL:-gemma3:4b}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      tts:
        condition: service_started
      whisper:
        condition: service_healthy
    # CMD is set in Dockerfile.backend; uncomment to override for one-off runs:
    # command: ["python", "main.py", "--use_avatar"]

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    image: playaides-frontend:latest
    container_name: playaides-frontend
    ports:
      - "5173:5173"
    volumes:
      - ./incarnation:/app/incarnation:rw
      - frontend_node_modules:/app/incarnation/node_modules
    # CMD is set in Dockerfile.frontend.

  tts:
    build:
      context: ./voice_generation/voice_server
      dockerfile: Dockerfile_streaming_tts
    image: playaides-tts:latest
    container_name: playaides-tts
    volumes:
      - ./voice_generation/voice_server/hf_models:/root/.cache/huggingface
      - ./voice_generation/voice_server/service:/app/Qwen3-TTS-streaming/service
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              capabilities: [gpu]
    # No host port — only reachable from `backend` over the docker network.

  whisper:
    image: onerahmet/openai-whisper-asr-webservice:latest
    container_name: playaides-whisper
    environment:
      - ASR_MODEL=base
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/"]
      interval: 10s
      retries: 5
      start_period: 60s
    # No host port — only reachable from `backend` over the docker network.

volumes:
  frontend_node_modules:
```

- [ ] **Step 2: Validate the YAML and resolved config**

```bash
docker compose config > /dev/null
```

Expected: no output, exit code 0. If it errors, fix the YAML.

```bash
docker compose config --services
```

Expected: prints exactly four service names (backend, frontend, tts, whisper).

- [ ] **Step 3: Build the runtime images** (still no `up`)

```bash
docker compose build backend frontend
```

Expected: both images build successfully (TTS skipped here because it requires GPU and we may not have one available during planning verification — the user can build TTS in Task 12).

- [ ] **Step 4: Verify backend image picks up the bind-mount path correctly**

```bash
docker run --rm -v "$PWD:/app" playaides-backend:latest python -c "import os; print(sorted(f for f in os.listdir('/app') if f.endswith('.py'))[:3])"
```

Expected: prints something like `['incarnation_client.py', 'incarnation_server.py', 'main.py']` — proves the bind mount + Python path work together.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: top-level docker-compose.yml — backend / frontend / tts / whisper"
```

---

## Task 6: `bin/` shell scripts

**Files:**
- Create: `bin/test`, `bin/test-js`, `bin/test-all`, `bin/test-live`, `bin/coverage`, `bin/shell`, `bin/js-shell`, `bin/clean`

Eight scripts. Each is a few lines of bash. Created with `chmod +x`.

- [ ] **Step 1: Create the directory**

```bash
mkdir -p bin
```

- [ ] **Step 2: Create `bin/test`**

```bash
cat > bin/test <<'EOF'
#!/usr/bin/env bash
# Run the Python test suite (pytest) inside a Docker container.
# Pass extra args through to pytest, e.g. `bin/test pytest tests/unit -k mytest`.
set -euo pipefail
mkdir -p .test-output
docker compose -f docker-compose.test.yml run --rm tests "$@"
EOF
chmod +x bin/test
```

- [ ] **Step 3: Create `bin/test-js`**

```bash
cat > bin/test-js <<'EOF'
#!/usr/bin/env bash
# Run the frontend Vitest suite inside a Docker container.
set -euo pipefail
docker compose -f docker-compose.test.yml run --rm js-tests
EOF
chmod +x bin/test-js
```

- [ ] **Step 4: Create `bin/test-all`**

```bash
cat > bin/test-all <<'EOF'
#!/usr/bin/env bash
# Run Python tests then frontend tests sequentially.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/test"
"$DIR/test-js"
EOF
chmod +x bin/test-all
```

- [ ] **Step 5: Create `bin/test-live`**

```bash
cat > bin/test-live <<'EOF'
#!/usr/bin/env bash
# End-to-end tests against real Ollama + TTS + Whisper containers.
# Needs an NVIDIA GPU for the TTS service.
set -euo pipefail
mkdir -p .test-output
COMPOSE="docker compose -f docker-compose.test.yml -f docker-compose.live.yml"
$COMPOSE up -d ollama tts whisper
$COMPOSE run --rm ollama-model-pull || true
$COMPOSE run --rm tests pytest -m live
$COMPOSE down
EOF
chmod +x bin/test-live
```

- [ ] **Step 6: Create `bin/coverage`**

```bash
cat > bin/coverage <<'EOF'
#!/usr/bin/env bash
# Run tests and copy coverage.xml to the repo root.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/test"
if [[ -f .test-output/coverage.xml ]]; then
  cp .test-output/coverage.xml ./coverage.xml
  echo "Coverage XML: ./coverage.xml"
else
  echo "no coverage.xml produced" >&2
  exit 1
fi
EOF
chmod +x bin/coverage
```

- [ ] **Step 7: Create `bin/shell`**

```bash
cat > bin/shell <<'EOF'
#!/usr/bin/env bash
# Drop into bash inside the test image — useful for interactive `pytest`.
set -euo pipefail
docker compose -f docker-compose.test.yml run --rm --entrypoint /bin/bash tests
EOF
chmod +x bin/shell
```

- [ ] **Step 8: Create `bin/js-shell`**

```bash
cat > bin/js-shell <<'EOF'
#!/usr/bin/env bash
# Drop into bash inside the js-tests image.
set -euo pipefail
docker compose -f docker-compose.test.yml run --rm --entrypoint /bin/bash js-tests
EOF
chmod +x bin/js-shell
```

- [ ] **Step 9: Create `bin/clean`**

```bash
cat > bin/clean <<'EOF'
#!/usr/bin/env bash
# Tear down all docker compose stacks + remove caches.
set -euo pipefail
docker compose                                                       down -v --remove-orphans 2>/dev/null || true
docker compose -f docker-compose.test.yml                            down -v --remove-orphans 2>/dev/null || true
docker compose -f docker-compose.test.yml -f docker-compose.live.yml down -v --remove-orphans 2>/dev/null || true
rm -rf .test-output coverage.xml .pytest_cache .coverage
echo "clean: done"
EOF
chmod +x bin/clean
```

- [ ] **Step 10: Verify scripts exist and are executable**

```bash
ls -la bin/
```

Expected: 8 files, all `-rwxr-xr-x`.

- [ ] **Step 11: Smoke-test `bin/test`**

```bash
bin/test 2>&1 | tail -3
```

Expected: `174 passed, 4 deselected`. This is the same as `make test` — proves the script wraps it correctly.

- [ ] **Step 12: Smoke-test `bin/test-js`**

```bash
bin/test-js 2>&1 | grep -E "Test Files|Tests " | tail -2
```

Expected: `Test Files 8 passed (8)` and `Tests 89 passed (89)`.

- [ ] **Step 13: Commit**

```bash
git add bin/
git commit -m "feat: bin/ shell scripts replace Make for test commands"
```

---

## Task 7: Delete `Makefile`, `docker-compose.dev.yml`, `voice_generation/voice_server/docker-compose.yml`

**Files:**
- Delete: `Makefile`
- Delete: `docker-compose.dev.yml`
- Delete: `voice_generation/voice_server/docker-compose.yml`

The Makefile is dead now that `bin/` exists. The dev compose is replaced by the new top-level compose. The voice_server compose duplicates the `tts` service config.

- [ ] **Step 1: Verify the new alternatives still work before deletion**

```bash
bin/test 2>&1 | tail -3
docker compose config --services
```

Expected: `174 passed` and four service names. If either fails, do NOT delete — investigate first.

- [ ] **Step 2: Delete the files**

```bash
git rm Makefile
git rm docker-compose.dev.yml
git rm voice_generation/voice_server/docker-compose.yml
```

- [ ] **Step 3: Verify nothing references the deleted files**

```bash
grep -rn "Makefile\|docker-compose\.dev\.yml\|voice_generation/voice_server/docker-compose\.yml" \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.test-output \
  --exclude="*.md" || echo "(no code references — markdown will be cleaned up in Task 8)"
```

Expected: only matches in `.md` files (which Task 8 cleans up). No `.py`, `.js`, `.yaml`, `.yml`, or shell-script references.

- [ ] **Step 4: Run tests one more time to be certain**

```bash
bin/test 2>&1 | tail -3
```

Expected: `174 passed, 4 deselected`.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: remove Makefile + docker-compose.dev.yml + duplicate TTS compose

- Makefile replaced by bin/ scripts
- docker-compose.dev.yml replaced by top-level docker-compose.yml
- voice_generation/voice_server/docker-compose.yml was a duplicate of
  the tts service in the new top-level compose"
```

---

## Task 8: Update `README.md`

**Files:**
- Modify: `README.md`

Replace the "Running the test suite" section with a new "Running" section covering both runtime and tests.

- [ ] **Step 1: Read the current README "Running the test suite" section**

```bash
grep -n "Running the test suite\|## " README.md
```

Note the line numbers of the section heading and the next `## ` heading after it.

- [ ] **Step 2: Replace the section**

Open `README.md` and replace the entire "## Running the test suite" section (from `## Running the test suite` through to the line just before the next `## ` heading) with:

````markdown
## Running

### Runtime stack

Ollama runs externally (on the host or another machine). Everything else lives in `docker-compose.yml` at the repo root.

```bash
ollama serve                   # if not already running on the host
cp .env.example .env           # first time only; edit with your HA_TOKEN etc.
docker compose up -d           # backend + frontend + tts + whisper
docker compose logs -f         # tail all logs
docker compose down            # stop everything
```

Browser at `http://localhost:5173/`. Backend HTTP/WS at `http://localhost:8765/`.

To restart a single service: `docker compose restart backend`.

To bring up only some services: `docker compose up -d backend frontend whisper` (skips TTS — useful when your GPU is busy with other workloads).

Hot-reload works for both languages:
- Save a `*.py` file → `watchfiles` restarts the backend container in <2s
- Save a frontend file → Vite HMR pushes the patch to the open browser tab

### Tests

```bash
bin/test                       # Python unit + integration (~25s wall, 1.8s pytest)
bin/test-js                    # Frontend Vitest
bin/test-all                   # both, sequentially
bin/test-live                  # full E2E with real Ollama + TTS containers (GPU needed)
bin/coverage                   # run tests + copy coverage.xml to repo root
bin/shell                      # interactive bash in the test image (run pytest natively for sub-second feedback)
bin/js-shell                   # interactive bash in the js-tests image
bin/clean                      # tear all stacks down + remove caches
```

`bin/test` passes extra args through to pytest:

```bash
bin/test pytest tests/unit -k ha_client -v
```

Each `bin/` script is a few lines of bash — `cat bin/test` shows exactly what it runs.

Test layout:

```
tests/
├── conftest.py        # Shared fixtures (mock LLM, fake TTS, tmp personas dir, live-endpoint skippers)
├── unit/              # No network, no threads — pure logic
├── integration/       # FastAPI TestClient (HTTP + WebSocket)
└── live/              # Real Ollama + TTS — marked `live`, auto-skipped when URLs unset
```

Live tests auto-skip when `OLLAMA_URL` / `TTS_URL` aren't set or unreachable, so `bin/test` is always green regardless of which backend services are running.
````

- [ ] **Step 3: Verify nothing else in the README references `make`**

```bash
grep -n "make " README.md
```

Expected: no matches. If any remain, replace each with the appropriate `bin/` or `docker compose` command.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README — Running section covers runtime stack + bin/ test scripts"
```

---

## Task 9: Update the deferred testing-overhaul followup

**Files:**
- Modify: `docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md`

The "Make abstraction" sub-project is now resolved by this work. Mark it inline so a future session knows only fixture consolidation + Docker-or-not remain.

- [ ] **Step 1: Add a "Resolved sub-projects" callout near the top**

Open `docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md`. Just below the `# Followup: Testing Infrastructure Overhaul` heading and the existing intro lines, insert this block before the `## Why this exists` heading:

```markdown
> **Status update (2026-04-27):** The "Make abstraction" sub-project below was
> resolved by `docs/superpowers/specs/2026-04-27-docker-compose-consolidation-design.md`.
> Make is gone; `bin/` shell scripts replaced it. The other two sub-projects
> (fixture consolidation, Docker-or-not architectural question) remain
> deferred — see the "Suggested entry point" section at the bottom.
```

- [ ] **Step 2: Mark the specific sub-project as resolved at the bottom**

Find the "Suggested entry point for the future session" section near the bottom of the followup doc. Update the numbered list:

```markdown
Likely sub-projects this could decompose into (worth flagging up front so the brainstorm doesn't try to swallow everything at once):

1. ~~**Fast-iteration ergonomics** — document `make shell`, add `test-watch`, possibly drop Make for `just`/scripts.~~ **RESOLVED 2026-04-27** by the docker-compose consolidation spec; Make removed, `bin/` scripts replace it. `bin/shell` is the documented fast-iteration path.
2. **Fixture consolidation** — promote `_NoopThread` pattern to top-level conftest, prevent regression.
3. **Docker-or-not architectural question** — the bigger one; punts on whether the whole Docker-wrapped layer should stay.

Each could ship independently.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md
git commit -m "docs: mark Make-abstraction sub-project resolved by compose consolidation"
```

---

## Task 10: Update memory pointer

**Files:**
- Modify: `/home/bell/.claude/projects/-home-bell-repo-ai-life-playAIdes/memory/testing_infra_overhaul_deferred.md`

The memory pointer for the testing-overhaul followup should reflect that one sub-project shipped.

- [ ] **Step 1: Edit the memory file**

Open `/home/bell/.claude/projects/-home-bell-repo-ai-life-playAIdes/memory/testing_infra_overhaul_deferred.md`. Find the existing intro paragraph and update it to read:

```markdown
User flagged on 2026-04-27 that the playAIdes testing infrastructure feels overly complicated. They want to brainstorm and overhaul it at a future date — not now.

**Status (2026-04-27):** The "Make abstraction" piece was resolved by the docker-compose consolidation work (see `docs/superpowers/specs/2026-04-27-docker-compose-consolidation-design.md`). Make is gone; `bin/` shell scripts replaced it. Two sub-projects remain deferred: **fixture consolidation** and the **Docker-or-not architectural question**.

**Full context lives in the project**: [docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md](docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md).
```

(Replace the existing first-paragraph + "Full context lives in the project" line with the block above. Leave the rest of the file unchanged.)

- [ ] **Step 2: No commit needed**

Memory files live outside the project repo and aren't part of git history. Just save and move on.

---

## Task 11: End-of-pass verification (no full live `up` smoke yet)

**Files:** none (verification only).

- [ ] **Step 1: All test suites still pass**

```bash
bin/test 2>&1 | tail -3
bin/test-js 2>&1 | grep -E "Tests " | tail -1
```

Expected: `174 passed, 4 deselected` and `Tests 89 passed (89)`.

- [ ] **Step 2: Compose config is valid + has the expected services**

```bash
docker compose config --services
docker compose -f docker-compose.test.yml config --services
docker compose -f docker-compose.test.yml -f docker-compose.live.yml config --services
```

Expected:
- Top-level: `backend`, `frontend`, `tts`, `whisper` (4 lines).
- Test: `tests`, `js-tests` (2 lines).
- Live overlay: `tests`, `js-tests`, `ollama`, `ollama-model-pull`, `tts`, `whisper` (6 lines).

- [ ] **Step 3: All deleted-file references are gone from non-doc sources**

```bash
grep -rn "Makefile\|docker-compose\.dev\.yml" \
  --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.test-output \
  --exclude="*.md" || echo "(clean)"
```

Expected: `(clean)`.

- [ ] **Step 4: bin/ scripts are all executable**

```bash
ls -la bin/ | tail -n +2 | awk '{print $1, $NF}'
```

Expected: 8 entries, each `-rwxr-xr-x`.

- [ ] **Step 5: Self-review checklist**

- [ ] All 8 spec § 3 components implemented.
- [ ] No new `TODO` / `FIXME` / `TBD` strings introduced (`grep -rnE "TODO|FIXME|TBD" $(git diff --name-only main..HEAD | grep -E "\\.(py|md|sh|yml|yaml|toml|Dockerfile)$") | grep -v "Dockerfile.test\|Dockerfile.test-js"`).
- [ ] Existing test suite unchanged (174 Python / 89 Vitest).
- [ ] Followup doc updated with resolved sub-project.
- [ ] Memory pointer updated.
- [ ] All Phase 5 spec out-of-scope items remain unimplemented (no production mode, no Ollama containerization, no test-stack folding, no fixture consolidation).

- [ ] **Step 6: No commit (process marker)**

---

## Task 12: Manual full-stack smoke (user-driven, NOT a subagent task)

**Files:** none.

This is a one-time verification the user (not a subagent) runs to confirm the live stack actually comes up. It needs:
- Ollama running on the host (`curl localhost:11434/api/tags` returns 200)
- An NVIDIA GPU available for the `tts` service (or skip TTS by listing `backend frontend whisper` only)

Document for the user (not as automated steps for a subagent):

```bash
ollama serve  &                   # background — or already running
cp .env.example .env              # first time
# (edit .env: set HA_URL/HA_TOKEN if you want to test HA, otherwise leave empty)

docker compose up -d              # full stack including TTS
# OR for no-GPU test:
docker compose up -d backend frontend whisper

docker compose logs -f backend    # watch for "Loaded persona: ..."
                                  # then Ctrl-C out of logs

curl http://localhost:8765/api/state    # should return JSON {"active_persona_id": "...", "bound_client_count": 0}
curl -I http://localhost:5173/          # should return 200

# Hot-reload smoke:
touch persona.py                  # any *.py file under repo root
docker compose logs --tail=5 backend  # should show watchfiles restart messages

docker compose down               # all done
```

If anything in this manual smoke fails, file a fix as a separate small task — don't try to fix mid-plan.

---

## Self-review checklist (run before marking implementation done)

- [ ] **Spec coverage**: every section of the spec maps to a Task above (§3.1 → Task 2, §3.2 → Task 3, §3.3 → Task 5, §3.4 → Task 4, §3.5 → Task 6, §3.6 → Task 7, §3.7 → Task 8, §3.8 → Task 9). Plus dep change (Task 1) and verification (Task 11).
- [ ] **No placeholders**: no TBD/TODO/FIXME in any plan task.
- [ ] **Type / name consistency**: `playaides-backend:latest`, `playaides-frontend:latest`, `playaides-tts:latest`, `host.docker.internal`, `frontend_node_modules`, `bin/test*`, `compose_consolidation` (branch) — same names everywhere they appear.
- [ ] **No silent scope creep**: every task is a fix/feature/chore that maps directly to a spec component.
- [ ] **Backwards compat preserved**: existing test suite passes; nothing in `playAIdes.py` / `incarnation_server.py` / `persona.py` modified.
