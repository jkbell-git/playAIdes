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

class OllamaLLM(LLMInterface):
    def __init__(self, base_url: Optional[str] = None,
    model: Optional[str] = None):
    #model: str = "gpt-oss:20b"):
        import os
        self.base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "gemma3:4b")

    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/chat"
        
        # Prepare payload
        payload_messages = []
        
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})

        payload_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error("Error communicating with Ollama at %s: %s", url, e)
            raise LLMError(f"Ollama request failed: {e}") from e
        except ValueError as e:  # json decode
            logger.error("Malformed JSON from Ollama: %s", e)
            raise LLMError(f"Ollama returned non-JSON response: {e}") from e
        return data.get("message", {}).get("content", "")

class MockLLM(LLMInterface):
    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        last_message = messages[-1]['content'] if messages else ""
        return f"Mock Response: I heard you say '{last_message}'."
