# TTS-Consumer Migration → voicebox `/v1/*` — Design

- **Date:** 2026-06-09
- **Status:** Approved (design); ready for implementation plan.
- **Slice:** Backend re-architecture migration **item 4** (the TTS/STT consumer migration).
- **Related:** `docs/VOICEBOX_HTTP_API.md` (the target contract),
  `docs/superpowers/specs/2026-06-09-backend-frontend-architecture-redesign.md` (parent arch spec),
  `docs/superpowers/specs/2026-06-09-slice2-conversation-service-design.md` (the prior slice / pattern).

## 1. Context & problem

playAIdes' TTS consumer is written against a **removed** Python client. `playAIdes.py` still does:

```python
from voicebox_client import PersonaTTS, VoiceboxClient
from voicebox.api_models import VoiceDesignRequest, SpeechGenerationRequest
```

The voicebox project deleted that in-process `voicebox_client` API; voicebox is now a **decentralized,
OpenAI-style HTTP service** (`docs/VOICEBOX_HTTP_API.md`). Because the import target no longer exists,
**any test that imports `PlayAIdes` errors at collection time**, so the full `bin/test` suite is RED.
Dropping these imports and rewiring the consumer onto the HTTP contract is the keystone that makes the
suite collect green again.

### What is actually running (verified, 2026-06-09)

The contract doc describes the **target** API. The **running** harness does not serve it yet. Probing
the live harness `voicebox:8008` from inside the backend container:

| Endpoint | Result |
|---|---|
| `GET /health` | `{"status":"ok","backend":"kokoro","engine_loaded":true}` ← legacy shape |
| `GET /speakers` | **200** (legacy speaker list) |
| `POST /generate_stream`, `POST /design` | **422** (legacy routes exist) |
| `POST /v1/audio/speech`, `GET /v1/voices` | **404** (do not exist) |

So the baked `voicebox:kokoro` harness image is the **legacy monolith**, which the current proxy code
already targets and works against. The new `/v1/*` API exists only in `~/repo/voicebox` **source**
(HEAD `49123ef`, 2026-06-09) and is **multi-service**: a **registry** (`/v1/voices`, entrypoint
`voicebox`) plus **one rig per engine** (the shim app, `/v1/audio/speech`; the kokoro rig is CPU,
`clone_only`, with a *stub* `design_voice`). Real voice design is **qwen3 (GPU)**, absent from the
harness.

**Implication:** the cutover cannot be live-verified against the harness as-is. The moment the proxy
switches to `/v1/*`, the legacy server (no `/v1`) can no longer answer it. This slice therefore also
**stands up the new registry + CPU kokoro rig in the harness** to live-test the synth path, while the
GPU-bound qwen3 design path is migrated but live-tested later.

## 2. Goal & scope

**Goal:** migrate playAIdes' TTS consumer (synth, ref-audio, voice-design) onto the voicebox `/v1/*`
HTTP contract behind a single `TTSClient` seam in `backend/clients/`, mirroring the existing
`OpenAICompatLLM` pattern; drop the dead imports; restore a green `bin/test`.

**In scope**
- New `backend/clients/tts.py` — `TTSClient` (synth whole-file, synth stream, voice-design, ref-audio).
- Repoint `incarnation_server.py`'s `/api/tts/proxy` and `/api/speakers/{id}/ref_audio` to `/v1/*`.
- `persona.py`: rename `Voice.speaker_uuid` → `voice`; migrate `personas/silver/persona.json` (+ `.bak`).
- `playAIdes.py`: drop the dead imports; rewire `self.tts`, `_setup_voice`, the `design_voice` /
  `test_voice` WS handlers, and `speak_as_persona`.
- Stand up the new voicebox **registry + CPU kokoro rig** in the harness for a live synth test.
- Hermetic + live tests; confirm the full `bin/test` collects + passes in the plain container.

**Out of scope**
- The qwen3 (GPU) design rig deployment and its live test — deferred until the GPU is free.
- STT/whisper migration (separate; whisper is unaffected).
- Renaming the legacy console WS payload keys (`speaker_id`/`url`) — the parked console consumes them;
  only the `self.tts` calls behind those handlers are migrated.
- Any redesign of emotion/tags beyond passing the contract's `voicebox.tags` through.

## 3. Decisions (with rationale)

### D1 — `TTSClient` uses `httpx` (sync + async), tested with `respx`
The LLM seam (`OpenAICompatLLM`) is `requests` + `responses`. TTS differs: `/api/tts/proxy` is a FastAPI
**async streaming** route, and a blocking `requests` stream would stall the event loop. `httpx` provides
a sync client (for playAIdes' sync call sites) and an async client (for the streaming proxy) in one
library, and `incarnation_server.py` **already mocks httpx with `respx`**. One client, one mocking story,
no event-loop blocking.
*Rejected:* `requests`/`responses` to match the LLM client (would force blocking I/O inside the async
proxy, or a second HTTP stack just for streaming).

### D2 — Hard-cut the proxy to `/v1/*` (no dual legacy/new path)
Because the new kokoro rig is stood up in the harness, there is no need to keep the legacy
`/generate_stream` path alive behind a flag. Hard-cut is less code and a clearer seam.
*Rejected:* dual-path strangler with a runtime switch (unneeded once the new rig runs in the harness;
adds branching + config surface for a one-way migration).

### D3 — Three separated base URLs (registry / synth rig / design rig)
The `/v1/*` API is decentralized: ref-audio comes from the **registry**, synthesis from a **rig**, voice
design from the **qwen3 rig**. These are distinct services with distinct base URLs. `TTSClient` takes
three, each defaulting to an env var:
- `rig_url` ← `VOICEBOX_URL or TTS_URL` (synth; kokoro in the harness)
- `registry_url` ← `VOICEBOX_REGISTRY_URL`
- `design_url` ← `VOICEBOX_DESIGN_URL` (qwen3; may be unset until GPU-free)
*Rejected:* a single `VOICEBOX_URL` for everything (false in the decentralized contract; would break the
moment registry/rig/design are separate hosts, which they already are).

### D4 — `--generate_voice` / design: full migration, deferred live test
The design call moves fully onto `POST {design_url}/v1/audio/voice_design`. It is **not** stubbed or
error-only. Because the GPU is busy, no qwen3 rig is started now; the design path is covered by
mocked-client unit tests now and live-tested later by pointing `VOICEBOX_DESIGN_URL` at a real qwen3 rig.

### D5 — Hard rename `Voice.speaker_uuid` → `voice`; migrate the data files
The contract's identifier is the registry **voice UUID**, named `voice`. The persona field is hard-renamed
and `personas/silver/persona.json` (+ `.bak`) are rewritten to the new key. No pydantic back-compat alias.
*Rejected:* a `validation_alias` accepting both names (keeps two names alive indefinitely; this is a
single-operator app with a known, finite set of persona files, so a clean rename + data migration is
simpler and there is no external consumer to break).

### D6 — Remove the CLI-only speak path
`speak_as_persona`'s non-avatar `else` branch called the old `generate_speech_stream(...)` and discarded
its result. In this architecture the **browser/avatar is the audio sink**; there is no host-side playback.
The branch is **removed**: `speak_as_persona` only pushes the lip-sync proxy URL when an avatar + display
exist. **Behavior change:** `--use_voice` without `--use_avatar` now produces no audio. Documented here so
it is reversible if a host-playback mode is ever wanted.

### D7 — `/api/tts/proxy` derives the WAV sample rate from the response header
The legacy proxy hardcoded 24000 Hz in its streaming WAV header. The `/v1/audio/speech` pcm response sets
`Content-Type: audio/l16; rate=<sr>; channels=1`; the proxy now parses `<sr>` and builds the WAV header
from it (the contract says "trust the header"). Removes a latent wrong-pitch bug if a rig's sample rate
differs.

## 4. Component design

### 4.1 `backend/clients/tts.py` — `TTSClient`

Thin, stateless, env-driven. `class TTSError(RuntimeError)` for any backend failure (mirrors `LLMError`).
Maps voicebox error shapes (`{"detail": ...}`, 400/404/422/500) to `TTSError`.

| Method | Sync/async | HTTP call | Returns | Consumer |
|---|---|---|---|---|
| `synth(text, voice, *, tags="")` | sync | `POST {rig_url}/v1/audio/speech` `{input, voice, response_format:"wav", voicebox:{tags}}` | WAV `bytes` | `test_voice` WS |
| `synth_stream(text, voice, *, tags="")` | **async** | `POST {rig_url}/v1/audio/speech` `{…, response_format:"pcm"}` | `(sample_rate:int, AsyncIterator[bytes])` (PCM L16 chunks; rate from header) | `/api/tts/proxy` |
| `design_voice(name, instruct, text, gender, language)` | sync | `POST {design_url}/v1/audio/voice_design` `{name, instruct, text, gender, language}` | `voice` UUID `str` | `_setup_voice`, `design_voice` WS |
| `ref_audio(voice)` | async | `GET {registry_url}/v1/voices/{voice}/ref_audio` | WAV `bytes` | `/api/speakers/{voice}/ref_audio` |

Constructor: `TTSClient(rig_url=None, registry_url=None, design_url=None, timeout=...)`, each falling back
to its env var (D3). A `FakeTTS` test double (duck-typed: provides `synth`/`design_voice`) supports
service-level tests without HTTP.

### 4.2 `incarnation_server.py` proxy routes (repointed)
- `GET /api/tts/proxy?text=…&voice=…` → `TTSClient.synth_stream` → wrap PCM in a WAV header built from
  the response sample rate (D7) → `StreamingResponse(audio/wav)`. Query param renamed `speaker_id`→`voice`
  (the browser fetches the URL opaquely; only playAIdes produces it).
- `GET /api/speakers/{voice}/ref_audio` → `TTSClient.ref_audio` (registry) → `StreamingResponse(audio/wav)`.
  Path param renamed `speaker_id`→`voice`.

### 4.3 `persona.py`
```python
class Voice(BaseModel):
    voice: Optional[str] = None          # registry voice UUID (was speaker_uuid)
    voice_instruct: Optional[list[str]] = None
    def is_voice_valid(self) -> bool:
        return self.voice is not None
```
Data migration: `personas/silver/persona.json` + `.bak`, `persona_voice.speaker_uuid` → `persona_voice.voice`.

### 4.4 `playAIdes.py`
- Remove the two dead `import` lines (the keystone for green collection).
- `PlayAIdesArgs.tts: Optional[TTSClient]`; `validate_tts` reduced to a duck-typed check
  (`callable(getattr(v, "synth", None)) or callable(getattr(v, "design_voice", None))`) so `FakeTTS` and
  MagicMock doubles pass. `self.tts = args.tts or TTSClient()`.
- `_setup_voice`: `p.persona_voice.voice = self.tts.design_voice(name=p.name, instruct=…, text=p.back_ground, gender=p.gender, language=p.language)`.
- `design_voice` WS handler: `voice = self.tts.design_voice(…)`; `ref_audio_url = …/api/speakers/{voice}/ref_audio`; WS payload keys unchanged (D-out-of-scope).
- `test_voice` WS handler: `wav = self.tts.synth(text, voice)`; **write `wav` to `incarnation/public/outputs/tts/temp/<uuid>.wav`** ourselves; build the static URL.
- `speak_as_persona`: guard on `voice.voice`; avatar+display path builds `…/api/tts/proxy?text=…&voice={voice.voice}`; **remove the CLI-only `else` branch** (D6).

## 5. Data flow — live speak (unchanged shape, new upstream)
Silver replies → `speak_as_persona` pushes `start_lip_sync {url:/api/tts/proxy?text=…&voice=…}` → browser
GETs it → proxy `POST {kokoro-rig}/v1/audio/speech {input, voice, response_format:"pcm"}` → PCM L16 stream
→ WAV header (rate from the response header) → browser plays + lip-syncs.

## 6. Harness live-test setup
Stand up the new voicebox **registry** + **CPU kokoro rig** (from `~/repo/voicebox`) in the harness and
repoint the backend:
- `VOICEBOX_REGISTRY_URL` → the registry service
- `VOICEBOX_URL` → the kokoro rig (CPU)
- `VOICEBOX_DESIGN_URL` → unset (no qwen3 now)

Register a voice in the new registry (or use a kokoro preset) to obtain a valid `voice` UUID for the live
synth test. **Discovery step (first task of the plan):** inspect the new voicebox's own compose
(registry + CPU kokoro rig service, ~`:9008`) and how the kokoro rig maps a voice UUID → preset, before
wiring the harness compose. Do not assume Silver's legacy UUID exists in the new registry — it lives in the
legacy DB.

## 7. Test plan
- **Hermetic (`respx`)** — `TTSClient` per method: `synth` (wav bytes), `synth_stream` (pcm + sample-rate
  header parsing), `design_voice` (returns uuid), `ref_audio`, and error mapping (404/422/500/connection
  → `TTSError`). Proxy routes: `/api/tts/proxy` builds the correct `/v1/audio/speech` pcm request and
  WAV-wraps with the header's rate; `/api/speakers/{voice}/ref_audio` hits the registry. Persona: loads
  with `voice`; Silver's file parses.
- **Plain-container green** — with the dead import gone, the `import PlayAIdes` call-site tests
  (`_setup_voice`, `test_voice`, `speak_as_persona`) run in the plain `bin/test` container. **Verify the
  full suite now collects and passes** (the slice's success criterion).
- **Live (now)** — synth + ref_audio against the new CPU kokoro rig + registry in the harness.
- **Live (deferred, GPU-free)** — `design_voice` against a qwen3 rig via `VOICEBOX_DESIGN_URL`.

## 8. Success criteria
1. `playAIdes.py` no longer imports `voicebox_client` / `voicebox.api_models`.
2. Full `bin/test` **collects and passes** in the plain container (no harness needed for unit tests).
3. Live synth + ref_audio work in the harness against the new CPU kokoro rig + registry (Silver speaks).
4. The design path is code-complete on `/v1/audio/voice_design`, mock-tested, and ready to live-test when
   a qwen3 rig is available.

## 9. Open / deferred items
- **qwen3 design rig** live test — deferred (GPU busy).
- **Voice identity for the live synth test** — register-vs-preset decision resolved during the harness
  discovery step (§6).
- **Legacy console WS payload keys** (`speaker_id`/`url`) — left as-is; revisit if/when the console is
  un-parked.
- **Host-side CLI playback** — removed (D6); reintroduce only if a no-browser audio mode is ever needed.
