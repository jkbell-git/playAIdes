from abc import ABC, abstractmethod
import requests
import json
from typing import List, Dict, Optional

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
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma3:4b"):
        self.base_url = base_url
        self.model = model

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
            return data.get("message", {}).get("content", "")
        except requests.RequestException as e:
            print(f"Error communicating with Ollama: {e}")
            return "Error: Unable to communicate with the AI model."

class MockLLM(LLMInterface):
    def chat(self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> str:
        last_message = messages[-1]['content'] if messages else ""
        return f"Mock Response: I heard you say '{last_message}'."
