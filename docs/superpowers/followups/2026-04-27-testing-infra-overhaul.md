# Followup: Testing Infrastructure Overhaul

**Created:** 2026-04-27
**Status:** Deferred — to be brainstormed in a future session
**Triggered by:** HA integration session (2026-04-26 → 04-27) — leaked test containers caused a workstation crash, exposing fragility in the test setup

## Why this exists

During the HA integration build, the test infrastructure caused real pain:

1. **Container leaks** — One bad test fixture (`host="testhost"` causing DNS hang in a daemon thread) leaked one zombie Docker container per `make test` invocation. Over ~30 test runs across a session, this accumulated 12+ stuck containers consuming CPU/RAM and ultimately crashed the workstation.
2. **Two parallel test fixture patterns** — The "right" pattern (`_NoopThread` monkeypatch in `tests/integration/conftest.py`) wasn't discovered by the agent that wrote the new HA fixtures, leading to a wrong fixture that compounded the leak.
3. **Slow per-iteration feedback** — `make test` takes ~25s wall-clock for a 1.8s pytest run. That's Docker startup overhead. Acceptable for pre-commit, painful for active iteration.
4. **Make wrapper isn't pulling much weight** — The `Makefile` aliases `docker compose run --rm tests` to `make test`. It's about 80% convention, 20% real value at this project's scale. Modern alternatives (`just`, `npm` scripts, plain `bin/test` shell scripts, `hatch`/`uv` task runners) exist.
5. **`make shell` for fast interactive iteration is undocumented.** It exists and works (drop into bash inside the test image, run `pytest tests/...` natively for sub-second feedback), but nothing tells a new contributor about it.

None of these are individually broken. Together they suggest the testing infrastructure has accumulated complexity faster than ergonomics.

## What to brainstorm next session

Open questions worth designing through, not pre-answering here:

- **Should we keep Docker-wrapped tests at all?** Pure `pytest` in a venv is ~2s end-to-end. Docker gives reproducibility at a 12× iteration cost. Is that trade still earning its keep at 174 tests?
- **If yes to Docker, can we drop the Make layer?** What would `just`-based or `package.json`-based or bare-shell-script alternatives look like?
- **Test fixture consolidation.** Document the `_NoopThread` pattern as the canonical way to build IncarnationServer in tests. Possibly factor the fixture into the top-level `tests/conftest.py` so it's discoverable from any test file (right now it's only in `tests/integration/conftest.py`). Optionally add a lint/CI check that flags any test creating `IncarnationServer` without the monkeypatch.
- **Faster local iteration.** Add a `make test-watch` (pytest-watch in a container) or document the `make shell` + interactive pytest workflow in CLAUDE.md / a CONTRIBUTING doc.
- **Container leak prevention.** Even with the `_NoopThread` pattern, a bad fixture could regress and leak again. Should `make test` end with a sanity check (`docker ps --filter ... -q | wc -l` should be 0)? Or a CI-side leak detector?
- **Should the test deps live in `pyproject.toml` `[project.optional-dependencies]` `dev`** (current state — works) **or in a separate `requirements-test.txt`** (older convention)? Less important; just flagging.
- **JS test parity.** `make test-js` uses a separate Docker image with vitest. Same complexity question — could it just be `npm test` natively? Vitest is fast either way.

## Background context for the brainstormer

These will save you a lot of digging:

- **Current setup**: [Makefile](Makefile), [docker-compose.test.yml](docker-compose.test.yml), [Dockerfile.test](Dockerfile.test), [Dockerfile.test-js](Dockerfile.test-js), [pyproject.toml](pyproject.toml) `[project.optional-dependencies] dev` block.
- **The good fixture pattern**: [tests/integration/conftest.py](tests/integration/conftest.py) — `_NoopThread` + `incarnation_server` + `client` fixtures.
- **The painful commits from this session**:
  - `30fcab3` — first attempt: change `host="testhost"` to `127.0.0.1`. Made tests bind cleanly but didn't stop uvicorn's asyncio loop from keeping pytest alive at shutdown.
  - `5e0e84b` — actual fix: refactor my HA test fixtures to reuse the existing `_NoopThread` pattern.
  - The lessons are in those commit messages.
- **Existing test counts** (as of 2026-04-27): 174 Python passed (4 deselected, 2 warnings), 89 Vitest passed. `make test` wall: ~25s. `pytest` inside `make shell`: ~2s.

## Suggested entry point for the future session

Start with: `/superpowers:brainstorm overhaul the testing infrastructure — see docs/superpowers/followups/2026-04-27-testing-infra-overhaul.md`. The brainstorming skill will then explore the questions above and propose 2-3 architectural options before writing a spec.

Likely sub-projects this could decompose into (worth flagging up front so the brainstorm doesn't try to swallow everything at once):

1. **Fast-iteration ergonomics** — document `make shell`, add `test-watch`, possibly drop Make for `just`/scripts.
2. **Fixture consolidation** — promote `_NoopThread` pattern to top-level conftest, prevent regression.
3. **Docker-or-not architectural question** — the bigger one; punts on whether the whole Docker-wrapped layer should stay.

Each could ship independently.
