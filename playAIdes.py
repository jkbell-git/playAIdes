from persona import Persona
from pydantic import BaseModel,ConfigDict, field_validator
from model_interfaces import LLMInterface, OllamaLLM
from typing import Optional, List, Dict
from voice_generation.voice_api import PersonaTTS, Qwen3TTS_local, VoiceDesignRequest, SpeechGenerationRequest
import json
import logging
from incarnation_server import IncarnationServer
import os

logger = logging.getLogger(__name__)


class PersonaLoadError(RuntimeError):
    """Raised when a persona file cannot be loaded or parsed."""


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
        except FileNotFoundError as e:
            logger.error("Persona file not found: %s", filepath)
            raise PersonaLoadError(f"Persona file not found: {filepath}") from e
        except json.JSONDecodeError as e:
            logger.error("Persona file %s contains invalid JSON: %s", filepath, e)
            raise PersonaLoadError(f"Invalid JSON in persona file {filepath}: {e}") from e
        try:
            self.current_persona = Persona(**data)
        except Exception as e:
            logger.error("Persona file %s failed schema validation: %s", filepath, e)
            raise PersonaLoadError(f"Persona file {filepath} failed validation: {e}") from e
        logger.info("Loaded persona: %s", self.current_persona.name)
        self._validate_persona(self.current_persona)
    def _update_persona_file(self,p:Persona):
        with open(f"personas/{p.name.lower()}/persona.json", 'w') as f:
            json.dump(p.model_dump(), f, indent=2)

    def list_personas(self) -> List[dict]:
        personas_dir = "personas"
        os.makedirs(personas_dir, exist_ok=True)
        persona_list = []
        for d in os.listdir(personas_dir):
            p_dir = os.path.join(personas_dir, d)
            if os.path.isdir(p_dir):
                p_file = os.path.join(p_dir, "persona.json")
                if os.path.exists(p_file):
                    try:
                        with open(p_file, 'r') as f:
                            data = json.load(f)
                            data["id"] = d
                            persona_list.append(data)
                    except Exception as e:
                        logger.error(f"Error reading {p_file}: {e}")
        return persona_list

    def get_persona_by_id(self, persona_id: str) -> Optional[dict]:
        p_file = os.path.join("personas", persona_id, "persona.json")
        if os.path.exists(p_file):
             with open(p_file, 'r') as f:
                 data = json.load(f)
                 data["id"] = persona_id
                 return data
        return None

    def create_persona(self, name: str, description: str) -> dict:
        persona_id = name.strip().lower().replace(" ", "_")
        p_dir = os.path.join("personas", persona_id)
        os.makedirs(p_dir, exist_ok=True)
        p_data = {
            "name": name,
            "back_ground": description,
            "psyche": {"traits": []},
            "gender": "Female",
            "language": "English",
            "avatar": None,
            "persona_voice": None,
            "memories": None
        }
        with open(os.path.join(p_dir, "persona.json"), "w") as f:
            json.dump(p_data, f, indent=2)
        p_data["id"] = persona_id
        return p_data

    def update_persona(self, persona_id: str, data: dict) -> dict:
        p_dir = os.path.join("personas", persona_id)
        os.makedirs(p_dir, exist_ok=True)
        p_file = os.path.join(p_dir, "persona.json")
        if "id" in data:
            del data["id"]
        with open(p_file, "w") as f:
            json.dump(data, f, indent=2)
        data["id"] = persona_id
        return data

    def _validate_persona(self,p:Persona):
        
        # validate voice
        if self.args.use_voice:
            self._setup_voice(p)
            
        # Avatar setup is now deferred until the frontend connects and sends {"state": "ready"}
        
    
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
        msg_type = msg.get("type")
        payload = msg.get("payload", {})
        
        if msg_type == "get_personas":
            self.incarnation_server.send_command("personas_list", {"personas": self.list_personas()})
            return
            
        if msg_type == "get_persona":
            pid = payload.get("id")
            if pid:
                p = self.get_persona_by_id(pid)
                if p:
                    self.incarnation_server.send_command("persona_data", {"persona": p})
            return
            
        if msg_type == "create_persona":
            name = payload.get("name", "Unknown")
            desc = payload.get("description", "")
            p = self.create_persona(name, desc)
            self.incarnation_server.send_command("persona_created", {"persona": p})
            return
            
        if msg_type == "update_persona":
            pid = payload.get("id")
            if pid:
                p = self.update_persona(pid, payload)
                self.incarnation_server.send_command("persona_updated", {"persona": p})
            return
            
        if msg_type == "model_uploaded":
            pid = payload.get("persona_id")
            url = payload.get("url")
            if pid and url:
                p_data = self.get_persona_by_id(pid)
                if p_data:
                    if not p_data.get("avatar"):
                        p_data["avatar"] = {}
                    p_data["avatar"]["model_url"] = url
                    self.update_persona(pid, p_data)
                    # Forward to WS client
                    self.incarnation_server.send_command("model_uploaded", {"persona_id": pid, "url": url})
            return
            
        if msg_type == "animation_uploaded":
            pid = payload.get("persona_id")
            url = payload.get("url")
            name = payload.get("name")
            if pid and url and name:
                p_data = self.get_persona_by_id(pid)
                if p_data:
                    if "animations" not in p_data or not p_data["animations"]:
                        p_data["animations"] = []
                    if not any(a.get("name") == name for a in p_data["animations"]):
                        p_data["animations"].append({"name": name, "url": url})
                    self.update_persona(pid, p_data)
                    # Forward to WS client
                    self.incarnation_server.send_command("animation_uploaded", {"persona_id": pid, "name": name, "url": url})
            return
            
        if msg_type == "design_voice":
            req = VoiceDesignRequest(
                text=payload.get("sample_text", "hello"),
                language=payload.get("language", "English"),
                instruct=payload.get("instruct", ""),
                name=payload.get("name", "voice"),
                gender=payload.get("gender", "Female")
            )
            speaker_uuid = self.tts.generate_voice(req)
            ref_audio_url = f"http://localhost:{self.incarnation_server.port}/api/speakers/{speaker_uuid}/ref_audio"
            self.incarnation_server.send_command("voice_designed", {
                "speaker_id": speaker_uuid, 
                "name": payload.get("name"),
                "ref_audio_url": ref_audio_url
            })
            return
            
        if msg_type == "test_voice":
            req = SpeechGenerationRequest(
                text=payload.get("text", "hello"),
                language=payload.get("language", "English"),
                speaker_id=payload.get("speaker_id", "")
            )
            try:
                # We save audio to public/outputs so it's statically addressable by frontend via /outputs/...
                output_path = "incarnation/public/outputs/tts/temp"
                os.makedirs(output_path, exist_ok=True)
                output_file = self.tts.generate_speech_file(req, output_path=output_path)
                # Ensure the url is relative to the root for the frontend
                filename = os.path.basename(output_file)
                url = f"http://localhost:8765/outputs/tts/temp/{filename}"
                self.incarnation_server.send_command("voice_tested", {"url": url})
            except Exception as e:
                logger.error(f"Voice test failed: {e}")
                self.incarnation_server.send_command("voice_test_failed", {"error": str(e)})
            return

        if msg_type == "status":
            state = msg['payload'].get("state")
            payload = msg['payload']
            logger.info(f"Incarnation state: {state}")
            if state == "ready":
                if self.current_persona and self.args.use_avatar:
                    logger.info("Incarnation client ready, sending avatar setup")
                    self._setup_avatar(self.current_persona)
            
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
            