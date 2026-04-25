# playAIdes test orchestration — everything runs in Docker, nothing on the host.
#
# Common targets:
#   make test        # Python unit + integration (default, fast, offline)
#   make test-js     # frontend Vitest (incarnation/ JS modules)
#   make test-all    # Python + JS (runs both in sequence)
#   make test-live   # full E2E against real Ollama + TTS containers (GPU required for TTS)
#   make coverage    # run tests and copy coverage.xml out of the container
#   make shell       # interactive shell in the test image for poking around
#   make clean       # tear down containers, volumes, and .test-output/

COMPOSE_TEST := docker compose -f docker-compose.test.yml
COMPOSE_LIVE := docker compose -f docker-compose.test.yml -f docker-compose.live.yml
COMPOSE_DEV  := docker compose -f docker-compose.dev.yml

.PHONY: help test test-js test-all test-live test-unit test-integration coverage shell js-shell clean build build-js whisper whisper-stop dev-up dev-down

help:
	@echo "Targets: test, test-js, test-all, test-live, test-unit, test-integration, coverage, shell, js-shell, clean, build, build-js, whisper, whisper-stop, dev-up, dev-down"

build:
	$(COMPOSE_TEST) build tests

build-js:
	$(COMPOSE_TEST) build js-tests

test: build
	mkdir -p .test-output
	$(COMPOSE_TEST) run --rm tests

test-js: build-js
	$(COMPOSE_TEST) run --rm js-tests

test-all: test test-js

test-unit: build
	mkdir -p .test-output
	$(COMPOSE_TEST) run --rm tests pytest tests/unit -m "not live"

test-integration: build
	mkdir -p .test-output
	$(COMPOSE_TEST) run --rm tests pytest tests/integration -m "integration"

test-live:
	mkdir -p .test-output
	$(COMPOSE_LIVE) up -d ollama tts whisper
	$(COMPOSE_LIVE) run --rm ollama-model-pull || true
	$(COMPOSE_LIVE) run --rm tests pytest -m live
	$(COMPOSE_LIVE) down

coverage: test
	@cp .test-output/coverage.xml ./coverage.xml 2>/dev/null || echo "no coverage.xml produced"
	@echo "Coverage XML: ./coverage.xml"

shell: build
	$(COMPOSE_TEST) run --rm --entrypoint /bin/bash tests

js-shell: build-js
	$(COMPOSE_TEST) run --rm --entrypoint /bin/bash js-tests

# Local-dev backing services (host-port-exposed, distinct from test-live overlay).
whisper:
	$(COMPOSE_DEV) up -d whisper
	@echo "Whisper running at http://localhost:9000 (first run pulls the base model — give it ~60s)."
	@echo "Tail logs:  docker logs -f playaides-whisper-dev"

whisper-stop:
	$(COMPOSE_DEV) stop whisper
	$(COMPOSE_DEV) rm -f whisper

dev-up: whisper

dev-down:
	$(COMPOSE_DEV) down

clean:
	$(COMPOSE_LIVE) down -v --remove-orphans 2>/dev/null || true
	$(COMPOSE_TEST) down -v --remove-orphans 2>/dev/null || true
	$(COMPOSE_DEV)  down -v --remove-orphans 2>/dev/null || true
	rm -rf .test-output coverage.xml .pytest_cache .coverage
