"""Unit tests for OpenAICompatLLM (HTTP mocked with `responses`)."""
import pytest
import responses
from model_interfaces import OpenAICompatLLM, LLMError


BASE_URL = "http://llm.test/v1"


@responses.activate
def test_chat_returns_message_content_on_success():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={
            "choices": [
                {"message": {"role": "assistant", "content": "Hello there"}}
            ]
        },
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="test-model")
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result == "Hello there"


@responses.activate
def test_chat_prepends_system_prompt_when_provided():
    captured = {}

    def callback(request):
        import json as _json
        captured["body"] = _json.loads(request.body)
        return (200, {}, '{"choices":[{"message":{"role":"assistant","content":"ok"}}]}')

    responses.add_callback(
        responses.POST, f"{BASE_URL}/chat/completions", callback=callback,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="test-model")
    llm.chat(
        [{"role": "user", "content": "hi"}],
        system_prompt="You are helpful.",
    )
    msgs = captured["body"]["messages"]
    assert msgs[0] == {"role": "system", "content": "You are helpful."}
    assert msgs[1] == {"role": "user", "content": "hi"}
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["stream"] is False


@responses.activate
def test_chat_falls_back_to_reasoning_content_when_content_empty():
    """Gemma 4 may put thinking tokens in reasoning_content with empty content."""
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={
            "choices": [
                {"message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "Let me think about this...",
                }}
            ]
        },
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result == "Let me think about this..."


@responses.activate
def test_chat_prefers_content_over_reasoning_content_when_both_present():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={
            "choices": [
                {"message": {
                    "role": "assistant",
                    "content": "The answer is 42",
                    "reasoning_content": "Let me think...",
                }}
            ]
        },
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    assert llm.chat([{"role": "user", "content": "hi"}]) == "The answer is 42"


@responses.activate
def test_chat_returns_empty_string_when_both_fields_empty():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={"choices": [{"message": {"role": "assistant", "content": ""}}]},
        status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    assert llm.chat([{"role": "user", "content": "hi"}]) == ""


@responses.activate
def test_chat_raises_llmerror_on_http_500():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        json={"error": "internal"}, status=500,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


@responses.activate
def test_chat_raises_llmerror_on_connection_error():
    # No registered endpoint → requests.ConnectionError → LLMError.
    llm = OpenAICompatLLM(base_url="http://nope-nope-nope:1/v1", model="m", timeout=1.0)
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


@responses.activate
def test_chat_raises_llmerror_on_non_json_response():
    responses.add(
        responses.POST,
        f"{BASE_URL}/chat/completions",
        body="not json", status=200,
    )
    llm = OpenAICompatLLM(base_url=BASE_URL, model="m")
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])


def test_constructor_strips_trailing_slash_from_base_url():
    llm = OpenAICompatLLM(base_url=f"{BASE_URL}/", model="m")
    assert llm.base_url == BASE_URL


def test_constructor_reads_env_vars_when_args_omitted(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://from-env.test/v1")
    monkeypatch.setenv("LLM_MODEL", "from-env-model")
    llm = OpenAICompatLLM()
    assert llm.base_url == "http://from-env.test/v1"
    assert llm.model == "from-env-model"


def test_constructor_uses_defaults_when_no_args_no_env(monkeypatch):
    monkeypatch.delenv("LLM_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = OpenAICompatLLM()
    assert llm.base_url == "http://localhost:11434/v1"
    assert llm.model == "gemma3:4b"


def test_explicit_args_win_over_env(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://from-env:99/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    llm = OpenAICompatLLM(base_url="http://explicit:1/v1", model="explicit-model")
    assert llm.base_url == "http://explicit:1/v1"
    assert llm.model == "explicit-model"
