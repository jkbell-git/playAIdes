"""Shared pytest fixtures for the playAIdes test suite.

Design goals:
- Tests never hit the real network unless explicitly marked ``live``.
- Tests never touch the user's ``personas/`` dir on disk; persona ops run
  against a per-test tmp directory.
- ``live`` tests auto-skip when OLLAMA_URL / TTS_URL are absent or the
  endpoints aren't reachable, so the suite is the same whether or not the
  live compose stack is up.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any, Iterator, List, Optional
from urllib.parse import urlparse

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Persona fixtures
# ──────────────────────────────────────────────────────────────────────────────

VALID_PERSONA: dict = {
    "name": "TestBot",
    "back_ground": "A persona used only in tests.",
    "psyche": {"traits": ["calm", "deterministic"]},
    "gender": "Female",
    "language": "English",
}


@pytest.fixture
def valid_persona_dict() -> dict:
    """A minimal-but-valid persona dict that satisfies the Persona schema."""
    return json.loads(json.dumps(VALID_PERSONA))  # deep copy


@pytest.fixture
def tmp_personas_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a tmp personas/ directory seeded with one valid persona.

    Also ``chdir``s into the tmp dir so ``PlayAIdes`` (which uses relative
    ``personas/`` paths) operates entirely inside the sandbox.
    """
    personas = tmp_path / "personas"
    personas.mkdir()
    seeded = personas / "testbot"
    seeded.mkdir()
    (seeded / "persona.json").write_text(json.dumps(VALID_PERSONA, indent=2))
    monkeypatch.chdir(tmp_path)
    return personas


@pytest.fixture
def persona_file(tmp_personas_dir: Path) -> Path:
    return tmp_personas_dir / "testbot" / "persona.json"


# ──────────────────────────────────────────────────────────────────────────────
# LLM / TTS fakes
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm():
    """Return the in-repo MockLLM — deterministic, no network."""
    from model_interfaces import MockLLM
    return MockLLM()


class FakeTTS:
    """In-memory PersonaTTS implementation for tests.

    Records every call so tests can assert behavior without hitting a real
    TTS server or audio device.
    """

    def __init__(self, speaker_uuid: str = "fake-speaker-0001") -> None:
        self.speaker_uuid = speaker_uuid
        self.design_calls: List[Any] = []
        self.file_calls: List[Any] = []
        self.stream_calls: List[Any] = []

    def generate_voice(self, voice_design_request) -> Optional[str]:
        self.design_calls.append(voice_design_request)
        return self.speaker_uuid

    def generate_speech(self, speech_generation_request, output_path=None):  # Protocol method
        return self.generate_speech_file(speech_generation_request, output_path)

    def generate_speech_file(self, speech_generation_request, output_path=None) -> str:
        self.file_calls.append(speech_generation_request)
        return f"{output_path or '/tmp'}/fake.wav"

    def generate_speech_stream(self, speech_generation_request, output_path=None) -> str:
        self.stream_calls.append(speech_generation_request)
        return speech_generation_request.text


@pytest.fixture
def fake_tts() -> FakeTTS:
    return FakeTTS()


# ──────────────────────────────────────────────────────────────────────────────
# IncarnationServer stub — prevents threads/ports during PlayAIdes tests.
# ──────────────────────────────────────────────────────────────────────────────

class StubIncarnationServer:
    """Drop-in replacement for IncarnationServer that records commands."""

    def __init__(self, *args, on_message_callback=None, **kwargs):
        self.host = kwargs.get("host", "stub")
        self.port = kwargs.get("port", 0)
        self.on_message_callback = on_message_callback
        self.commands: List[tuple[str, dict]] = []

    def send_command(self, cmd_type: str, payload: dict = None):
        self.commands.append((cmd_type, payload or {}))


@pytest.fixture
def no_incarnation(monkeypatch: pytest.MonkeyPatch):
    """Replace IncarnationServer with StubIncarnationServer for the test.

    Returns the stub class so tests can inspect ``.commands`` of the instance
    attached to a ``PlayAIdes`` under test.
    """
    import playAIdes as play_mod
    monkeypatch.setattr(play_mod, "IncarnationServer", StubIncarnationServer)
    return StubIncarnationServer


# ──────────────────────────────────────────────────────────────────────────────
# Live-test helpers
# ──────────────────────────────────────────────────────────────────────────────

def _endpoint_reachable(url: Optional[str], timeout: float = 2.0) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def ollama_url() -> str:
    url = os.environ.get("OLLAMA_URL")
    if not _endpoint_reachable(url):
        pytest.skip(f"OLLAMA_URL not reachable (got {url!r}); skipping live test")
    return url  # type: ignore[return-value]


@pytest.fixture(scope="session")
def tts_url() -> str:
    url = os.environ.get("TTS_URL")
    if not _endpoint_reachable(url):
        pytest.skip(f"TTS_URL not reachable (got {url!r}); skipping live test")
    return url  # type: ignore[return-value]
