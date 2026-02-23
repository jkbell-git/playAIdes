from persona import Persona
from pydantic import BaseModel,ConfigDict, field_validator
from model_interfaces import LLMInterface, OllamaLLM
from typing import Optional, List, Dict
from voice_generation.voice_api import PersonaTTS, Qwen3TTS_local, VoiceDesignRequest, SpeechGenerationRequest
from playsound3 import playsound
import json
import logging
from incarnation_server import IncarnationServer
import os

logger = logging.getLogger(__name__)
#this will be the main class for PlayAIdes and manage all currently loaded personas
# will be in charge of routing requests to the service to handle a personas actions/tasks
# I believe we should do as much async as possible due to the nature of how we will be waiting for our services to perform actions

class PlayAIdesArgs(BaseModel): 
    model_config = ConfigDict(arbitrary_types_allowed=True)   
    persona: List[str]
    generate_voice: bool
    use_voice: bool
    use_avatar: bool
    generate_avatar: bool
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
        self.incarnation_server: Optional[IncarnationServer] = IncarnationServer(on_message_callback=self._handle_incarnation_message) if args.use_avatar else None
        self.current_persona: Optional[Persona] = None
        self.chat_history: List[Dict[str, str]] = []
        self.args: PlayAIdesArgs = args
        self.expected_animations = set()
        for persona in args.persona:
            self._load_persona_from_file(persona)
            break  # currently only support one persona at a time

    def _load_persona_from_file(self, filepath: str):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            self.current_persona = Persona(**data)
            logger.info(f"Loaded persona: {self.current_persona.name}")
            self._validate_persona(self.current_persona)
        except Exception as e:
            logger.exception(f"Error loading persona from {filepath}: {e}")
            return
    def _update_persona_file(self,p:Persona):
        with open(f"personas/{p.name.lower()}/persona.json", 'w') as f:
            json.dump(p.model_dump(), f, indent=2)

    def _validate_persona(self,p:Persona):
        
        # validate voice
        if self.args.use_voice:
            self._setup_voice(p)
            
        if self.args.use_avatar:
            self._setup_avatar(p)
        
    
    def _setup_voice(self,p:Persona):
        if self.tts is None:
            logger.error("TTS not initialized")
            return
        # is the voice design generation needed?
        if (self.args.generate_voice and 
        (p.persona_voice is None or not p.persona_voice.is_voice_valid())):
            voice_instruct = p.persona_voice.voice_instruct if p.persona_voice.voice_instruct else []
            voice_instruct.append(f"Background: {p.back_ground}. ")
            voice_instruct.append(f"{', '.join(p.psyche.traits)}. ")
            # send a generate voice request to the TTS service
            p.persona_voice.speaker_uuid = self.tts.generate_voice(VoiceDesignRequest(            
                text=p.back_ground,
                language=p.language,
                instruct=f" ".join(voice_instruct),
                #output_path=f"personas/{p.name}/tts",                
                name=p.name,
                gender=p.gender
            ))
            #update the persona file with the new voice
            self._update_persona_file(p)

    def _setup_avatar(self, p: Persona):
        if self.incarnation_server is None:
            logger.error("IncarnationServer not initialized")
            return
        if p.avatar is not None and p.avatar.model_url:
            self.expected_animations.clear()
            logger.info(f"Sending load_model command for avatar: {p.avatar.model_url}")
            self.incarnation_server.send_command("load_model", {"url": p.avatar.model_url})
            
        else:
            logger.info("No avatar configured for this persona.")

    def load_default_animations(self):
        # We send set_background when the client connects and sends model_loaded,
        # ensuring the client is actually ready to receive it.
        if self.current_persona and self.current_persona.avatar:
            bg_url = self.current_persona.avatar.background_url
            if bg_url:
                logger.info(f"Sending set_background for avatar: {bg_url}")
                self.incarnation_server.send_command("set_background", {"url": bg_url})

        if self.current_persona.avatar.model_url.lower().endswith('.vrm'):
            animation_dir = "incarnation/public/vrma/animations"
            if os.path.exists(animation_dir):
                logger.info("Loading VRMA animations...")
                for filename in os.listdir(animation_dir):
                    if filename.lower().endswith('.vrma'):
                        anim_url = f"vrma/animations/{filename}"
                        anim_name = os.path.splitext(filename)[0].split(".vrma")[0]
                        self.expected_animations.add(anim_name)
                        logger.info(f"Loading animation: {anim_name} from {anim_url}")
                        self.incarnation_server.send_command("load_vrma_animation", {
                            "url": anim_url,
                            "name": anim_name
                        })

    def _handle_incarnation_message(self, msg: dict):
        logger.info(f"Incarnation callback: {msg}")
        if msg.get("type") == "status":
            state = msg['payload'].get("state")
            # if state == None and "payload" in msg:
            #     state = msg["payload"].get("state")
            payload = msg['payload']
            logger.info(f"Incarnation state: {state}")
            if state == "animation_loaded":
                anim_name = payload.get("name") # payload is actually a dict from getModelInfo in JS, so it has animations array, not name
                if not anim_name and payload.get("animations"):
                    # For Mixamo/VRMA the payload returns the entire animations array and a "loaded" array that has the actual name 
                    loaded_arr = payload.get("loaded", [])
                    if loaded_arr:
                        anim_name = loaded_arr[0]
                
                if anim_name:
                    logger.info(f"Animation {anim_name} loaded. Expected animations: {self.expected_animations}")
                    if anim_name in self.expected_animations:
                        self.expected_animations.remove(anim_name)
                        
                if not self.expected_animations:
                    logger.info("All auto-loaded animations finished loading. Playing initial animation...")
                    self.incarnation_server.send_command("play_animation", {
                        "name": "cute_greeting_twirl",
                        "loop": False
                    })
            if state == "animation_finished":
                anim_name = payload.get("name")
                logger.info(f"Animation {anim_name} finished playing.")
                idle_anim = self.current_persona.avatar.idle_animation if (self.current_persona and self.current_persona.avatar) else "idle"
                logger.info(f"Switching to idle animation '{idle_anim}' and focusing camera...")
                self.incarnation_server.send_command("play_animation", {
                     "name": idle_anim,
                     "loop": True,
                     "crossFade": 0.5
                })
                self.incarnation_server.send_command("focus_camera")
            if state == "model_loaded":
                self.load_default_animations()

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
            )
        
        return response
            