# playAIdes

What's working:

**PlayAIdes**
- Chatting with Ollama
- Loading personas from JSON files
- Basic chat interface

**Incarnation**
- Basic model loading (local file)
- Basic animation loading (local file)
- Animation playback over WebSockets

## Running the test suite

Everything runs in Docker — **no Python or dependencies need to be installed on the host**. Only requirements are `docker` + `docker compose` + `make`.

```bash
make test           # Unit + integration tests (fast, offline)
make test-unit      # Unit tests only
make test-integration  # FastAPI TestClient integration tests only
make test-live      # End-to-end against real Ollama + TTS containers (needs NVIDIA GPU for TTS)
make coverage       # Run tests and export coverage.xml to the repo root
make shell          # Drop into a shell in the test image for poking around
make clean          # Tear down containers, volumes, and .test-output/
```

Test layout:

```
tests/
├── conftest.py        # Shared fixtures (mock LLM, fake TTS, tmp personas dir, live-endpoint skippers)
├── unit/              # No network, no threads — pure logic
├── integration/       # FastAPI TestClient (HTTP + WebSocket)
└── live/              # Real Ollama + TTS — marked `live`, auto-skipped when URLs unset
```

Live tests auto-skip when `OLLAMA_URL` / `TTS_URL` aren't set or unreachable, so `make test` is always green regardless of which backend services are running.

## Notes
Can't push model and persona files to GitHub because of licensing/size.
