import persona
from pydantic import BaseModel
from model_interfaces import LLMInterface, OllamaLLM, MockLLM
import json
from typing import Optional, List, Dict

#this will be the main class for PlayAIdes and manage all currently loaded personas
# will be in charge of routing requests to the service to handle a personas actions/tasks
# I believe we should do as much async as possible due to the nature of how we will be waiting for our services to perform actions
class PlayAIdes:
    def __init__(self, llm_interface: LLMInterface = None):
        self.llm = llm_interface if llm_interface else OllamaLLM() # Default to Ollama
        self.current_persona: Optional[persona.Persona] = None
        self.chat_history: List[Dict[str, str]] = []

    def load_persona_from_file(self, filepath: str):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            self.current_persona = persona.Persona(**data)
            print(f"Loaded persona: {self.current_persona.name}")
        except Exception as e:
            print(f"Error loading persona from {filepath}: {e}")

    def chat(self, user_input: str) -> str:
        if not self.current_persona:
            return "No persona loaded."

        # Construct system prompt based on persona
        system_prompt = f"You are {self.current_persona.name}. "
        if self.current_persona.psyche and self.current_persona.psyche.traits:
            traits = ", ".join(self.current_persona.psyche.traits)
            system_prompt += f"Your traits are: {traits}. "
        
        system_prompt += "Respond to the user's input in character."

        self.chat_history.append({"role": "user", "content": user_input})
        
        response = self.llm.chat(self.chat_history, system_prompt=system_prompt)
        
        self.chat_history.append({"role": "assistant", "content": response})
        return response

