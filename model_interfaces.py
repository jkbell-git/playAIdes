from abc import ABC, abstractmethod
import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when an LLM backend call fails (network error, bad status, bad JSON)."""


class LLMInterface(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        """
        Send a chat request to the LLM.
        
        Args:
            messages: A list of dictionaries with 'role' and 'content' keys.
            system_prompt: An optional system prompt to prepend or use as context.
            
        Returns:
            The content of the LLM's response.
        """
        pass

class OpenAICompatLLM(LLMInterface):
    """OpenAI-compatible chat completions client.

    Talks to any /v1/chat/completions endpoint — Ollama (which serves
    OpenAI-compat at /v1 since 0.1.30), llamacpp-wrapper, vLLM, OpenAI
    itself, etc. Backend choice is a deployment decision: set LLM_URL
    to the right /v1 base URL.

    Default timeout is 120s to cover llamacpp-wrapper cold-start
    (~25-30s for Q4 models when llama-swap spawns the llama-server
    child). Harmless slack for warm Ollama.
    """

    def __init__(self, base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: float = 120.0):
        import os
        self.base_url = (
            base_url or os.environ.get("LLM_URL", "http://localhost:11434/v1")
        ).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL", "gemma3:4b")
        self.timeout = timeout

    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/chat/completions"
        msgs: List[Dict[str, str]] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(messages)
        payload = {"model": self.model, "messages": msgs, "stream": False}

        try:
            r = requests.post(url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.error("Error communicating with LLM at %s: %s", url, e)
            raise LLMError(f"LLM request failed: {e}") from e
        except ValueError as e:  # json decode
            logger.error("Malformed JSON from LLM: %s", e)
            raise LLMError(f"LLM returned non-JSON response: {e}") from e

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        if content:
            return content
        # Gemma 4 may put thinking tokens in reasoning_content when content
        # is empty (e.g. truncated mid-reasoning). Surface that rather than
        # returning an empty string.
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            logger.warning(
                "LLM returned only reasoning_content; using as fallback"
            )
            return reasoning
        return ""

class MockLLM(LLMInterface):
    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        last_message = messages[-1]['content'] if messages else ""
        return f"Mock Response: I heard you say '{last_message}'."
