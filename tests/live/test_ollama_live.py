"""Live E2E smoke test against a real Ollama container (via OpenAI-compat /v1).

Skipped automatically unless LLM_URL points at a reachable endpoint —
that fixture handling lives in ``tests/conftest.py``.
"""
from __future__ import annotations

import os

import pytest

from model_interfaces import OpenAICompatLLM

pytestmark = [pytest.mark.live, pytest.mark.slow]


def test_ollama_chat_smoke(llm_url: str):
    model = os.environ.get("LLM_MODEL", "gemma3:4b")
    client = OpenAICompatLLM(base_url=llm_url, model=model)
    out = client.chat(
        [{"role": "user", "content": "Reply with exactly one word: hello"}],
        system_prompt="You are concise.",
    )
    assert isinstance(out, str)
    assert out.strip() != ""
