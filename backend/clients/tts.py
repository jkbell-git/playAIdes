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
