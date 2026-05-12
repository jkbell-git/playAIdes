"""Unit tests for model_interfaces.py — MockLLM stub.

OpenAICompatLLM coverage lives in tests/unit/test_openai_compat_llm.py.
"""
from __future__ import annotations

from model_interfaces import MockLLM


class TestMockLLM:
    def test_echoes_last_message(self):
        out = MockLLM().chat([{"role": "user", "content": "hello"}])
        assert "hello" in out
        assert out.startswith("Mock Response")

    def test_empty_messages_safe(self):
        # Should not raise even if there are no messages.
        out = MockLLM().chat([])
        assert isinstance(out, str)

    def test_system_prompt_ignored(self):
        # MockLLM intentionally ignores the system prompt — it's a test double.
        out = MockLLM().chat(
            [{"role": "user", "content": "hi"}], system_prompt="you are a pirate"
        )
        assert "hi" in out
