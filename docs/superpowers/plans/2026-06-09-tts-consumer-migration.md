# TTS-Consumer Migration → voicebox `/v1/*` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate playAIdes' TTS consumer off the removed `voicebox_client` Python API onto the voicebox `/v1/*` HTTP contract behind a single `TTSClient` seam, dropping the dead imports so the full `bin/test` suite collects and passes green.

**Architecture:** A thin, stateless, env-driven `backend/clients/tts.py` (`TTSClient`, mirroring the `OpenAICompatLLM` seam) speaks the decentralized voicebox contract — synth rig (`/v1/audio/speech`), registry (`/v1/voices`), design rig (`/v1/audio/voice_design`) — over three base URLs. `incarnation_server.py`'s proxy routes and `playAIdes.py`'s call sites are repointed to it; `persona.Voice.speaker_uuid` is hard-renamed to `voice`.

**Tech Stack:** Python, `httpx` (sync + async), `pydantic`, FastAPI; tested with `respx` (httpx mocking) + `pytest` (`asyncio_mode=auto`, so `async def test_…` run directly). Reference contract: `docs/VOICEBOX_HTTP_API.md`. Design: `docs/superpowers/specs/2026-06-09-tts-consumer-migration-design.md`.

**Branch:** `tts-consumer-migration` (already created off `main`; the spec is committed there).

---

## File structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `backend/clients/tts.py` | Create | `TTSClient` + `PersonaTTS` protocol + `TTSError` + `_parse_sample_rate`. The whole HTTP seam. |
| `tests/unit/test_tts_client.py` | Create | Hermetic `respx` unit tests for `TTSClient`. |
| `tests/integration/test_tts_proxy.py` | Create | Hermetic `respx` tests for the two repointed proxy routes. |
| `persona.py` | Modify | `Voice.speaker_uuid` → `voice`. |
| `personas/silver/persona.json` (+ `.bak`) | Modify | Data migration: `persona_voice.speaker_uuid` → `voice`. |
| `incarnation_server.py` | Modify | Repoint `/api/tts/proxy` + `/api/speakers/{voice}/ref_audio`; add `_wav_streaming_header`. |
| `playAIdes.py` | Modify | Drop dead imports; rewire `self.tts`, `PlayAIdesArgs`, `_setup_voice`, the `design_voice`/`test_voice` WS handlers, `speak_as_persona`. |
| `tests/conftest.py` | Modify | Migrate the shared in-memory `_FakeTTS` fixture to the new protocol. |
| `tests/unit/test_persona.py` | Modify | `Voice(speaker_uuid=…)` → `voice=…`; add a Silver-loads-with-`voice` test. |
| `tests/unit/test_conversation_service.py` | Modify | persona dict `speaker_uuid` → `voice` (line ~80). |
| `tests/unit/test_playaides_chat.py` | Modify | persona dict `speaker_uuid` → `voice` (line ~66). |
| `tests/unit/test_speak_as_persona.py` | Modify | Remove voicebox stub; `voice=`; update lip-sync URL assertion; drop the CLI-path test. |
| `tests/unit/test_handle_event.py` | Modify | Remove the voicebox `sys.modules` stub block (line ~8). |
| `tests/unit/test_chat_skill_dispatch.py` | Modify | Remove the voicebox `sys.modules` stub block (line ~7). |
| `tests/integration/test_persona_routing.py` | Modify | Remove the voicebox `sys.modules` stub block (lines ~19–21). |
| `tests/live/test_tts_live.py` | Modify | Rewrite onto `TTSClient` (its top-level import of the removed module currently breaks collection). |

**Out of scope (do NOT touch):** the entire `voice_generation/**` subtree and `tests/unit/test_voice_api.py` — these test a *separate* legacy local voice server, not playAIdes' consumer; they import from `voice_generation.voice_server.…`, not the removed `voicebox_client`.

---

## Task 1: `TTSClient` — config, `synth` (sync WAV), `TTSError`, `PersonaTTS`, `_parse_sample_rate`

**Files:**
- Create: `backend/clients/tts.py`
- Test: `tests/unit/test_tts_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_tts_client.py`:

```python
"""Hermetic unit tests for backend.clients.tts.TTSClient (respx-mocked)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from backend.clients.tts import TTSClient, TTSError, _parse_sample_rate


def test_urls_default_and_from_env(monkeypatch):
    monkeypatch.delenv("VOICEBOX_URL", raising=False)
    monkeypatch.delenv("TTS_URL", raising=False)
    monkeypatch.delenv("VOICEBOX_REGISTRY_URL", raising=False)
    monkeypatch.delenv("VOICEBOX_DESIGN_URL", raising=False)
    c = TTSClient()
    assert c.rig_url == "http://localhost:8008"
    assert c.registry_url == "http://localhost:8008"
    assert c.design_url == "http://localhost:8008"  # falls back to rig_url

    monkeypatch.setenv("VOICEBOX_URL", "http://rig:8008")
    monkeypatch.setenv("VOICEBOX_REGISTRY_URL", "http://reg:8008")
    monkeypatch.setenv("VOICEBOX_DESIGN_URL", "http://qwen:8008")
    c2 = TTSClient()
    assert (c2.rig_url, c2.registry_url, c2.design_url) == (
        "http://rig:8008", "http://reg:8008", "http://qwen:8008")


def test_parse_sample_rate():
    assert _parse_sample_rate("audio/l16; rate=22050; channels=1") == 22050
    assert _parse_sample_rate("audio/wav") == 24000           # default
    assert _parse_sample_rate("audio/l16; rate=bogus") == 24000


@respx.mock
def test_synth_returns_wav_bytes_and_sends_contract_body():
    route = respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(200, content=b"RIFFwav", headers={"content-type": "audio/wav"}))
    out = TTSClient(rig_url="http://rig.test").synth("hello", "v1", tags="[calm]")
    assert out == b"RIFFwav"
    body = json.loads(route.calls.last.request.content)
    assert body == {"input": "hello", "voice": "v1",
                    "response_format": "wav", "voicebox": {"tags": "[calm]"}}


@respx.mock
def test_synth_maps_http_error_to_ttserror():
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(404, json={"detail": "voice 'x' not found"}))
    with pytest.raises(TTSError):
        TTSClient(rig_url="http://rig.test").synth("hi", "x")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test pytest tests/unit/test_tts_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.clients.tts'`.

- [ ] **Step 3: Create `backend/clients/tts.py` (config + sync `synth`)**

```python
"""HTTP client for the voicebox /v1/* TTS service.

Mirrors the OpenAICompatLLM seam (model_interfaces.py): a thin, stateless,
env-driven client. voicebox is decentralized (docs/VOICEBOX_HTTP_API.md): a
registry (voice catalog + ref audio), a synth rig per engine
(POST /v1/audio/speech), and a design rig (qwen3, POST /v1/audio/voice_design).
Each is a separate base URL.

httpx (not requests) because the streaming consumer — incarnation_server's
/api/tts/proxy — is an async FastAPI route; a blocking requests stream would
stall the event loop. Sync methods use httpx's module-level client; the
streaming method uses httpx.AsyncClient. Tested with respx.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Protocol, Tuple, runtime_checkable

import httpx

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 24000


class TTSError(RuntimeError):
    """Raised when a voicebox call fails (network, bad status, or bad body)."""


@runtime_checkable
class PersonaTTS(Protocol):
    """The sync TTS surface PlayAIdes depends on. TTSClient implements it; test
    doubles need only these two methods."""

    def synth(self, text: str, voice: str, *, tags: str = "") -> bytes: ...

    def design_voice(self, name: str, instruct: str, text: str,
                     gender: str, language: str) -> str: ...


def _parse_sample_rate(content_type: str, default: int = DEFAULT_SAMPLE_RATE) -> int:
    """Extract <sr> from 'audio/l16; rate=<sr>; channels=1'. The contract says
    trust the header (VOICEBOX_HTTP_API §3.1); fall back if absent/garbled."""
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("rate="):
            try:
                return int(part[len("rate="):])
            except ValueError:
                return default
    return default


class TTSClient:
    def __init__(self, rig_url: Optional[str] = None,
                 registry_url: Optional[str] = None,
                 design_url: Optional[str] = None,
                 timeout: float = 60.0):
        self.rig_url = (rig_url or os.environ.get("VOICEBOX_URL")
                        or os.environ.get("TTS_URL") or "http://localhost:8008").rstrip("/")
        self.registry_url = (registry_url or os.environ.get("VOICEBOX_REGISTRY_URL")
                             or "http://localhost:8008").rstrip("/")
        self.design_url = (design_url or os.environ.get("VOICEBOX_DESIGN_URL")
                           or self.rig_url).rstrip("/")
        self.timeout = timeout

    def synth(self, text: str, voice: str, *, tags: str = "") -> bytes:
        """Whole-file WAV synthesis (POST /v1/audio/speech, response_format=wav)."""
        url = f"{self.rig_url}/v1/audio/speech"
        payload = {"input": text, "voice": voice,
                   "response_format": "wav", "voicebox": {"tags": tags}}
        try:
            r = httpx.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("TTS synth failed at %s: %s", url, e)
            raise TTSError(f"TTS synth failed: {e}") from e
        return r.content
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test pytest tests/unit/test_tts_client.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/clients/tts.py tests/unit/test_tts_client.py
git commit -m "feat(tts): TTSClient config + synth (sync WAV) against /v1/audio/speech"
```

---

## Task 2: `TTSClient.open_speech_stream` (async PCM + sample-rate from header)

**Files:**
- Modify: `backend/clients/tts.py`
- Test: `tests/unit/test_tts_client.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tts_client.py`:

```python
@respx.mock
async def test_open_speech_stream_yields_rate_and_pcm():
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(
            200, content=b"\x01\x02\x03\x04",
            headers={"content-type": "audio/l16; rate=16000; channels=1"}))
    chunks = bytearray()
    async with TTSClient(rig_url="http://rig.test").open_speech_stream("hi", "v1") as (sr, stream):
        assert sr == 16000
        async for chunk in stream:
            chunks.extend(chunk)
    assert bytes(chunks) == b"\x01\x02\x03\x04"


@respx.mock
async def test_open_speech_stream_error_raises_ttserror():
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(500, json={"detail": "boom"}))
    with pytest.raises(TTSError):
        async with TTSClient(rig_url="http://rig.test").open_speech_stream("hi", "v1"):
            pass
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test pytest tests/unit/test_tts_client.py -k open_speech_stream -q`
Expected: FAIL — `AttributeError: 'TTSClient' object has no attribute 'open_speech_stream'`.

- [ ] **Step 3: Add `open_speech_stream` to `TTSClient`**

Add this method to the `TTSClient` class in `backend/clients/tts.py`:

```python
    @asynccontextmanager
    async def open_speech_stream(self, text: str, voice: str, *, tags: str = ""
                                 ) -> AsyncIterator[Tuple[int, AsyncIterator[bytes]]]:
        """Streamed PCM synthesis (response_format=pcm). Yields (sample_rate,
        byte-iterator); the rate is read from the rig's audio/l16 header so the
        proxy can build a correct WAV wrapper."""
        url = f"{self.rig_url}/v1/audio/speech"
        payload = {"input": text, "voice": voice,
                   "response_format": "pcm", "voicebox": {"tags": tags}}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise TTSError(f"TTS stream failed: {resp.status_code} {body[:200]!r}")
                sample_rate = _parse_sample_rate(resp.headers.get("content-type", ""))
                yield sample_rate, resp.aiter_bytes()
```

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_tts_client.py -k open_speech_stream -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/clients/tts.py tests/unit/test_tts_client.py
git commit -m "feat(tts): async open_speech_stream (PCM + sample-rate from header)"
```

---

## Task 3: `TTSClient.design_voice` (sync) + `ref_audio` (async)

**Files:**
- Modify: `backend/clients/tts.py`
- Test: `tests/unit/test_tts_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_tts_client.py`:

```python
@respx.mock
def test_design_voice_returns_uuid_and_sends_body():
    route = respx.post("http://design.test/v1/audio/voice_design").mock(
        return_value=httpx.Response(200, json={"voice": "uuid-xyz"}))
    out = TTSClient(design_url="http://design.test").design_voice(
        name="Naoko", instruct="calm narrator", text="Hello.",
        gender="female", language="English")
    assert out == "uuid-xyz"
    body = json.loads(route.calls.last.request.content)
    assert body == {"name": "Naoko", "instruct": "calm narrator",
                    "text": "Hello.", "gender": "female", "language": "English"}


@respx.mock
def test_design_voice_missing_voice_key_raises():
    respx.post("http://design.test/v1/audio/voice_design").mock(
        return_value=httpx.Response(200, json={"oops": True}))
    with pytest.raises(TTSError):
        TTSClient(design_url="http://design.test").design_voice(
            name="x", instruct="y", text="z", gender="female", language="English")


@respx.mock
async def test_ref_audio_fetches_from_registry():
    respx.get("http://reg.test/v1/voices/v1/ref_audio").mock(
        return_value=httpx.Response(200, content=b"RIFFref",
                                    headers={"content-type": "audio/wav"}))
    out = await TTSClient(registry_url="http://reg.test").ref_audio("v1")
    assert out == b"RIFFref"
```

- [ ] **Step 2: Run to verify they fail**

Run: `bin/test pytest tests/unit/test_tts_client.py -k "design_voice or ref_audio" -q`
Expected: FAIL — `AttributeError` for `design_voice` / `ref_audio`.

- [ ] **Step 3: Add `design_voice` and `ref_audio` to `TTSClient`**

Add to the `TTSClient` class:

```python
    def design_voice(self, name: str, instruct: str, text: str,
                     gender: str, language: str) -> str:
        """Mint a voice on the qwen3 design rig; returns the registry voice UUID."""
        url = f"{self.design_url}/v1/audio/voice_design"
        payload = {"name": name, "instruct": instruct, "text": text,
                   "gender": gender, "language": language}
        try:
            r = httpx.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            logger.error("voice_design failed at %s: %s", url, e)
            raise TTSError(f"voice_design failed: {e}") from e
        except ValueError as e:  # non-JSON body
            raise TTSError(f"voice_design returned non-JSON: {e}") from e
        voice = data.get("voice")
        if not voice:
            raise TTSError(f"voice_design response missing 'voice': {data!r}")
        return voice

    async def ref_audio(self, voice: str) -> bytes:
        """Fetch a voice's reference WAV from the registry."""
        url = f"{self.registry_url}/v1/voices/{voice}/ref_audio"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url)
                r.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("ref_audio fetch failed at %s: %s", url, e)
            raise TTSError(f"ref_audio fetch failed: {e}") from e
        return r.content
```

- [ ] **Step 4: Run to verify they pass**

Run: `bin/test pytest tests/unit/test_tts_client.py -q`
Expected: PASS (all 9 tests in the file).

- [ ] **Step 5: Commit**

```bash
git add backend/clients/tts.py tests/unit/test_tts_client.py
git commit -m "feat(tts): design_voice + ref_audio; TTSClient surface complete"
```

---

## Task 4: Rename `persona.Voice.speaker_uuid` → `voice` + data migration

**Files:**
- Modify: `persona.py:24-29`
- Modify: `personas/silver/persona.json`, `personas/silver/persona.json.bak`
- Modify: `tests/unit/test_persona.py:53-59`
- Modify: `tests/unit/test_conversation_service.py:80`
- Modify: `tests/unit/test_playaides_chat.py:66`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_persona.py`, replace the three `Voice(speaker_uuid=…)` usages (around lines 53-59) with `voice=…`, and add a Silver-loads test. The updated assertions:

```python
        assert Voice(voice=None).is_voice_valid() is False
        assert Voice(voice="abc-123").is_voice_valid() is True
        v = Voice(voice="x", voice_instruct=["calm", "slow"])
        assert v.voice == "x" and v.voice_instruct == ["calm", "slow"]
```

Add a new test in the same file:

```python
def test_silver_persona_loads_with_voice_field():
    import json
    from pathlib import Path
    from persona import Persona
    data = json.loads(Path("personas/silver/persona.json").read_text())
    p = Persona(**data)
    assert p.persona_voice.voice == "f89c35ba-6db3-40c3-a7ee-d6b03cf71449"
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test pytest tests/unit/test_persona.py -q`
Expected: FAIL — `Voice(voice=…)` is rejected/ignored (field is still `speaker_uuid`), and the Silver test sees `voice is None`.

- [ ] **Step 3: Rename the field in `persona.py`**

Replace lines 24-29 of `persona.py`:

```python
class Voice(BaseModel): #optional
    #speaker: Speaker # this can also be a local file path
    voice: Optional[str] = None          # registry voice UUID (was speaker_uuid)
    voice_instruct: Optional[list[str]] = None
    def is_voice_valid(self) -> bool:
        return self.voice is not None
```

- [ ] **Step 4: Migrate the persona data files**

In `personas/silver/persona.json` and `personas/silver/persona.json.bak`, rename the key inside `persona_voice`: `"speaker_uuid": "f89c35ba-6db3-40c3-a7ee-d6b03cf71449"` → `"voice": "f89c35ba-6db3-40c3-a7ee-d6b03cf71449"`. (Use Edit on each file; the surrounding `persona_voice` block is otherwise unchanged.)

- [ ] **Step 5: Update the other persona-dict literals**

- `tests/unit/test_conversation_service.py:80` — `persona_voice={"speaker_uuid": "v-1"}` → `persona_voice={"voice": "v-1"}`.
- `tests/unit/test_playaides_chat.py:66` — `valid_persona_dict["persona_voice"] = {"speaker_uuid": "uuid-1"}` → `{"voice": "uuid-1"}`.

- [ ] **Step 6: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_persona.py tests/unit/test_conversation_service.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add persona.py personas/silver/persona.json personas/silver/persona.json.bak \
        tests/unit/test_persona.py tests/unit/test_conversation_service.py tests/unit/test_playaides_chat.py
git commit -m "refactor(persona): rename Voice.speaker_uuid -> voice + migrate persona files"
```

---

## Task 5: Repoint `incarnation_server.py` proxy routes to `/v1/*`

**Files:**
- Modify: `incarnation_server.py` (imports near top; `TTS_BASE` at line ~54; routes at ~351-419)
- Test: `tests/integration/test_tts_proxy.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_tts_proxy.py`:

```python
"""Integration tests for the repointed TTS proxy routes (respx-mocked)."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from starlette.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def proxy_client(monkeypatch):
    monkeypatch.setenv("VOICEBOX_URL", "http://rig.test")
    monkeypatch.setenv("VOICEBOX_REGISTRY_URL", "http://reg.test")
    monkeypatch.delenv("TTS_URL", raising=False)
    from incarnation_server import IncarnationServer
    return TestClient(IncarnationServer().app)


@respx.mock
def test_tts_proxy_wraps_pcm_in_wav_with_header_rate(proxy_client):
    respx.post("http://rig.test/v1/audio/speech").mock(
        return_value=httpx.Response(
            200, content=b"\xaa\xbb\xcc\xdd",
            headers={"content-type": "audio/l16; rate=16000; channels=1"}))
    r = proxy_client.get("/api/tts/proxy", params={"text": "hi", "voice": "v1"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    body = r.content
    assert body.startswith(b"RIFF")
    assert int.from_bytes(body[24:28], "little") == 16000   # sample rate in WAV header
    assert body.endswith(b"\xaa\xbb\xcc\xdd")
    sent = json.loads(respx.calls.last.request.content)
    assert sent["response_format"] == "pcm" and sent["voice"] == "v1" and sent["input"] == "hi"


@respx.mock
def test_ref_audio_proxy_hits_registry(proxy_client):
    respx.get("http://reg.test/v1/voices/v1/ref_audio").mock(
        return_value=httpx.Response(200, content=b"RIFFref",
                                    headers={"content-type": "audio/wav"}))
    r = proxy_client.get("/api/speakers/v1/ref_audio")
    assert r.status_code == 200
    assert r.content == b"RIFFref"
```

- [ ] **Step 2: Run to verify they fail**

Run: `bin/test pytest tests/integration/test_tts_proxy.py -q`
Expected: FAIL — the proxy still POSTs to `{TTS_BASE}/generate_stream` (no respx route → connect error / 404), and the pcm body/rate assertions don't hold.

- [ ] **Step 3: Add the imports + WAV-header helper**

Near the top of `incarnation_server.py`, add to the imports:

```python
from backend.clients.tts import TTSClient, TTSError
```

Remove the now-unused `TTS_BASE` constant (line ~54: `TTS_BASE = os.environ.get("TTS_URL") or "http://localhost:8009"`). Leave `WHISPER_BASE` untouched.

Add this module-level helper (near the other module-level defs, e.g. just below `WHISPER_BASE`):

```python
def _wav_streaming_header(sample_rate: int, channels: int = 1, bits: int = 16) -> bytes:
    """RIFF/WAVE header for a streamed PCM body of unknown length (0xFFFFFFFF
    sizes). Sample rate comes from the rig's audio/l16 response header."""
    header = bytearray(b"RIFF")
    header.extend([0xFF, 0xFF, 0xFF, 0xFF])          # ChunkSize (unknown)
    header.extend(b"WAVEfmt ")
    header.extend([16, 0, 0, 0])                     # Subchunk1Size
    header.extend([1, 0])                            # AudioFormat (PCM)
    header.extend([channels, 0])                     # NumChannels
    header.extend(sample_rate.to_bytes(4, "little"))
    byte_rate = sample_rate * channels * bits // 8
    header.extend(byte_rate.to_bytes(4, "little"))
    block_align = channels * bits // 8
    header.extend(block_align.to_bytes(2, "little"))
    header.extend(bits.to_bytes(2, "little"))
    header.extend(b"data")
    header.extend([0xFF, 0xFF, 0xFF, 0xFF])          # Subchunk2Size (unknown)
    return bytes(header)
```

- [ ] **Step 4: Rewrite the two routes**

Replace the existing `proxy_ref_audio` route (lines ~351-364) with:

```python
        # ── Ref audio proxy (registry → frontend) ────────────────────────────
        @self.app.get("/api/speakers/{voice}/ref_audio")
        async def proxy_ref_audio(voice: str):
            try:
                content = await TTSClient().ref_audio(voice)
            except TTSError as e:
                raise HTTPException(status_code=502, detail=f"Voice registry error: {e}")
            return StreamingResponse(
                iter([content]),
                media_type="audio/wav",
                headers={"Content-Disposition": f"inline; filename={voice}_ref.wav"},
            )
```

Replace the existing `proxy_tts_stream` route (lines ~366-419, the whole `@self.app.get("/api/tts/proxy")` block including the inline `pcm_to_wav_stream`) with:

```python
        # ── TTS Stream Proxy ──────────────────────────────────────────────────
        @self.app.get("/api/tts/proxy")
        async def proxy_tts_stream(text: str, voice: str):
            """Proxy a browser GET → voicebox POST /v1/audio/speech (pcm), wrapping
            the raw L16 PCM in a WAV header (sample rate from the rig's response)
            so the browser can play it."""
            async def pcm_to_wav_stream():
                try:
                    async with TTSClient().open_speech_stream(text, voice) as (sample_rate, chunks):
                        yield _wav_streaming_header(sample_rate)
                        async for chunk in chunks:
                            yield chunk
                except TTSError as e:
                    logger.error("TTS proxy error: %s", e)
                    return

            return StreamingResponse(
                pcm_to_wav_stream(),
                media_type="audio/wav",
                headers={
                    "Accept-Ranges": "none",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
```

> Note: `TTSClient()` is constructed per request — it is stateless and just reads env, so this keeps the routes env-fresh for tests with no measurable cost.

- [ ] **Step 5: Run to verify they pass**

Run: `bin/test pytest tests/integration/test_tts_proxy.py -q`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add incarnation_server.py tests/integration/test_tts_proxy.py
git commit -m "feat(server): repoint TTS proxy routes to voicebox /v1/* via TTSClient"
```

---

## Task 6: `playAIdes.py` — drop dead imports, rewire `PlayAIdesArgs`/`self.tts`

**Files:**
- Modify: `playAIdes.py` (lines 5-6 imports; 84 field; 89-104 validator; 109 default)
- Test: `tests/unit/test_tts_import.py` (create — proves a clean import with no stub)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_tts_import.py` (note: this file deliberately has **no** `voicebox_client` `sys.modules` stub — the whole point is that playAIdes imports cleanly without it):

```python
"""Proves playAIdes imports with no voicebox_client stub — the migration keystone."""


def test_playaides_imports_without_voicebox_stub():
    import playAIdes  # must NOT raise ModuleNotFoundError
    assert hasattr(playAIdes, "PlayAIdes")


def test_args_accepts_duck_typed_tts():
    from playAIdes import PlayAIdesArgs

    class FakeTTS:
        def synth(self, text, voice, *, tags=""):
            return b""
        def design_voice(self, name, instruct, text, gender, language):
            return "v"

    args = PlayAIdesArgs(persona=["x"], generate_voice=False, use_voice=False,
                         use_avatar=False, generate_avatar=False, tts=FakeTTS())
    assert args.tts is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test pytest tests/unit/test_tts_import.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'voicebox_client'` at `import playAIdes`.

- [ ] **Step 3: Drop the dead imports and swap in `TTSClient`**

In `playAIdes.py`, delete lines 5-6:

```python
from voicebox_client import PersonaTTS, VoiceboxClient
from voicebox.api_models import VoiceDesignRequest, SpeechGenerationRequest
```

and add (next to the other top imports, e.g. after the `model_interfaces` import):

```python
from backend.clients.tts import TTSClient, PersonaTTS
```

- [ ] **Step 4: Simplify the `PlayAIdesArgs.tts` field + validator**

Replace the validator (lines 89-104). The field annotation at line 84 (`tts: Optional[PersonaTTS] = None`) stays as-is — `PersonaTTS` now resolves to the real protocol from `backend.clients.tts`. Replace the validator body with:

```python
    @field_validator("tts")
    @classmethod
    def validate_tts(cls, v):
        if v is None:
            return v
        if not (callable(getattr(v, "synth", None))
                and callable(getattr(v, "design_voice", None))):
            raise TypeError("tts must implement the PersonaTTS protocol (synth, design_voice)")
        return v
```

- [ ] **Step 5: Swap the default client at line 109**

```python
        self.tts: Optional[PersonaTTS] = args.tts if args.tts else TTSClient()  # default: VOICEBOX_URL / TTS_URL
```

- [ ] **Step 6: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_tts_import.py -q`
Expected: PASS (2 tests).
(Other `import PlayAIdes` tests that still carry the old `sys.modules` stub keep passing — stubbing an unused module is harmless; their stubs are removed in Task 9.)

- [ ] **Step 7: Commit**

```bash
git add playAIdes.py tests/unit/test_tts_import.py
git commit -m "refactor(playaides): drop dead voicebox_client imports; default to TTSClient"
```

---

## Task 7: `playAIdes.py` — `_setup_voice` + `design_voice`/`test_voice` WS handlers

**Files:**
- Modify: `playAIdes.py` (`_setup_voice` ~307-327; `design_voice` handler ~655-670; `test_voice` handler ~672-690)
- Test: `tests/unit/test_voice_handlers.py` (create)

**Before writing tests:** read `playAIdes.py` lines ~600-700 to confirm the dispatcher method name (`_handle_incarnation_message`) and the message envelope (`{"type": …, "payload": {…}}`), and skim `tests/unit/test_handle_event.py` for the existing stub-server invocation pattern.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_voice_handlers.py`:

```python
"""design_voice / test_voice WS handlers call the new TTSClient surface."""
import os
import types

from playAIdes import PlayAIdes


class _RecordingServer:
    def __init__(self):
        self.commands = []
        self.port = 8765
    def send_command(self, cmd_type, payload):
        self.commands.append((cmd_type, payload))


class _FakeTTS:
    def __init__(self):
        self.design_calls = []
        self.synth_calls = []
    def design_voice(self, name, instruct, text, gender, language):
        self.design_calls.append(dict(name=name, instruct=instruct, text=text,
                                      gender=gender, language=language))
        return "new-voice-uuid"
    def synth(self, text, voice, *, tags=""):
        self.synth_calls.append((text, voice))
        return b"RIFFwavbytes"


def _ai():
    ai = PlayAIdes.__new__(PlayAIdes)          # skip __init__
    ai.tts = _FakeTTS()
    ai.incarnation_server = _RecordingServer()
    return ai


def test_design_voice_handler_designs_and_emits():
    ai = _ai()
    ai._handle_incarnation_message(
        {"type": "design_voice",
         "payload": {"name": "Naoko", "instruct": "calm", "sample_text": "hi",
                     "gender": "female", "language": "English"}})
    assert ai.tts.design_calls[0]["name"] == "Naoko"
    assert ai.tts.design_calls[0]["text"] == "hi"           # sample_text -> text
    emitted = dict(ai.incarnation_server.commands)
    assert emitted["voice_designed"]["speaker_id"] == "new-voice-uuid"  # WS key unchanged
    assert "/api/speakers/new-voice-uuid/ref_audio" in emitted["voice_designed"]["ref_audio_url"]


def test_test_voice_handler_synths_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ai = _ai()
    ai._handle_incarnation_message(
        {"type": "test_voice",
         "payload": {"text": "hello", "speaker_id": "v-1", "language": "English"}})
    assert ai.tts.synth_calls == [("hello", "v-1")]
    emitted = dict(ai.incarnation_server.commands)
    assert "voice_tested" in emitted
    written = list((tmp_path / "incarnation/public/outputs/tts/temp").glob("*.wav"))
    assert len(written) == 1 and written[0].read_bytes() == b"RIFFwavbytes"
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test pytest tests/unit/test_voice_handlers.py -q`
Expected: FAIL — handlers still call `self.tts.generate_voice(VoiceDesignRequest(...))` / `generate_speech_file(...)` (NameError on the removed request classes, or wrong call surface).

- [ ] **Step 3: Rewrite `_setup_voice`**

Replace the body of `_setup_voice` that sets the voice (lines ~317-325) with:

```python
            p.persona_voice.voice = self.tts.design_voice(
                name=p.name,
                instruct=" ".join(voice_instruct),
                text=p.back_ground,
                gender=p.gender,
                language=p.language,
            )
```

(The surrounding guard `if self.args.generate_voice and (p.persona_voice is None or not p.persona_voice.is_voice_valid())` and the `voice_instruct` assembly above it are unchanged, as is the `self._update_persona_file(p)` call below.)

- [ ] **Step 4: Rewrite the `design_voice` WS handler**

Replace the `if msg_type == "design_voice":` block (lines ~655-670) with:

```python
        if msg_type == "design_voice":
            voice = self.tts.design_voice(
                name=payload.get("name", "voice"),
                instruct=payload.get("instruct", ""),
                text=payload.get("sample_text", "hello"),
                gender=payload.get("gender", "Female"),
                language=payload.get("language", "English"),
            )
            ref_audio_url = f"http://localhost:{self.incarnation_server.port}/api/speakers/{voice}/ref_audio"
            self.incarnation_server.send_command("voice_designed", {
                "speaker_id": voice,                    # WS payload key unchanged (parked console)
                "name": payload.get("name"),
                "ref_audio_url": ref_audio_url,
            })
            return
```

- [ ] **Step 5: Rewrite the `test_voice` WS handler**

Replace the `if msg_type == "test_voice":` block (lines ~672-690) with:

```python
        if msg_type == "test_voice":
            try:
                output_path = "incarnation/public/outputs/tts/temp"
                os.makedirs(output_path, exist_ok=True)
                wav = self.tts.synth(
                    text=payload.get("text", "hello"),
                    voice=payload.get("speaker_id", ""),     # WS payload key unchanged
                )
                import uuid as _uuid
                filename = f"{_uuid.uuid4().hex}.wav"
                with open(os.path.join(output_path, filename), "wb") as f:
                    f.write(wav)
                url = f"http://localhost:8765/outputs/tts/temp/{filename}"
                self.incarnation_server.send_command("voice_tested", {"url": url})
            except Exception as e:
                logger.error(f"Voice test failed: {e}")
                self.incarnation_server.send_command("voice_test_failed", {"error": str(e)})
            return
```

- [ ] **Step 6: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_voice_handlers.py -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add playAIdes.py tests/unit/test_voice_handlers.py
git commit -m "feat(playaides): migrate _setup_voice + design_voice/test_voice handlers to TTSClient"
```

---

## Task 8: `playAIdes.py` — `speak_as_persona` (rename + remove CLI path)

**Files:**
- Modify: `playAIdes.py` (`speak_as_persona` ~777-806)
- Modify: `tests/unit/test_speak_as_persona.py`

- [ ] **Step 1: Update the test (becomes the failing test)**

Rewrite `tests/unit/test_speak_as_persona.py` as follows. Changes: remove the `voicebox_client` `sys.modules` stub block (lines 1-9, no longer needed); `speaker_uuid` → `voice` in `_make_ai`; assert the lip-sync URL carries `&voice=`; replace the old no-avatar-calls-TTS test (the removed CLI path) with a no-avatar-is-silent test.

```python
import types as _types
from unittest.mock import MagicMock


def _make_ai():
    from playAIdes import PlayAIdes
    from incarnation_server import WebSocketDisplayChannel
    ai = PlayAIdes.__new__(PlayAIdes)            # skip __init__
    ai.incarnation_server = MagicMock()
    ai.display = WebSocketDisplayChannel(ai.incarnation_server)
    ai.args = _types.SimpleNamespace(use_voice=False, use_avatar=False)
    ai.tts = MagicMock()
    ai.current_persona = _types.SimpleNamespace(
        persona_voice=_types.SimpleNamespace(voice="uuid-1"),
        name="silver",
        language="English",
    )
    return ai


def test_speak_broadcasts_assistant_message():
    ai = _make_ai()
    ai.speak_as_persona("silver", "hello there")
    ai.incarnation_server.broadcast_to_persona.assert_any_call(
        "silver", "assistant_message", {"text": "hello there", "persona_id": "silver"},
    )


def test_speak_sends_lip_sync_url_with_voice_when_avatar_on():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = True
    ai.speak_as_persona("silver", "hi")
    payloads = [c.args[2] for c in ai.incarnation_server.broadcast_to_persona.call_args_list
                if c.args[1] == "start_lip_sync"]
    assert payloads, "expected a start_lip_sync command"
    assert "&voice=uuid-1" in payloads[0]["url"]
    assert "speaker_id=" not in payloads[0]["url"]


def test_speak_is_silent_without_avatar():
    ai = _make_ai()
    ai.args.use_voice = True
    ai.args.use_avatar = False                 # no display sink → no audio (CLI path removed)
    ai.speak_as_persona("silver", "hi")
    cmds = [c.args[1] for c in ai.incarnation_server.broadcast_to_persona.call_args_list]
    assert "start_lip_sync" not in cmds
    ai.tts.synth.assert_not_called()
```

- [ ] **Step 2: Run to verify it fails**

Run: `bin/test pytest tests/unit/test_speak_as_persona.py -q`
Expected: FAIL — `speak_as_persona` still reads `voice.speaker_uuid`, builds `&speaker_id=`, and the `else` branch calls `self.tts.generate_speech_stream`.

- [ ] **Step 3: Rewrite `speak_as_persona`**

Replace the voice/lip-sync portion of `speak_as_persona` (lines ~781-806, from `if not self.args.use_voice:` through the end of the method) with:

```python
        if not self.args.use_voice:
            return
        voice = getattr(self.current_persona, "persona_voice", None)
        if not (voice and voice.voice):
            logger.warning(
                "Persona %s has no voice config; skipping lip_sync",
                getattr(self.current_persona, "name", "<unknown>"),
            )
            return
        # The browser/avatar is the only audio sink; with no display there is
        # nothing to play to (the old CLI-only TTS path was removed).
        if self.args.use_avatar and self.display:
            import urllib.parse
            safe_text = urllib.parse.quote(text)
            proxy_url = (
                f"http://localhost:8765/api/tts/proxy?text={safe_text}"
                f"&voice={voice.voice}"
            )
            logger.info(f"Sending start_lip_sync: {proxy_url}")
            self.display.push(target_id, "start_lip_sync", {"url": proxy_url})
```

(The earlier `if self.display is not None: self.display.push(... "assistant_message" ...)` block at the top of the method is unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `bin/test pytest tests/unit/test_speak_as_persona.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add playAIdes.py tests/unit/test_speak_as_persona.py
git commit -m "refactor(playaides): speak_as_persona uses voice + drops the CLI-only TTS path"
```

---

## Task 9: Migrate shared test infra (fixtures, stubs, live test)

This task removes the now-obsolete `voicebox_client` scaffolding so the suite collects cleanly in the plain container.

**Files:**
- Modify: `tests/conftest.py:74-97` (the in-memory `_FakeTTS`)
- Modify: `tests/unit/test_handle_event.py` (stub block ~line 8)
- Modify: `tests/unit/test_chat_skill_dispatch.py` (stub block ~line 7)
- Modify: `tests/integration/test_persona_routing.py` (stub block ~lines 19-21)
- Modify: `tests/live/test_tts_live.py` (rewrite onto `TTSClient`)

- [ ] **Step 1: Migrate the shared `_FakeTTS` fixture**

In `tests/conftest.py`, replace the in-memory TTS class (lines ~74-97) so it implements the new `PersonaTTS` protocol. The new class:

```python
class _FakeTTS:
    """In-memory PersonaTTS implementation for tests (new /v1 surface)."""

    def __init__(self, voice: str = "fake-voice-0001") -> None:
        self.voice = voice

    def design_voice(self, name, instruct, text, gender, language) -> str:
        return self.voice

    def synth(self, text, voice, *, tags: str = "") -> bytes:
        return b"RIFFfake-wav-bytes"
```

Keep the existing fixture name/wiring that returns this object (e.g. the `fake_tts` fixture); only the class body changes. If any field/method name elsewhere in `conftest.py` references the old `speaker_uuid`/`generate_*` names, update them to `voice`/`design_voice`/`synth`.

- [ ] **Step 2: Remove the three `voicebox_client` `sys.modules` stub blocks**

In each of these files, delete the stub block (the `import sys`, `from unittest.mock import MagicMock` used only for it, and the `for _mod in ("voicebox_client", "voicebox", "voicebox.api_models"): … sys.modules[_mod] = MagicMock()` loop):

- `tests/unit/test_handle_event.py` (~line 8)
- `tests/unit/test_chat_skill_dispatch.py` (~line 7)
- `tests/integration/test_persona_routing.py` (~lines 19-21)

Leave any other imports those files need (e.g. `MagicMock` if used elsewhere in the same file — check before deleting the import).

- [ ] **Step 3: Rewrite the live TTS test**

`tests/live/test_tts_live.py` currently imports the removed module at top level (breaking collection). Replace its body with a `TTSClient`-based live synth check that auto-skips when no rig is reachable:

```python
"""Live TTS smoke test against a real voicebox /v1 rig + registry.

Auto-skips unless VOICEBOX_URL is set and reachable. Exercises whole-file synth
against a live engine (e.g. the CPU kokoro rig). Voice *design* (qwen3, GPU) is
covered by the deferred manual live test, not here.
"""
import os

import httpx
import pytest

from backend.clients.tts import TTSClient

pytestmark = pytest.mark.live


@pytest.fixture
def live_rig_url():
    url = os.environ.get("VOICEBOX_URL")
    if not url:
        pytest.skip("VOICEBOX_URL not set; skipping live TTS test")
    try:
        httpx.get(f"{url.rstrip('/')}/health", timeout=3).raise_for_status()
    except Exception as e:
        pytest.skip(f"voicebox rig not reachable at {url!r}: {e}")
    return url


def test_live_synth_returns_wav(live_rig_url):
    voice = os.environ.get("VOICEBOX_TEST_VOICE")
    if not voice:
        pytest.skip("VOICEBOX_TEST_VOICE not set (a voice UUID registered in the live registry)")
    out = TTSClient().synth("Hello from a live test.", voice)
    assert out[:4] == b"RIFF" and len(out) > 44   # a real WAV with body
```

- [ ] **Step 4: Run the affected suites**

Run: `bin/test pytest tests/unit/test_handle_event.py tests/unit/test_chat_skill_dispatch.py tests/unit/test_playaides_chat.py -q`
Expected: PASS (these import `PlayAIdes` and use `fake_tts`; they now work without the stub).
Run: `bin/test pytest tests/live/test_tts_live.py -q`
Expected: collected and **skipped** (no `VOICEBOX_URL`), not an error.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/unit/test_handle_event.py tests/unit/test_chat_skill_dispatch.py \
        tests/integration/test_persona_routing.py tests/live/test_tts_live.py
git commit -m "test: migrate fake TTS fixture, drop voicebox_client stubs, rewrite live TTS test"
```

---

## Task 10: Full plain-container suite green (verification)

**Files:** none (verification only).

- [ ] **Step 1: Confirm no stragglers reference the removed API**

Run:
```bash
grep -rnE "voicebox_client|voicebox\.api_models|generate_speech_stream|generate_speech_file|generate_voice\(|VoiceDesignRequest|SpeechGenerationRequest|speaker_uuid" --include='*.py' . | grep -v voice_generation/
```
Expected: **no matches** outside `voice_generation/` (which is out of scope). `main.py`'s `--generate_voice` *flag* and `generate_voice=` *kwargs* are fine — they are the CLI arg, not the removed method; the `generate_voice\(` pattern above only flags the removed method call.

- [ ] **Step 2: Run the full suite in the plain container**

Run: `bin/test pytest -q`
Expected: the suite **collects with no import errors** and passes; live tests are skipped. (This is success criteria #1 and #2 — the keystone.) If anything fails, fix it before proceeding; common causes are a missed persona-dict literal or a fixture still using an old method name.

- [ ] **Step 3: Update CONTINUITY + auto-memory**

Update `CONTINUITY.md` (Now & Next + a Decisions entry: TTS-consumer migration landed; harness still runs legacy voicebox; new registry+kokoro-rig stand-up is the manual live test). Update the auto-memory note `playaides-test-image-voicebox-gap` to record that the *running harness* was the legacy monolith (not the `/v1` server) and that the consumer is now migrated.

- [ ] **Step 4: Commit**

```bash
git add CONTINUITY.md
git commit -m "docs: record TTS-consumer migration; bin/test green again"
```

---

## Task 11: [MANUAL — walk through together] Harness live-test of the new voicebox

> **Not an automated task.** Per the operator's decision, the new-voicebox stand-up and live synth test are done **manually, interactively** — do not script the compose changes or the voice registration. The steps below are a checklist to work through together when ready. The GPU is busy, so **only the CPU kokoro synth path is live-tested now**; the qwen3 design path is deferred.

- [x] **Discovery:** read `~/repo/voicebox`'s own compose (registry service + the CPU kokoro rig, ~`:9008` per commit `aeec623`) and `src/voicebox/rigs/kokoro.py` to confirm how a voice UUID maps to a kokoro preset and whether the rig needs the registry for ref audio. *(Done 2026-06-10: UUID → preset deterministically; ref audio via registry.)*
- [x] **Stand up** the new voicebox **registry** + **CPU kokoro rig** (reuse the concurrent voicebox session's compose if one exists rather than reinventing it). *(Done 2026-06-10: one `voicebox:kokoro` image, two services in `docker-compose.harness.yml`, commit `76a2a6e`.)*
- [x] **Repoint** the harness backend env: `VOICEBOX_REGISTRY_URL` → the registry, `VOICEBOX_URL` → the kokoro rig; leave `VOICEBOX_DESIGN_URL` unset. *(Done; `VOICEBOX_DESIGN_URL` points at the rig's CPU heuristic design route instead of unset.)*
- [x] **Voice identity:** register a voice in the new registry (or pick a kokoro preset); set `VOICEBOX_TEST_VOICE` to its UUID and update `personas/silver/persona.json` `voice` if Silver should use it. *(Done: Silver's legacy UUID `f89c35ba-…` resolves via the shared `speakers.db` — no re-registration needed; `VOICEBOX_TEST_VOICE` set in `.env`.)*
- [x] **Live unit check:** `docker compose -f docker-compose.harness.yml exec -T backend pytest tests/live/test_tts_live.py -q` → passes (real WAV). *(2 passed, 2026-06-10.)*
- [x] **End-to-end:** trigger Silver to speak (control.html "Say on TV" / a greet) and confirm audio + lip-sync play through the repointed `/api/tts/proxy`. *(Done 2026-06-10: operator confirmed audio + lip-sync both good on the Fire TV — kokoro preset timbre.)*
- [ ] **Later (GPU free):** point `VOICEBOX_DESIGN_URL` at a qwen3 rig and live-test `--generate_voice` / the `design_voice` console path.

---

## Self-review

**Spec coverage:** §4.1 `TTSClient` (Tasks 1-3) ✓; §4.2 proxy repoint + D7 sample-rate (Task 5) ✓; §4.3 persona rename + data migration (Task 4) ✓; §4.4 playAIdes rewire incl. dead-import drop, D6 CLI removal (Tasks 6-8) ✓; §6 harness live-test (Task 11, manual) ✓; §7 test plan — hermetic (Tasks 1-5,7,8), plain-container green (Task 10), live (Tasks 9,11) ✓; D1-D7 all realized. Test-infra debt the spec implied (shared fixture, stubs, live test) is Task 9 ✓.

**Placeholder scan:** no TBD/TODO; every code step shows complete code. The two spots that say "read X first" (Task 7 dispatcher envelope; Task 9 conftest fixture name) are because the exact surrounding lines weren't quoted here — the *changes* are fully specified; the reads are to place them correctly, not to invent content.

**Type/name consistency:** `TTSClient(rig_url/registry_url/design_url)`, `synth(text, voice, *, tags)`, `open_speech_stream(...) -> (sample_rate, aiter)`, `design_voice(name, instruct, text, gender, language) -> str`, `ref_audio(voice) -> bytes`, `_parse_sample_rate`, `_wav_streaming_header(sample_rate)`, `PersonaTTS`/`TTSError` — used identically across tasks and tests. `Voice.voice` is consistent in persona.py, the data files, and every test literal. WS payload keys (`speaker_id`) intentionally retained (D-out-of-scope) and the tests assert exactly that.
