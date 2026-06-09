# Voicebox TTS — HTTP API Reference (for consumers)

**Audience:** any app/session that turns text into speech by calling Voicebox over plain HTTP.
**Status:** decentralized, OpenAI-style API. This documents the **complete target contract** so you can build against it once; an **availability column** (§6) tells you which engines are live today vs. coming.
**Auth:** none. All endpoints are open (no API key, no `Authorization` header).
**Content type:** `Content-Type: application/json` on POST bodies (except `POST /v1/voices`, which is multipart).

> **The one big idea:** every engine runs the *same* OpenAI-style shim, so `POST /v1/audio/speech` is **identical across all engines**. Design a voice once, then synthesize on whichever engine you want by pointing at that engine's base URL — same request body, same emotion tags, same response. Integrate against the uniform contract below and you need no per-engine code.

---

## 0. Base URLs (deployment-provided)

Voicebox is several services (a **registry** + one **rig** per engine). **Hosts and ports are deployment details and intentionally not specified here** — in production they sit behind a reverse proxy / gateway, and the actual ports may differ from any dev setup. Your deployment hands you the base URLs (via env var, gateway route, or service discovery). This doc uses two placeholders:

- **`$REGISTRY`** — base URL of the voice registry.
- **`$RIG`** — base URL of the engine rig you're calling. Point it at whichever engine you want (§6); the API is the same for all of them.

All paths below are relative to those. Examples assume you've set the placeholders, e.g. `REGISTRY=https://tts.example/registry` and `RIG=https://tts.example/qwen3` (or whatever your deployment exposes).

---

## 1. Architecture — who you talk to

| Service | Placeholder | Role |
|---|---|---|
| **Registry** | `$REGISTRY` | Voice catalog, reference-audio/text store, model catalog. |
| **A rig** (one per engine) | `$RIG` | Synthesis (+ voice design, on qwen3). Each engine has its own base URL; your deployment maps engine → URL. |

Rigs fetch voices from the registry themselves — you don't wire that up.

---

## 2. Quick start — the consumer flow

Three steps: **design a voice once → (optionally) look it up → synthesize as often as you like.** A voice is a UUID string returned by design; it carries its reference audio + transcript in the registry, so it works on **every** engine.

### Step 1 — Design a voice (point `$RIG` at qwen3 — the only engine that designs voices). Once per voice.
```bash
curl -sS -X POST "$RIG/v1/audio/voice_design" \
  -H 'content-type: application/json' \
  -d '{
        "name": "Naoko",
        "instruct": "Calm, warm, slightly formal narrator, measured pace",
        "text": "The rain had fallen for three days without pause.",
        "gender": "female",
        "language": "English"
      }'
# -> {"voice": "3fa85f64-5717-4562-b3fc-2c963f66afa6"}
```

### Step 2 — (optional) List / inspect voices
```bash
curl -sS "$REGISTRY/v1/voices"
curl -sS "$REGISTRY/v1/voices/3fa85f64-5717-4562-b3fc-2c963f66afa6"
```

### Step 3 — Synthesize (any live engine). Same call everywhere — just change `$RIG`.
```bash
curl -sS -X POST "$RIG/v1/audio/speech" \
  -H 'content-type: application/json' \
  -d '{
        "input": "The storm has finally passed.",
        "voice": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "response_format": "wav",
        "voicebox": {"tags": "[calm]"}
      }' \
  -o out.wav
```
To use a different engine, send the **identical body** to that engine's `$RIG`. The rig fetches + caches the voice's reference audio from the registry on first use — no extra calls.

---

## 3. Endpoint reference — synthesis rigs (`/v1/*`, every engine)

Every rig exposes these. The only difference: `voice_design` is mounted **only** on rigs that can invent voices (qwen3 today).

### 3.1 `POST /v1/audio/speech` — text → audio  *(the main call)*

**Request body:**

| Field | Type | Req? | Default | Notes |
|---|---|---|---|---|
| `input` | string | ✅ | — | Text to speak. May contain inline emotion tags (§5). |
| `voice` | string | ✅ | — | Voice UUID from `voice_design` / the registry. |
| `model` | string | – | `""` | Engine name; informational on a single-engine rig. |
| `response_format` | string | – | `"wav"` | `"wav"` (whole file) or `"pcm"` (streamed). Else → 400. |
| `speed` | float | – | `1.0` | Accepted for OpenAI-SDK compat; **not currently applied**. |
| `instructions` | string | – | `""` | Natural-language emotion steer (first comma-token used as a tag). |
| `stream_format` | string | – | `"audio"` | Only `"audio"` in v1 (`"sse"` → 400). |
| `voicebox` | object | – | `{}` | Voicebox extension (below). |
| `voicebox.tags` | string | – | `""` | Inline emotion tags, e.g. `"[angry]"`, `"[happy:0.6]"` (§5). |
| `voicebox.keep_alive` | int \| null | – | `null` | Residency hint (seconds). Parsed but **not yet honored**. |

Unknown fields are ignored (a generic OpenAI SDK client won't 422).
**Emotion priority:** `voicebox.tags` → inline tags in `input` → `instructions` → neutral.

**Responses:**

| `response_format` | Status | `Content-Type` | Body |
|---|---|---|---|
| `"wav"` (default) | 200 | `audio/wav` | Complete mono 16-bit WAV (single response). |
| `"pcm"` | 200 | `audio/l16; rate=<sr>; channels=1` | Raw little-endian signed-16-bit PCM, mono, **chunked/streamed**. |

`<sr>` is the engine's sample rate. **Trust the header** rather than hard-coding it; the WAV header is always correct regardless.

**Errors:** `400` bad `response_format`/`stream_format`; `404` voice not found; `500` synth failure. Shape: `{"detail": "<message>"}` (§8).

**Examples:**
```jsonc
{ "input": "Good morning.", "voice": "<uuid>", "response_format": "wav" }                  // neutral
{ "input": "Get out!", "voice": "<uuid>", "response_format": "pcm",
  "voicebox": { "tags": "[angry:0.9]" } }                                                   // angry, streamed pcm
{ "input": "[sad] I never got to say goodbye.", "voice": "<uuid>" }                         // tags inline in text
```

### 3.2 `POST /v1/audio/voice_design` — invent + register a voice  *(qwen3 rig only)*

| Field | Type | Req? | Default | Notes |
|---|---|---|---|---|
| `name` | string | ✅ | — | Display name. |
| `instruct` | string | ✅ | — | Design prompt — *how* it should sound. |
| `text` | string | ✅ | — | Sample utterance spoken while designing (also stored as the ref transcript). |
| `gender` | string | – | `""` | e.g. `"female"`. |
| `language` | string | – | `"English"` | qwen3 design is English-centric; it can't synthesize accents from a prompt — clone from accented ref audio instead. |
| `description` | string | – | `""` | Human blurb; falls back to `instruct`. |

**Response (200):** `{"voice": "<uuid>"}` — the registry voice id to use in `/v1/audio/speech`. The rig stores the generated ref WAV + transcript in the registry for you, so the voice immediately works on every engine (including those that need a ref transcript).

### 3.3 `GET /v1/models` — what this rig serves
```json
{"object": "list", "data": [{"id": "qwen3", "object": "model", "kind": "text_steer"}]}
```
(Single entry — the rig's own engine. For the full catalog, use the registry's `/v1/models`, §4.)

### 3.4 `GET /health` — liveness + load state
```json
{"status": "ok", "engine": "chatterbox", "loaded": false}
```
`loaded` is `false` until the model is in VRAM (lazy — first synth/design triggers load). **Use this to confirm a rig is up before targeting it.**

### 3.5 `POST /load` / `POST /unload` — VRAM control (ops)
No body. Returns `{"status": "ok", "loaded": <bool>}`. Manage GPU residency when swapping engines; consumers normally don't need these.

---

## 4. Endpoint reference — registry (`$REGISTRY`)

Discovery + reference assets. Most consumers only need `GET /v1/voices*`.

| Method + path | Purpose | Response |
|---|---|---|
| `GET /v1/voices` | list all voices | `[{id,name,gender,language,description}, …]` |
| `GET /v1/voices/{id}` | one voice (manifest) | `{id,name,gender,language,description,ref_audio_url,ref_text_url}`; `404` `{"detail":"Voice '…' not found"}` |
| `GET /v1/voices/{id}/ref_audio` | reference WAV | `audio/wav` binary |
| `GET /v1/voices/{id}/ref_text` | reference transcript | `text/plain` |
| `POST /v1/voices` | **register a voice manually** (advanced — below) | `{"voice":"<uuid>"}` |
| `GET /v1/models` | full engine catalog | see below |
| `GET /health` | registry liveness | `{"status":"ok","backend":"…","engine_loaded":bool}` |

The `ref_audio_url` / `ref_text_url` in a manifest are **paths relative to `$REGISTRY`** (e.g. `/v1/voices/<id>/ref_audio`), so they survive whatever host/proxy fronts the registry.

### `POST /v1/voices` (manual registration — `multipart/form-data`)
You normally don't call this — `voice_design` does. Use it to register a voice from your **own** reference audio (a cloning workflow):

| Form field | Req? | Default |
|---|---|---|
| `ref_audio` (file, WAV) | ✅ | — |
| `name` | ✅ | — |
| `gender` | ✅ | — |
| `language` | – | `"English"` |
| `description` | – | `""` |
| `instruct` | – | `""` |
| `ref_text` (transcript of the ref audio) | – | `""` |

→ `{"voice":"<uuid>"}`. **Tip:** if you'll synthesize on engines that need a ref transcript (§6), supply `ref_text`.

### `GET /v1/models` (registry — full catalog)
Lists **every** engine Voicebox knows about (the catalog, not only live rigs). Each entry:
```json
{"id":"chatterbox","object":"model","kind":"intensity",
 "needs_ref_text":false,"supports_nonverbal":false,"lead":true}
```
`kind` ∈ `text_steer | intensity | categorical | clone_only`; `lead:true` ≈ part of the v1 rollout. **An entry here doesn't guarantee a running rig** — confirm with that rig's `/health` (§3.4) or the status column in §6.

---

## 5. Emotion tags (the generic, engine-agnostic emotion layer)

Put tags in `voicebox.tags` (recommended) or inline in `input`. They're stripped from the spoken text. **You always send the same generic tags; each rig translates them to its engine's native controls automatically** (§6).

**Syntax** (regex `\[([a-zA-Z_]+)(?::([0-9]*\.?[0-9]+))?\]`):

| Form | Example | Meaning |
|---|---|---|
| `[emotion]` | `[angry]` | Bare tag → intensity **0.8**. |
| `[emotion:N]` | `[happy:0.6]` | Explicit intensity, clamped to `[0.0, 1.0]`. |
| Stacking | `[angry][angry]` | Each repeat adds **0.1** to the 0.8 base (2× → 0.9, 3× → 1.0). |

**Emotions (8):** `neutral`, `angry`, `sad`, `happy`, `calm`, `afraid`, `surprised`, `disgusted`.
**Non-verbals (7):** `laugh`, `sigh`, `cough`, `breath`, `chuckle`, `giggle`, `gasp` — rendered **only by engines with `supports_nonverbal=true`** (§6). Elsewhere they're silently ignored.
Unknown tag names are stripped and ignored.

---

## 6. Engines — capabilities & rollout status

The `/v1/audio/speech` contract is identical for all of these. They differ only in: how they realize emotion, whether they need a ref transcript, non-verbal support, whether they can design voices, and whether they're **live yet**. **Your deployment maps each engine name to a `$RIG` base URL.**

| Engine (name) | Emotion `kind` → mechanism | Ref text? | Non-verbals? | Designs voices? | **Status** |
|---|---|---|---|---|---|
| **qwen3** | `text_steer` → natural-language `instruct` ("Speak in an angry tone."); intensity unused | needs† | no | ✅ **yes** | ✅ **LIVE** |
| **chatterbox** | `intensity` → `exaggeration`/`cfg_weight` (0.8 → exagg 0.9 / cfg 0.34) | no | no | no | ✅ **LIVE** |
| **cosyvoice3** | `clone_only` → **ignores emotion** (faithful neutral clone; emotion would erode identity) | yes | **yes** | no | ⏳ Plan 4b |
| **indextts2** | `categorical` → 8-dim `emo_vector` + `emo_alpha` (richest emotion) | no | no | no | ⏳ Plan 4b |
| zonos | `categorical` → 8-dim vector + `pitch_std` | no | no | no | catalog (eval) |
| step_audio | `categorical` → iterative emotion edit (`iterations:2`) | yes | **yes** | no | catalog (eval) |
| higgs | `intensity` → scene prompt + `temperature` (0.3→0.8) | yes | no | no | catalog (eval) |

**Status legend:**
- **LIVE** — serving `/v1/audio/speech` now (Plan 4a). Build & test against these today.
- **Plan 4b** — lead engine moving onto `/v1/audio/speech` next (same contract). Code for them now; they'll answer when deployed.
- **catalog (eval)** — known to the registry with emotion translation defined, but not part of the current v1 rollout. Treat as future/optional.

† qwen3 is flagged `needs_ref_text` in the catalog, but it's also the **designer** — voices created via `voice_design` always carry ref audio + transcript, so they work everywhere.

**Picking an engine** (when more are live): **qwen3** = voice factory + text-steer emotion; **indextts2** = strongest, most controllable emotion; **chatterbox** = simple intensity dial, fast, MIT; **cosyvoice3** = most faithful clone (no emotion) + non-verbals. Same request to all — choose per voice/moment by `$RIG`.

**Consumer takeaways:**
1. **Design on qwen3**, synthesize anywhere. Designed voices satisfy every engine's ref-text requirement automatically.
2. **Emotion is uniform** — send generic `[tags]`; the rig translates. Exception: **cosyvoice3 ignores emotion** (clone-only).
3. **Non-verbals** (`[laugh]`, `[sigh]`) only land on engines with `supports_nonverbal=true` (cosyvoice3, step_audio).
4. **Check liveness** via each rig's `GET /health`; don't infer it from the registry catalog.

---

## 7. Service configuration (for whoever runs/deploys the service)

Behavior is configured via `VOICEBOX_`-prefixed env vars. Consumer-irrelevant for calling the API, but useful to know what the operator controls (values are deployment-specific — **no hosts/ports are part of the API contract**):

| Env var | Meaning |
|---|---|
| `VOICEBOX_REGISTRY_URL` | URL the rigs use to reach the registry (deployment-specific). |
| `VOICEBOX_BACKEND` | Engine backend (`fake` = CPU/no-GPU, for tests). |
| `VOICEBOX_PRELOAD` | Load model at boot vs. lazily on first request. |
| `VOICEBOX_UNLOAD_POLICY` | `keep` vs `on_demand` (frees VRAM between calls). |
| `VOICEBOX_SAMPLE_RATE` | Drives the pcm `audio/l16; rate=` header. |
| `VOICEBOX_OUTPUT_DIR` | Voice/ref-wav store (rigs cache fetched voices here). |

Host/port bindings and which rig answers which URL are set in the deployment (compose / reverse proxy / gateway), not here.

---

## 8. Errors

All errors use FastAPI's default shape: `{"detail": "<message>"}`, with the status set accordingly:

| Status | When |
|---|---|
| `400` | Unsupported `response_format` / `stream_format`. |
| `404` | Voice id not found (registry or rig). |
| `500` | Engine/synthesis failure (`detail` = exception text). |
| `422` | Body failed validation — FastAPI's `{"detail":[{loc,msg,type}]}` list shape. |

---

## 9. Caveats & gotchas

1. **First request is cold.** A rig may start unloaded (lazy load); the first `voice_design`/`speech` triggers a model load (seconds to tens of seconds). Size timeouts accordingly, or call `POST /load` first.
2. **`speed` and `voicebox.keep_alive` are accepted but not yet acted on.**
3. **Voice-id field name:** `voice_design` and `POST /v1/voices` both return `{"voice":"<uuid>"}`. (A *legacy* `/design` returns `{"speaker_id":…}` — don't use it; §10.)
4. **cosyvoice3 ignores emotion tags** (clone-only) — expected, not a bug.
5. **GPU residency:** one model loaded per rig at a time; sharing a GPU across engines may need `/unload` on the previous rig (ops concern, not a request param).

---

## 10. Legacy endpoints (do not build against — retiring in Plan 5)

The registry still exposes an older surface predating the `/v1/*` API: `POST /speak` (central router that picks an engine + translates emotion), `POST /design`, `POST /generate_file`, `POST /generate_stream`, `GET /speakers`, `POST /load_model` / `/unload_model`. They work today but are slated for removal once all leads are on `/v1/audio/speech`. **New consumers: use the `/v1/*` rig + registry endpoints above.**

---

*Generated from source inspection of `~/repo/voicebox` (`src/voicebox_shim/{server,openai_models,tags,emotion_map,engines}.py`, `src/voicebox/registry.py`, `config.py`, the rig `build_app`s), 2026-06-09. If a field/behavior here ever disagrees with the code, the code wins — re-generate this doc.*
