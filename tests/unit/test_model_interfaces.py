"""Unit tests for model_interfaces.py — LLM abstraction + Ollama client."""
from __future__ import annotations

import json

import pytest
import responses

from model_interfaces import LLMError, MockLLM, OllamaLLM


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


class TestOllamaLLM:
    @responses.activate
    def test_happy_path(self):
        responses.post(
            "http://fake-ollama:11434/api/chat",
            json={"message": {"content": "hello back"}},
            status=200,
        )
        client = OllamaLLM(base_url="http://fake-ollama:11434", model="test-model")
        out = client.chat([{"role": "user", "content": "hi"}], system_prompt="sys")
        assert out == "hello back"
        # And the request body contained the system prompt first.
        body = json.loads(responses.calls[0].request.body)
        assert body["model"] == "test-model"
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert body["messages"][-1] == {"role": "user", "content": "hi"}
        assert body["stream"] is False

    @responses.activate
    def test_no_system_prompt(self):
        responses.post(
            "http://fake-ollama:11434/api/chat",
            json={"message": {"content": "ok"}},
            status=200,
        )
        out = OllamaLLM(base_url="http://fake-ollama:11434").chat(
            [{"role": "user", "content": "hi"}]
        )
        assert out == "ok"
        body = json.loads(responses.calls[0].request.body)
        assert body["messages"][0]["role"] == "user"

    @responses.activate
    def test_empty_response_content(self):
        responses.post(
            "http://fake-ollama:11434/api/chat",
            json={"message": {}},  # no content key
            status=200,
        )
        assert OllamaLLM(base_url="http://fake-ollama:11434").chat([]) == ""

    @responses.activate
    def test_http_error_raises_llmerror(self):
        responses.post(
            "http://fake-ollama:11434/api/chat", json={"err": "boom"}, status=500
        )
        with pytest.raises(LLMError, match="Ollama request failed"):
            OllamaLLM(base_url="http://fake-ollama:11434").chat([])

    @responses.activate
    def test_connection_error_raises_llmerror(self):
        # No registered endpoint → ConnectionError → LLMError.
        with pytest.raises(LLMError):
            OllamaLLM(base_url="http://nope-nope-nope:1").chat([])

    @responses.activate
    def test_malformed_json_raises_llmerror(self):
        responses.post(
            "http://fake-ollama:11434/api/chat",
            body="not json",
            status=200,
            content_type="application/json",
        )
        # In modern requests, response.json() raises requests.exceptions.JSONDecodeError
        # which subclasses RequestException — so either error path ends up wrapped.
        with pytest.raises(LLMError):
            OllamaLLM(base_url="http://fake-ollama:11434").chat([])

    def test_env_var_base_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_URL", "http://from-env:99")
        monkeypatch.setenv("OLLAMA_MODEL", "env-model")
        c = OllamaLLM()
        assert c.base_url == "http://from-env:99"
        assert c.model == "env-model"

    def test_explicit_args_win_over_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_URL", "http://from-env:99")
        c = OllamaLLM(base_url="http://explicit:1", model="explicit-model")
        assert c.base_url == "http://explicit:1"
        assert c.model == "explicit-model"
