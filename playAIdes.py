from persona import Persona
from pydantic import BaseModel,ConfigDict, field_validator
from model_interfaces import LLMInterface, OllamaLLM
from typing import Optional, List, Dict
from voice_generation.voice_api import PersonaTTS, Qwen3TTS_local, VoiceDesignRequest, SpeechGenerationRequest
from playsound3 import playsound
import json
#this will be the main class for PlayAIdes and manage all currently loaded personas
# will be in charge of routing requests to the service to handle a personas actions/tasks
# I believe we should do as much async as possible due to the nature of how we will be waiting for our services to perform actions

class PlayAIdesArgs(BaseModel): 
    model_config = ConfigDict(arbitrary_types_allowed=True)   
    persona: List[str]
    generate_voice: bool
    use_voice: bool
    llm: LLMInterface = None
    tts: Optional[PersonaTTS] = None
    @field_validator("tts")
    @classmethod
    def validate_tts(cls, v):
        if v is None:
            return v
        if not isinstance(v, PersonaTTS):
            raise TypeError("tts must implement PersonaTTS protocol")
        return v

class PlayAIdes:
    def __init__(self, args: PlayAIdesArgs):
        self.llm: Optional[LLMInterface] = args.llm if args.llm else OllamaLLM() # Default to Ollama
        self.tts: Optional[PersonaTTS] = args.tts if args.tts else Qwen3TTS_local() #Default to Qwen3TTS_local
        self.current_persona: Optional[Persona] = None
        self.chat_history: List[Dict[str, str]] = []
        self.args: PlayAIdesArgs = args
        for persona in args.persona:
            self._load_persona_from_file(persona)
            break  # currently only support one persona at a time

    def _load_persona_from_file(self, filepath: str):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            self.current_persona = Persona(**data)
            print(f"Loaded persona: {self.current_persona.name}")
            self._validate_persona(self.current_persona)
        except Exception as e:
            print(f"Error loading persona from {filepath}: {e}")
            import traceback
            traceback.print_exc()
            return
    def _update_persona_file(self,p:Persona):
        with open(f"personas/{p.name}/persona.json", 'w') as f:
            json.dump(p.model_dump(), f, indent=2)

    def _validate_persona(self,p:Persona):
        
        # validate voice
        if self.args.use_voice:
            self._setup_voice(p)
        
    
    def _setup_voice(self,p:Persona):
        if self.tts is None:
            print("Error: TTS not initialized")
            return
        # is the voice design generation needed?
        if (self.args.generate_voice and 
        (p.persona_voice is None or not p.persona_voice.is_voice_valid())):
            # send a generate voice request to the TTS service
            p.persona_voice.speaker_uuid = self.tts.generate_voice(VoiceDesignRequest(            
                text=p.back_ground,
                language=p.language,
                instruct=f"{', '.join(p.psyche.traits)}. ",
                #output_path=f"personas/{p.name}/tts",                
                name=p.name,
                gender=p.gender
            ))
            #update the persona file with the new voice
            self._update_persona_file(p)
            
        

    def chat(self, user_input: str) -> str:
        if not self.current_persona:
            return "No persona loaded."

        # Construct system prompt based on persona
        system_prompt = (f"You are impersonating a this character named"
        f"{self.current_persona.name}. "
        f"Your background is: {self.current_persona.back_ground}. "
        )
        if self.current_persona.psyche and self.current_persona.psyche.traits:
            system_prompt += (f"Your Psyche contains the following traits"
            f"{', '.join(self.current_persona.psyche.traits)}. ")
        if self.current_persona.memories and self.current_persona.memories.memories:
            system_prompt += (f"your memories are: {self.current_persona.memories.memories}.")

        
        system_prompt += "be a helpful assistant to the user. with yor responses in character"

        if self.current_persona.persona_voice and self.current_persona.persona_voice.is_voice_valid():
            system_prompt += (f"your response will be sent to a TTS service to be spoken."
            f"please make sure your response does not contain things not spoken. no emojis")

        self.chat_history.append({"role": "user", "content": user_input})
        
        response = self.llm.chat(self.chat_history, system_prompt=system_prompt)
        if self.args.use_voice:
            self.tts.generate_speech_stream(SpeechGenerationRequest(
                text=response,
                speaker_id=self.current_persona.persona_voice.speaker_uuid),
            #output_path=f"outputs/tts/{self.current_persona.name}")
            )
            #playsound(sound_file)
        
        self.chat_history.append({"role": "assistant", "content": response})
        return response

