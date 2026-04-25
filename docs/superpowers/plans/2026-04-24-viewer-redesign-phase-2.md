# Viewer Redesign — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the viewer conversational by voice — browser mic captures the user's speech, energy-threshold VAD bounds each utterance, the audio is round-tripped through a containerized multilingual Whisper STT proxy, the resulting text is sent over WebSocket as `user_input`, and `PlayAIdes.chat()` routes it to the LLM. The existing `assistant_message` + `start_lip_sync` reply path from Phase 1 closes the loop. New `LISTENING` and `THINKING` states drive the mic-indicator + subtitle band visuals.

**Architecture:** Two pure-ish frontend modules — `audioCapture.js` (mic + AnalyserNode VAD; emits `voicestart` / `voiceend` events) and `sttClient.js` (multipart POST to `/api/stt/proxy`). Both are unit-testable under Vitest's node env with stub AudioContext/MediaRecorder/fetch. The orchestrator (`viewer.js`) wires those events into the state machine and forwards transcripts to `connection.send('user_input', { text })`. Backend gains one HTTP proxy endpoint and one WS message handler — both follow the patterns established by the existing `/api/tts/proxy` and `_handle_incarnation_message` switch.

**Tech Stack:** Vanilla JS (ES modules + Vitest), Three.js (already wired), FastAPI + httpx + python-multipart (already in `Dockerfile.test`), pytest, [`onerahmet/openai-whisper-asr-webservice`](https://github.com/ahmetoner/whisper-asr-webservice) for the Whisper container.

**Branch:** continue on `viewer_redesign` / `claude/sleepy-bell-4e5de8` after Phase 1 lands.

**Reference spec:** `docs/superpowers/specs/2026-04-24-viewer-redesign-design.md` — read §1 (overview), §2 (state machine), §3 (architecture, especially "Multilingual STT" and the WS message tables), §6 (backend additions), §7 (URL params), §9 (open questions, especially VAD library choice + Whisper-down behavior). Phase 2 implements the LISTENING and THINKING states; INTRO/AMBIENT/SPEAKING already work from Phase 1.

## Conventions for this plan

- **Backend (Python)** uses TDD via `make test`. Whisper-touching tests use `respx` to mock the upstream HTTP call so they run offline. The real-Whisper smoke test goes in `tests/live/` and is skipped without the live stack.
- **Frontend (JS)** pure modules use Vitest in Docker (`make test-js`). DOM-coupled wiring (orchestrator extensions, overlay updates) uses manual browser verification.
- Each task ends with a commit. Conventional Commits prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- All file paths are relative to repo root: `/home/bell/repo/ai_life/playAIdes/`.

## Phase 2 simplifications (deferred to later phases)

- **Wake-word matching is not implemented in Phase 2.** The `?activation=` URL param is still parsed, but in Phase 2 every detected utterance is forwarded to `user_input` regardless of `wake` vs `continuous`. Phase 3 introduces the wake-word gate that makes the modes diverge.
- **Persona routing fields on `user_input` are deferred.** Phase 2 sends `{ text }`; the spec's full `{ text, persona_id }` shape lands in Phase 4 alongside `set_active_persona`.
- **Echo / TTS bleed-through into the mic is accepted.** Browser `getUserMedia` applies AEC by default, which is good enough for headphone/speaker users in v1. No "pause mic during SPEAKING" logic.

---

## Task 1: Whisper container + `WHISPER_BASE` env wiring

**Files:**
- Modify: `docker-compose.live.yml`
- Modify: `incarnation_server.py` (top-of-file env block, ~line 30)

No tests in this task — the upstream is exercised in Tasks 2 and 8. This is config + plumbing only.

- [ ] **Step 1: Add the `whisper` service to `docker-compose.live.yml`**

Append to the `services:` block (alongside `ollama`, `tts`, etc.):

```yaml
  whisper:
    image: onerahmet/openai-whisper-asr-webservice:latest
    container_name: playaides-whisper
    environment:
      # Multilingual base model — supports both English and Japanese.
      # Do NOT switch to *.en — we lose Japanese.
      - ASR_MODEL=base
      - ASR_ENGINE=faster_whisper
    ports: []
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import urllib.request; urllib.request.urlopen('http://localhost:9000/docs', timeout=2)\""]
      interval: 15s
      timeout: 5s
      retries: 40
      start_period: 60s
    restart: unless-stopped
```

GPU is optional for `base` — CPU works. (`small` would benefit from GPU; we stay on `base` for v1.)

- [ ] **Step 2: Add `WHISPER_URL` to the test compose env so live tests can talk to it**

In `docker-compose.test.yml`, the existing `tests` service has an `environment` block setting `OLLAMA_URL=` and `TTS_URL=` (intentionally empty so live tests skip). Add:

```yaml
      - WHISPER_URL=
```

This keeps the unit + integration test behavior unchanged (env var empty → `WHISPER_BASE` falls back to its default at module import).

- [ ] **Step 3: Read `WHISPER_URL` near the top of `incarnation_server.py`**

In `incarnation_server.py`, line ~30 currently has:

```python
TTS_BASE = os.environ.get("TTS_URL", "http://localhost:8009")
```

Add directly below it:

```python
WHISPER_BASE = os.environ.get("WHISPER_URL", "http://localhost:9000")
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.live.yml docker-compose.test.yml incarnation_server.py
git commit -m "chore(infra): add Whisper STT container + WHISPER_URL env"
```

---

## Task 2: Backend `POST /api/stt/proxy` endpoint (TDD)

**Files:**
- Modify: `incarnation_server.py` (new route alongside `/api/tts/proxy`)
- Test: `tests/integration/test_stt_proxy.py` (new)

Endpoint takes a `multipart/form-data` upload with field name `audio`, forwards the bytes to `WHISPER_BASE/asr` (multipart field `audio_file`), and returns `{"text": str, "language": str}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_stt_proxy.py`:

```python
"""Integration tests for POST /api/stt/proxy.

Verifies the proxy forwards audio uploads to the Whisper container
(mocked via respx) and returns the transcribed text + detected language.
"""
from __future__ import annotations

import io

import pytest
import respx
from httpx import Response
from fastapi.testclient import TestClient

from incarnation_server import IncarnationServer

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    server = IncarnationServer(callback=lambda _msg: None)
    return TestClient(server.app)


@respx.mock
def test_stt_proxy_happy_path(client):
    """Forwards audio to Whisper, returns text + language."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(
            200,
            json={"text": "hello there", "language": "en"},
        )
    )

    fake_audio = io.BytesIO(b"RIFF....fake-wav-bytes")
    response = client.post(
        "/api/stt/proxy",
        files={"audio": ("clip.wav", fake_audio, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"text": "hello there", "language": "en"}


@respx.mock
def test_stt_proxy_upstream_error_returns_502(client):
    """Whisper down / 5xx → proxy responds 502 with a clear detail string."""
    respx.post("http://localhost:9000/asr").mock(
        return_value=Response(503, text="model loading"),
    )

    fake_audio = io.BytesIO(b"junk")
    response = client.post(
        "/api/stt/proxy",
        files={"audio": ("clip.wav", fake_audio, "audio/wav")},
    )

    assert response.status_code == 502
    assert "STT" in response.json()["detail"]


def test_stt_proxy_missing_audio_field_returns_422(client):
    """Missing `audio` form field → FastAPI returns 422 (validation error)."""
    response = client.post("/api/stt/proxy", files={})
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_stt_proxy)" | head
```

Expected: 3 failures (route doesn't exist yet → 404 / unrecognized URL).

- [ ] **Step 3: Add the route to `incarnation_server.py`**

In `incarnation_server.py`, in the `_setup_routes` method (or wherever `/api/tts/proxy` is registered — directly above or below it), add:

```python
        @self.app.post("/api/stt/proxy")
        async def proxy_stt(audio: UploadFile = File(...)):
            """
            Forwards an audio upload to the Whisper container and returns
            its transcription + detected language. Symmetric with
            /api/tts/proxy: the Whisper container is never directly
            reachable from the browser.
            """
            try:
                audio_bytes = await audio.read()
                async with httpx.AsyncClient() as client:
                    upstream = await client.post(
                        f"{WHISPER_BASE}/asr",
                        files={"audio_file": (audio.filename or "clip.wav",
                                              audio_bytes,
                                              audio.content_type or "audio/wav")},
                        params={"output": "json"},
                        timeout=30.0,
                    )
                if upstream.status_code != 200:
                    logger.error(f"STT upstream error: {upstream.status_code} {upstream.text!r}")
                    raise HTTPException(
                        status_code=502,
                        detail=f"STT upstream error: {upstream.status_code}",
                    )
                data = upstream.json()
                return {
                    "text": data.get("text", "").strip(),
                    "language": data.get("language", ""),
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.exception(f"STT Proxy error: {e}")
                raise HTTPException(status_code=502, detail=f"STT Proxy error: {e}")
```

If `UploadFile` and `File` aren't already imported at the top of the file, add:

```python
from fastapi import UploadFile, File
```

(They should already be imported because `/api/personas/{persona_id}/model` uses them at line ~131.)

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `86 passed, 3 deselected` (was 83; +3 new tests).

- [ ] **Step 5: Commit**

```bash
git add incarnation_server.py tests/integration/test_stt_proxy.py
git commit -m "feat(server): add /api/stt/proxy endpoint forwarding to Whisper"
```

---

## Task 3: WS handler for `user_input` (TDD)

**Files:**
- Modify: `playAIdes.py` (`_handle_incarnation_message`, after the existing `model_loaded` branch)
- Test: `tests/integration/test_user_input_ws.py` (new)

When the browser sends `{type: "user_input", payload: {text: "..."}}`, route to `self.chat(text)`. Phase 1 already makes `chat()` emit `assistant_message` and (when voice is on) `start_lip_sync`, so no further server-side wiring is needed for the reply.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_user_input_ws.py`:

```python
"""Integration test: incoming `user_input` WS messages route to PlayAIdes.chat()."""
from __future__ import annotations

import json

import pytest

from playAIdes import PlayAIdes, PlayAIdesArgs
from model_interfaces import MockLLM

pytestmark = pytest.mark.integration


@pytest.fixture
def play(persona_file, fake_tts, no_incarnation):
    args = PlayAIdesArgs(
        persona=[str(persona_file)],
        generate_voice=False,
        use_voice=False,
        use_avatar=True,
        generate_avatar=False,
        llm=MockLLM(),
        tts=fake_tts,
    )
    return PlayAIdes(args)


def test_user_input_routes_to_chat(play):
    """A `user_input` WS message triggers chat() and the assistant_message
    broadcast path that Phase 1 already wired."""
    play._handle_incarnation_message({
        "type": "user_input",
        "payload": {"text": "hello there"},
    })

    cmds = play.incarnation_server.commands
    assistant_messages = [
        (cmd, payload) for cmd, payload in cmds if cmd == "assistant_message"
    ]
    assert len(assistant_messages) == 1
    _, payload = assistant_messages[0]
    assert payload["text"]  # MockLLM returns a non-empty string


def test_user_input_ignores_empty_text(play):
    """Empty / whitespace-only utterances drop silently (don't waste an LLM round-trip)."""
    play._handle_incarnation_message({
        "type": "user_input",
        "payload": {"text": "   "},
    })
    cmds = play.incarnation_server.commands
    assistant_messages = [c for c, _ in cmds if c == "assistant_message"]
    assert assistant_messages == []


def test_user_input_missing_text_does_not_crash(play):
    """Malformed payload (no `text` key) is ignored, not raised."""
    play._handle_incarnation_message({
        "type": "user_input",
        "payload": {},
    })  # Should not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test 2>&1 | grep -E "(FAILED|test_user_input)" | head
```

Expected: at least `test_user_input_routes_to_chat` fails because no handler exists for `user_input` yet.

- [ ] **Step 3: Add the handler to `_handle_incarnation_message`**

In `playAIdes.py`, the `_handle_incarnation_message` method has a series of `if msg_type == "...":` branches (around lines 226–245 — `get_personas`, `get_persona`, `set_persona`, etc.). Add a new branch directly after the `if msg_type == "get_persona":` block, before any of the deeper `state == ...` logic:

```python
        if msg_type == "user_input":
            text = (payload.get("text") or "").strip()
            if not text:
                return
            try:
                self.chat(text)
            except Exception as e:
                logger.exception(f"user_input chat() failed: {e}")
            return
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test 2>&1 | tail -3
```

Expected: `89 passed, 3 deselected` (was 86; +3 new tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/integration/test_user_input_ws.py
git commit -m "feat: route user_input WS message to PlayAIdes.chat()"
```

---

## Task 4: Frontend `audioCapture.js` — mic + energy-threshold VAD

**Files:**
- Create: `incarnation/src/audioCapture.js`
- Test: `incarnation/src/audioCapture.test.js`

Pure-ish module. Wraps `getUserMedia` + `AudioContext` + `AnalyserNode` + `MediaRecorder`. Exposes:
- `start()` — async, opens mic + recorder.
- `stop()` — closes everything.
- Events: `voicestart` (no detail), `voiceend` (`{ detail: { blob } }`).

The VAD logic — measuring RMS energy on a Float32Array and bouncing between voice / silence states — is split out into a pure helper `detectVoiceState(...)` so it can be unit-tested without DOM APIs.

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/audioCapture.test.js`:

```js
import { describe, it, expect } from 'vitest';
import { detectVoiceState } from './audioCapture.js';

describe('detectVoiceState', () => {
    it('returns silent when energy is below threshold', () => {
        const result = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
            now: 1000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(result.event).toBe(null);
        expect(result.currentlyVoice).toBe(false);
    });

    it('emits voicestart after sustained voice above threshold', () => {
        // First tick crosses threshold, voiceStartedAt is set, no event yet.
        const t1 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
            now: 1000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t1.event).toBe(null);
        expect(t1.voiceStartedAt).toBe(1000);

        // 250ms later, still above threshold → voicestart fires.
        const t2 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: t1.voiceStartedAt,
            silenceStartedAt: null,
            now: 1250,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe('voicestart');
        expect(t2.currentlyVoice).toBe(true);
    });

    it('emits voiceend after sustained silence following voice', () => {
        // Already in voice, silence just started.
        const t1 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: null,
            now: 2000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t1.event).toBe(null);
        expect(t1.silenceStartedAt).toBe(2000);

        // 900ms later, still silent → voiceend fires.
        const t2 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: t1.silenceStartedAt,
            now: 2900,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe('voiceend');
        expect(t2.currentlyVoice).toBe(false);
    });

    it('cancels pending voicestart if energy drops before minVoiceMs', () => {
        const t1 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
            now: 1000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t1.voiceStartedAt).toBe(1000);

        // 100ms later, energy drops back below threshold → voiceStartedAt clears.
        const t2 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: t1.voiceStartedAt,
            silenceStartedAt: null,
            now: 1100,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe(null);
        expect(t2.voiceStartedAt).toBe(null);
    });

    it('cancels pending voiceend if voice resumes before silenceMs', () => {
        const t1 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: null,
            now: 2000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        // Brief silence pause, then voice returns within 300ms.
        const t2 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: t1.silenceStartedAt,
            now: 2300,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe(null);
        expect(t2.silenceStartedAt).toBe(null);
    });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -10
```

Expected: 5 failures with "module not found" (the file doesn't exist yet).

- [ ] **Step 3: Create `incarnation/src/audioCapture.js`**

```js
/**
 * audioCapture.js — mic capture + energy-threshold VAD.
 *
 * Lifecycle:
 *   const cap = new AudioCapture({ silenceThreshold: 0.02, ... });
 *   cap.addEventListener('voicestart', () => { ... });
 *   cap.addEventListener('voiceend', (e) => sttSend(e.detail.blob));
 *   await cap.start();   // requests mic permission
 *
 * `detectVoiceState` is exported as a pure function so the bouncing
 * between silent / voice states can be unit-tested without DOM APIs.
 */

const DEFAULTS = Object.freeze({
    silenceThreshold: 0.02,   // RMS energy [0,1] below this is "silence"
    minVoiceMs: 200,          // need this much sustained voice before voicestart
    silenceMs: 800,           // need this much sustained silence before voiceend
    pollIntervalMs: 50,       // how often we sample the analyser
    fftSize: 1024,
});

/**
 * Pure VAD state machine — call once per audio sample tick.
 *
 * @param {object} args
 * @param {number} args.energy             RMS energy of the current sample
 * @param {number} args.silenceThreshold
 * @param {boolean} args.currentlyVoice
 * @param {number|null} args.voiceStartedAt   ms timestamp when a candidate voice run began
 * @param {number|null} args.silenceStartedAt ms timestamp when a candidate silence run began
 * @param {number} args.now
 * @param {number} args.minVoiceMs
 * @param {number} args.silenceMs
 *
 * @returns {{event: 'voicestart'|'voiceend'|null, currentlyVoice: boolean,
 *           voiceStartedAt: number|null, silenceStartedAt: number|null}}
 */
export function detectVoiceState({
    energy, silenceThreshold,
    currentlyVoice, voiceStartedAt, silenceStartedAt,
    now, minVoiceMs, silenceMs,
}) {
    const isVoice = energy >= silenceThreshold;

    if (!currentlyVoice) {
        // Looking for sustained voice to fire voicestart.
        if (isVoice) {
            if (voiceStartedAt === null) {
                return { event: null, currentlyVoice: false,
                         voiceStartedAt: now, silenceStartedAt: null };
            }
            if (now - voiceStartedAt >= minVoiceMs) {
                return { event: 'voicestart', currentlyVoice: true,
                         voiceStartedAt, silenceStartedAt: null };
            }
            return { event: null, currentlyVoice: false,
                     voiceStartedAt, silenceStartedAt: null };
        }
        // Below threshold — clear any pending voice run.
        return { event: null, currentlyVoice: false,
                 voiceStartedAt: null, silenceStartedAt: null };
    }

    // Already in voice — looking for sustained silence to fire voiceend.
    if (!isVoice) {
        if (silenceStartedAt === null) {
            return { event: null, currentlyVoice: true,
                     voiceStartedAt, silenceStartedAt: now };
        }
        if (now - silenceStartedAt >= silenceMs) {
            return { event: 'voiceend', currentlyVoice: false,
                     voiceStartedAt: null, silenceStartedAt: null };
        }
        return { event: null, currentlyVoice: true,
                 voiceStartedAt, silenceStartedAt };
    }
    // Voice resumed — cancel any pending silence run.
    return { event: null, currentlyVoice: true,
             voiceStartedAt, silenceStartedAt: null };
}

/** Compute RMS energy [0,1] from a Float32 time-domain frame. */
function rms(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
}

export class AudioCapture extends EventTarget {
    constructor(options = {}) {
        super();
        this.config = { ...DEFAULTS, ...options };
        this.stream = null;
        this.audioContext = null;
        this.analyser = null;
        this.recorder = null;
        this.pollTimer = null;
        this._chunks = [];
        this._vadState = {
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
        };
    }

    async start() {
        if (this.stream) return;   // idempotent
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true },
        });
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = this.audioContext.createMediaStreamSource(this.stream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = this.config.fftSize;
        source.connect(this.analyser);

        // Pick a mime type the browser supports. webm/opus is universal in
        // Chromium; Firefox prefers ogg/opus. Whisper handles both.
        let mimeType = 'audio/webm;codecs=opus';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'audio/ogg;codecs=opus';
        }
        this.recorder = new MediaRecorder(this.stream, { mimeType });
        this.recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) this._chunks.push(e.data);
        };
        this.recorder.onstop = () => {
            const blob = new Blob(this._chunks, { type: this.recorder.mimeType });
            this._chunks = [];
            this.dispatchEvent(new CustomEvent('voiceend', { detail: { blob } }));
        };

        const buf = new Float32Array(this.analyser.fftSize);
        this.pollTimer = setInterval(() => this._tick(buf), this.config.pollIntervalMs);
    }

    _tick(buf) {
        this.analyser.getFloatTimeDomainData(buf);
        const energy = rms(buf);
        const next = detectVoiceState({
            energy,
            silenceThreshold: this.config.silenceThreshold,
            currentlyVoice: this._vadState.currentlyVoice,
            voiceStartedAt: this._vadState.voiceStartedAt,
            silenceStartedAt: this._vadState.silenceStartedAt,
            now: performance.now(),
            minVoiceMs: this.config.minVoiceMs,
            silenceMs: this.config.silenceMs,
        });
        this._vadState = {
            currentlyVoice: next.currentlyVoice,
            voiceStartedAt: next.voiceStartedAt,
            silenceStartedAt: next.silenceStartedAt,
        };

        if (next.event === 'voicestart') {
            this._chunks = [];
            this.recorder.start();
            this.dispatchEvent(new CustomEvent('voicestart'));
        } else if (next.event === 'voiceend') {
            this.recorder.stop();   // triggers onstop → emits voiceend with blob
        }
    }

    async stop() {
        if (this.pollTimer) clearInterval(this.pollTimer);
        if (this.recorder && this.recorder.state !== 'inactive') this.recorder.stop();
        if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
        if (this.audioContext) await this.audioContext.close();
        this.stream = null;
        this.audioContext = null;
        this.analyser = null;
        this.recorder = null;
    }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -15
```

Expected: `Test Files  3 passed (3) / Tests  47 passed (47)` (was 42 — added 5 detectVoiceState tests).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/audioCapture.js incarnation/src/audioCapture.test.js
git commit -m "feat(viewer): mic capture + energy-threshold VAD module"
```

---

## Task 5: Frontend `sttClient.js` — POST audio to `/api/stt/proxy`

**Files:**
- Create: `incarnation/src/sttClient.js`
- Test: `incarnation/src/sttClient.test.js`

Tiny module. Single function: `transcribe(blob)` returns `{ text, language }`.

- [ ] **Step 1: Write the failing tests**

Create `incarnation/src/sttClient.test.js`:

```js
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SttClient } from './sttClient.js';

describe('SttClient.transcribe', () => {
    let originalFetch;

    beforeEach(() => {
        originalFetch = global.fetch;
    });

    afterEach(() => {
        global.fetch = originalFetch;
    });

    it('POSTs the blob as multipart and returns the parsed JSON', async () => {
        const fakeFetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ text: 'hello there', language: 'en' }),
        });
        global.fetch = fakeFetch;

        const client = new SttClient('http://api.test:8765');
        const blob = new Blob(['fake-audio-bytes'], { type: 'audio/webm' });
        const result = await client.transcribe(blob);

        expect(result).toEqual({ text: 'hello there', language: 'en' });
        expect(fakeFetch).toHaveBeenCalledTimes(1);
        const [url, init] = fakeFetch.mock.calls[0];
        expect(url).toBe('http://api.test:8765/api/stt/proxy');
        expect(init.method).toBe('POST');
        expect(init.body).toBeInstanceOf(FormData);
        expect(init.body.get('audio')).toBeInstanceOf(Blob);
    });

    it('throws on non-2xx responses', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 502,
            text: async () => 'STT upstream error',
        });

        const client = new SttClient('http://api.test:8765');
        const blob = new Blob([''], { type: 'audio/webm' });
        await expect(client.transcribe(blob)).rejects.toThrow(/502/);
    });

    it('strips trailing slashes from the API base', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ text: '', language: '' }),
        });

        const client = new SttClient('http://api.test:8765/');
        await client.transcribe(new Blob([], { type: 'audio/webm' }));

        const [url] = global.fetch.mock.calls[0];
        expect(url).toBe('http://api.test:8765/api/stt/proxy');
    });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
make test-js 2>&1 | tail -15
```

Expected: 3 failures with module-not-found.

- [ ] **Step 3: Create `incarnation/src/sttClient.js`**

```js
/**
 * sttClient.js — POSTs an audio blob to the server's /api/stt/proxy
 * and returns the transcription.
 *
 * The server forwards to the Whisper container; the browser never
 * talks to Whisper directly. Symmetric with the existing TTS proxy.
 */
export class SttClient {
    /** @param {string} apiBase  e.g. "http://localhost:8765" */
    constructor(apiBase) {
        this.apiBase = String(apiBase).replace(/\/+$/, '');
    }

    /**
     * Send an audio blob and resolve to the transcript.
     * @param {Blob} blob
     * @returns {Promise<{text: string, language: string}>}
     */
    async transcribe(blob) {
        const form = new FormData();
        form.append('audio', blob, 'utterance.webm');

        const response = await fetch(`${this.apiBase}/api/stt/proxy`, {
            method: 'POST',
            body: form,
        });
        if (!response.ok) {
            const detail = await response.text().catch(() => '');
            throw new Error(`STT proxy ${response.status}: ${detail || 'unknown error'}`);
        }
        return response.json();
    }
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files  4 passed (4) / Tests  50 passed (50)` (was 47 — added 3 sttClient tests).

- [ ] **Step 5: Commit**

```bash
git add incarnation/src/sttClient.js incarnation/src/sttClient.test.js
git commit -m "feat(viewer): STT client wrapping /api/stt/proxy"
```

---

## Task 6: Wire LISTENING / THINKING into the orchestrator

**Files:**
- Modify: `incarnation/src/viewer.js`

Manual verification only — DOM + WebSocket + mic permissions can't be exercised in node Vitest.

- [ ] **Step 1: Add imports near the top of `viewer.js`**

In `incarnation/src/viewer.js`, alongside the existing imports, add:

```js
import { AudioCapture } from './audioCapture.js';
import { SttClient } from './sttClient.js';
```

- [ ] **Step 2: Construct the audio capture and STT client at boot**

In `viewer.js`, just below the existing `const connection = new ConnectionManager();` line, add:

```js
const audioCapture = new AudioCapture();
const stt = new SttClient(config.apiBase);

// Last user utterance text — populated when STT returns, attached to the
// THINKING state's meta so the subtitle band can render it (greyed).
let lastUserUtterance = '';
```

- [ ] **Step 3: Wire `voicestart` and `voiceend` to the state machine**

After the existing `connection.addEventListener('stop_lip_sync', ...)` block (and before the generic `'message'` catch-all) add:

```js
// ── Voice input → LISTENING → THINKING → user_input WS send ───────────────
audioCapture.addEventListener('voicestart', () => {
    if (stateMachine.current === State.AMBIENT || stateMachine.current === State.EMPTY) {
        safeTransition(State.LISTENING);
    }
});

audioCapture.addEventListener('voiceend', async (e) => {
    if (stateMachine.current !== State.LISTENING) return;
    safeTransition(State.THINKING, { lastUtterance: '…' });
    try {
        const { text } = await stt.transcribe(e.detail.blob);
        lastUserUtterance = (text || '').trim();
        if (!lastUserUtterance) {
            // No speech detected — just bounce back to AMBIENT.
            safeTransition(State.AMBIENT);
            return;
        }
        // Update THINKING meta with the actual transcript so the subtitle
        // band can show what was heard while the LLM is in flight.
        stateMachine.transition(State.THINKING, { lastUtterance: lastUserUtterance });
        connection.send('user_input', { text: lastUserUtterance });
        // The reply comes back via assistant_message + start_lip_sync,
        // already wired in Phase 1 — no further action needed here.
    } catch (err) {
        console.error('[viewer] STT failed:', err);
        safeTransition(State.AMBIENT);
    }
});
```

Note: `stateMachine.transition(State.THINKING, ...)` from a THINKING state isn't strictly a transition — it's a meta refresh. The current `viewerState.js` rejects same-state "transitions". The simplest workaround for Phase 2 is to update `viewerState.js` to allow same-state transitions (for meta refresh) — but that's a contract change. Instead, dispatch a synthetic `change` event manually for the meta update. Replace the `stateMachine.transition(State.THINKING, ...)` line above with:

```js
        // Meta refresh inside THINKING — dispatch a synthetic change event
        // so the overlay layer can re-render the subtitle text. (Same-state
        // transitions are illegal in the state machine by design.)
        stateMachine.dispatchEvent(new CustomEvent('change', {
            detail: {
                prev: State.THINKING, next: State.THINKING,
                prevMeta: { lastUtterance: '…' },
                meta: { lastUtterance: lastUserUtterance },
            },
        }));
```

- [ ] **Step 4: Start mic capture on the first user gesture**

Modify the existing `unlockAudio` function in `viewer.js` to also kick off mic capture. Replace:

```js
async function unlockAudio() {
    GESTURES.forEach((t) => window.removeEventListener(t, unlockAudio, true));
    if (incarnation.lipSyncManager) {
        await incarnation.lipSyncManager.resume();
    }
    console.log('[viewer] audio unlocked');
}
```

with:

```js
async function unlockAudio() {
    GESTURES.forEach((t) => window.removeEventListener(t, unlockAudio, true));
    if (incarnation.lipSyncManager) {
        await incarnation.lipSyncManager.resume();
    }
    try {
        await audioCapture.start();
        console.log('[viewer] mic + audio unlocked');
    } catch (err) {
        // Permission denied or no mic — viewer remains usable but no voice in.
        console.warn('[viewer] mic unavailable:', err);
    }
}
```

- [ ] **Step 5: Manual verification**

Restart the dev server and the Python backend:

```bash
npm --prefix incarnation run dev
# in another terminal:
python main.py --persona personas/silver/persona.json --use_avatar
```

Open `http://localhost:5173/?activation=continuous`. Click anywhere on the page (audio + mic gesture), grant the mic prompt. Then speak.

Expected sequence in DevTools console:
1. `[viewer] mic + audio unlocked`
2. While speaking: mic dot turns crimson + fast pulses (LISTENING)
3. After ~800ms silence: mic dot turns gold + spins (THINKING). A POST to `/api/stt/proxy` appears in the Network tab and returns `{text, language}`.
4. `connection.send('user_input', ...)` fires
5. Server replies with `assistant_message` + `start_lip_sync` → mic dot dim-red + subtitle band renders the persona's reply (SPEAKING)
6. After audio ends: back to dim-gold pulse (AMBIENT). Subtitle fades out 2 s later.

If you see "STT proxy 502", Whisper isn't running — see Task 8 for the live stack.

- [ ] **Step 6: Commit**

```bash
git add incarnation/src/viewer.js
git commit -m "feat(viewer): wire LISTENING and THINKING via mic + STT proxy"
```

---

## Task 7: Subtitle band shows live transcript during LISTENING and THINKING

**Files:**
- Modify: `incarnation/src/viewerOverlays.js`
- Modify: `incarnation/styles/viewer.css`

Phase 1's `viewerOverlays._onStateChange` only populates the subtitle band during SPEAKING. Spec §4 says it should also show:
- LISTENING: a faded "listening…" placeholder, replaced with the final transcript when STT returns.
- THINKING: the last user utterance, in greyed style.

- [ ] **Step 1: Extend `_onStateChange` in `viewerOverlays.js`**

Open `incarnation/src/viewerOverlays.js`. The current `_onStateChange` only renders subtitle for SPEAKING. Replace its body with:

```js
    _onStateChange({ next, meta }) {
        // Mic indicator: color/animation per state. CSS owns the actual
        // styling — we just attach a class.
        if (this.elMic && !this.elMic.hidden) {
            this.elMic.className = 'mic-indicator state-' + next.toLowerCase();
        }

        if (this.elSubtitle && !this.elSubtitle.hidden) {
            this._renderSubtitle(next, meta);
        }
    }

    _renderSubtitle(next, meta) {
        const setText = (text, klass) => {
            if (this.elSubText) this.elSubText.textContent = text;
            this.elSubtitle.classList.remove('user', 'placeholder');
            if (klass) this.elSubtitle.classList.add(klass);
        };

        clearTimeout(this._subtitleTimer);

        if (next === State.LISTENING) {
            const transcript = (meta && meta.lastUtterance) || '';
            setText(transcript || 'listening…', transcript ? 'user' : 'placeholder');
            this.elSubtitle.classList.add('visible');
            return;
        }
        if (next === State.THINKING) {
            const transcript = (meta && meta.lastUtterance) || '…';
            setText(transcript, 'user');
            this.elSubtitle.classList.add('visible');
            return;
        }
        if (next === State.SPEAKING) {
            setText((meta && meta.text) || '', null);
            this.elSubtitle.classList.add('visible');
            return;
        }
        // AMBIENT / EMPTY / INTRO — fade out over the next SUBTITLE_FADE_MS.
        this._subtitleTimer = setTimeout(() => {
            this.elSubtitle.classList.remove('visible');
            this.elSubtitle.classList.remove('user', 'placeholder');
        }, SUBTITLE_FADE_MS);
    }
```

- [ ] **Step 2: Add styles for the new subtitle variants**

In `incarnation/styles/viewer.css`, find the existing `.subtitle-band.visible { opacity: 1; }` rule. Directly below it add:

```css
/* User-utterance variant (LISTENING / THINKING) — greyed, italic. */
.subtitle-band.user {
    color: var(--cream-dim);
    font-style: italic;
    border-color: var(--gold-dim);
}

/* Placeholder variant (LISTENING with no transcript yet). */
.subtitle-band.placeholder {
    color: var(--gold-dim);
    font-family: 'Chakra Petch', sans-serif;
    font-size: 14px;
    letter-spacing: .2em;
    text-transform: lowercase;
    font-style: normal;
    border-color: var(--gold-dim);
}
```

- [ ] **Step 3: Manual verification**

Reload the viewer. Speak a sentence. Confirm:
- During LISTENING: subtitle band shows `listening…` in dim gold, P5-style chip look.
- During THINKING: subtitle band shows the transcribed text in greyed italic with a thin gold-dim border.
- During SPEAKING: subtitle band shows the persona's reply in full crimson + Cinzel font (Phase 1 styling unchanged).
- After AMBIENT: subtitle fades out after 2 s.

- [ ] **Step 4: Commit**

```bash
git add incarnation/src/viewerOverlays.js incarnation/styles/viewer.css
git commit -m "feat(viewer): subtitle band renders LISTENING + THINKING states"
```

---

## Task 8: Live smoke test against the real Whisper container

**Files:**
- Create: `tests/live/test_whisper_live.py`
- Create: `tests/live/test_clips/hello_en.wav` (a short test audio file — see step 1)

- [ ] **Step 1: Generate / source a 1–2 second WAV containing "hello"**

We need a tiny English clip checked in for reproducible tests. The fastest path is to record one from your own mic via any tool (system recorder, Audacity), trim to ~1.5 s, export as 16-bit PCM WAV at 16 kHz mono. Save to `tests/live/test_clips/hello_en.wav`. Aim for under 50 KB.

If you'd rather skip this and rely on a synthetic tone, you can substitute Whisper's behavior with a known result, but a real human "hello" is the most useful smoke. Commit the file.

(For a Japanese smoke, source a 1–2 s clip of `こんにちは` similarly to `tests/live/test_clips/hello_ja.wav`. Optional for Phase 2 — English is enough to prove the pipe.)

- [ ] **Step 2: Write the live test**

Create `tests/live/test_whisper_live.py`:

```python
"""Live smoke test: real Whisper container in docker-compose.live.yml.

Skips automatically when WHISPER_URL is unset (i.e. when running the
default `make test` rather than `make test-live`).
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.live

WHISPER_URL = os.environ.get("WHISPER_URL")
CLIPS_DIR = Path(__file__).parent / "test_clips"


@pytest.fixture
def stt_proxy_url():
    """The STT proxy URL on the test container's incarnation_server."""
    # Live tests run incarnation_server in-process via the test container,
    # so we hit the localhost route. Same pattern as existing live tests.
    return "http://localhost:8765/api/stt/proxy"


@pytest.mark.skipif(not WHISPER_URL, reason="WHISPER_URL not set — skip live STT test")
def test_whisper_transcribes_english(stt_proxy_url):
    """Real Whisper round-trip on a tiny English clip."""
    clip = CLIPS_DIR / "hello_en.wav"
    assert clip.exists(), f"missing test clip: {clip}"

    with clip.open("rb") as f:
        with httpx.Client(timeout=30.0) as c:
            response = c.post(
                stt_proxy_url,
                files={"audio": ("hello_en.wav", f, "audio/wav")},
            )

    assert response.status_code == 200
    body = response.json()
    text = body.get("text", "").lower()
    # We don't pin the exact transcript (Whisper's "base" model isn't perfect)
    # but a short clip of "hello" should produce *something* and detect English.
    assert text, f"empty transcript: {body!r}"
    assert body.get("language") == "en"
```

- [ ] **Step 3: Wire `WHISPER_URL` into `docker-compose.live.yml` test stack**

In `docker-compose.live.yml`, the existing `tts` service has its own healthcheck and the live test runner reads `TTS_URL=http://tts:8000`. The `whisper` service from Task 1 doesn't have an env-var injection yet. Add to the `tests` service in the live overlay (if there's an explicit `tests` override in `docker-compose.live.yml`) or as an env in the live `make test-live` target. Search the file for `TTS_URL=`:

```yaml
      - TTS_URL=http://tts:8000
```

If you find it, add directly below:

```yaml
      - WHISPER_URL=http://whisper:9000
```

If `docker-compose.live.yml` doesn't currently override the `tests` service env, add this minimal block:

```yaml
  tests:
    environment:
      - TTS_URL=http://tts:8000
      - WHISPER_URL=http://whisper:9000
      - OLLAMA_URL=http://ollama:11434
```

- [ ] **Step 4: Run the live test**

Pre-pull and warm the Whisper image; the first run downloads the `base` model (~150 MB) and can take a couple of minutes:

```bash
docker compose -f docker-compose.test.yml -f docker-compose.live.yml up -d whisper
# wait for healthcheck — ~60 s on cold cache
docker compose -f docker-compose.test.yml -f docker-compose.live.yml run --rm tests pytest tests/live/test_whisper_live.py -v
docker compose -f docker-compose.test.yml -f docker-compose.live.yml down
```

Expected: `tests/live/test_whisper_live.py::test_whisper_transcribes_english PASSED`.

- [ ] **Step 5: Commit**

```bash
git add tests/live/test_whisper_live.py tests/live/test_clips/ docker-compose.live.yml
git commit -m "test(live): smoke-test Whisper container via /api/stt/proxy"
```

---

## Task 9: End-to-end smoke + final review

**Files:**
- None — verification + final review only.

- [ ] **Step 1: Backend tests still green**

```bash
make test 2>&1 | tail -3
```

Expected: `89 passed, 3 deselected` (75 baseline + 7 from Phase 1 + 6 from Phase 2 = 88 — adjust if Phase 1 count drifted).

- [ ] **Step 2: JS tests still green**

```bash
make test-js 2>&1 | tail -10
```

Expected: `Test Files  4 passed (4) / Tests  50 passed (50)` (Phase 1's 42 plus Task 4's 5 plus Task 5's 3).

- [ ] **Step 3: Live voice round-trip**

In separate terminals:

```bash
# Terminal 1 — full live stack:
docker compose -f docker-compose.test.yml -f docker-compose.live.yml up -d ollama tts whisper
docker compose -f docker-compose.test.yml -f docker-compose.live.yml run --rm ollama-model-pull || true
```

```bash
# Terminal 2 — Python backend talking to the live containers:
OLLAMA_URL=http://localhost:11434 TTS_URL=http://localhost:8009 WHISPER_URL=http://localhost:9000 \
    python main.py --persona personas/silver/persona.json --use_avatar
```

```bash
# Terminal 3 — Vite dev server:
npm --prefix incarnation run dev
```

Open `http://localhost:5173/?activation=continuous` in Chrome (use Chrome — Firefox's `getUserMedia` quirks aren't worth debugging in v1). Click anywhere, grant mic permission, then speak: *"Hello Silver, what's the weather like in your land?"*

Expected sequence (the same five-state arc described in spec §2):
1. **AMBIENT** — dim-gold mic pulse, idle anim.
2. **LISTENING** — crimson fast pulse + glow, subtitle shows `listening…`.
3. **THINKING** — gold spinning ring, subtitle shows your transcribed sentence in greyed italic.
4. **SPEAKING** — dim-red dot, subtitle shows Silver's reply in full crimson, lip sync drives the mouth, audio plays.
5. Back to **AMBIENT** — subtitle fades out 2 s after audio ends.

If any step fails, the DevTools console + Network tab will show:
- `[viewer] →` state-transition log lines
- `POST /api/stt/proxy` request + 200 / 502 status
- WS frames in the Network → WS tab

- [ ] **Step 4: Self-review against spec §10 Phase 2 row**

Confirm each Phase-2 bullet from the spec maps to a task above:

- "Whisper container (multilingual `base` model)" → Task 1
- "/api/stt/proxy" → Task 2
- "Browser mic capture with VAD" → Task 4
- "New `LISTENING` and `THINKING` states wired" → Tasks 6, 7
- "Voice in → PlayAIdes → voice out, in EN or JP" → Task 3 (server) + Task 6 (client) + Task 8 (live smoke)
- "`user_input` + `assistant_message` WS messages" → Task 3 (`user_input` server-side) + Phase 1 `assistant_message`

`persona_id` on `user_input` is deferred to Phase 4 (and called out at the top of this plan).

- [ ] **Step 5: Final consistency check**

Search the diff for the type / name consistency points the writing-plans skill calls out:

- `audioCapture.js` exports `AudioCapture` class + `detectVoiceState` function — both used at the names defined here.
- `sttClient.js` exports `SttClient` class with `transcribe(blob)` — the orchestrator calls exactly that.
- The orchestrator imports both modules with the names used in their files (no `Stt` vs `STT` drift).
- `connection.send('user_input', { text })` — server-side `_handle_incarnation_message` dispatches on `msg_type == "user_input"` and reads `payload.get("text")`. Names align.

- [ ] **Step 6: Commit (no changes — process marker)**

This step is a checkpoint. No files; nothing to commit.

---

## Self-review checklist (run before marking phase 2 done)

- [ ] **Spec coverage** — see Step 4 above; every Phase 2 bullet has a task.
- [ ] **No placeholders** — search the plan for `TBD`, `TODO`, `FIXME`. None exist.
- [ ] **Type / name consistency** — `AudioCapture`, `SttClient`, `transcribe`, `voicestart`, `voiceend`, `user_input`, `lastUtterance`, `WHISPER_BASE`, `WHISPER_URL` — each name appears with the same casing and shape across server, client, tests, and config. The `lastUtterance` meta key is the contract between `viewer.js` and `viewerOverlays.js._renderSubtitle`.
- [ ] **Whisper-down behavior** — the orchestrator's `voiceend` handler catches STT errors and bounces back to AMBIENT (Task 6 Step 3). Spec §9 calls for an "error" mic state in this case; that's a follow-up, not a Phase 2 deliverable.
- [ ] **VAD library hand-off** — energy-threshold VAD is the prototype per spec §9; if it proves flaky in real-world use, the swap to `@ricky0123/vad-web` is a one-file change in `audioCapture.js`. Not in Phase 2.
