import json
import responses
from model_interfaces import MockLLM, OpenAICompatLLM


def test_mock_llm_chat_stream_yields_single_chunk():
    out = list(MockLLM().chat_stream([{"role": "user", "content": "hello"}]))
    assert out == ["Mock Response: I heard you say 'hello'."]


@responses.activate
def test_openai_chat_stream_parses_sse_deltas():
    body = (
        'data: {"choices":[{"delta":{"content":"He"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"llo"}}]}\n\n'
        'data: [DONE]\n\n'
    )
    responses.add(
        responses.POST, "http://fake-llm:11434/v1/chat/completions",
        body=body, status=200, content_type="text/event-stream",
    )
    llm = OpenAICompatLLM(base_url="http://fake-llm:11434/v1", model="m")
    out = list(llm.chat_stream([{"role": "user", "content": "hi"}]))
    assert out == ["He", "llo"]
