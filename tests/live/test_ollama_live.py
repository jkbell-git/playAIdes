"""Live E2E smoke test against a real Ollama container.

Skipped automatically unless OLLAMA_URL points at a reachable endpoint —
that fixture handling lives in ``tests/conftest.py``.
"""
from __future__ import annotations

import os

import pytest

from model_interfaces import OllamaLLM

pytestmark = [pytest.mark.live, pytest.mark.slow]


def test_ollama_chat_smoke(ollama_url: str):
    model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    client = OllamaLLM(base_url=ollama_url, model=model)
    out = client.chat(
        [{"role": "user", "content": "Reply with exactly one word: hello"}],
        system_prompt="You are concise.",
    )
    assert isinstance(out, str)
    assert out.strip() != ""
