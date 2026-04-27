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

# Default clip to fall back to when a persona has no intro_animation and no
# idle_animation. Must match a file in incarnation/public/vrma/animations/
# (the shared VRMA pack); model_pose is the standing-still T-pose-replacement.
DEFAULT_IDLE_ANIMATION = "model_pose"

# Cap chat_histories at the most recent N messages on load. Older entries
# are trimmed in-place so the LLM context window stays bounded. Configurable
# later via env / persona-level override.
CHAT_HISTORY_CAP = 80


def find_default_persona_id(personas_dir) -> Optional[str]:
    """Pick the boot persona id from a personas directory.

    Returns:
        - Id of the persona whose `is_default: true`, if any.
        - Else id of the first persona alphabetically (with a warning).
        - Else None when no personas are found.

    Skips directories that don't contain a parseable persona.json.
    """
    from pathlib import Path
    personas_dir = Path(personas_dir)
    if not personas_dir.is_dir():
        return None

    candidates = []
    for entry in sorted(personas_dir.iterdir()):
        if not entry.is_dir():
            continue
        pfile = entry / "persona.json"
        if not pfile.exists():
            continue
        try:
            data = json.loads(pfile.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        candidates.append((entry.name, bool(data.get("is_default", False))))

    if not candidates:
        return None

    for pid, is_default in candidates:
        if is_default:
            return pid

    fallback = candidates[0][0]
    logger.warning(
        "No is_default=true persona found; falling back to first alphabetically: %s",
        fallback,
    )
    return fallback


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
    api_key: Optional[str] = None
    ha_url: Optional[str] = None
    ha_token: Optional[str] = None
    ha_default_agent_id: Optional[str] = None
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
        self.incarnation_server: Optional[IncarnationServer] = IncarnationServer(
            on_message_callback=self._handle_incarnation_message,
            state_provider=lambda: {
                "active_persona_id": (
                    self.current_persona.name.strip().lower().replace(" ", "_")
                    if self.current_persona else None
                ),
            },
        ) if args.use_avatar else None
        self.current_persona: Optional[Persona] = None
        # chat_histories: persona_id → list of message dicts. Loaded lazily
        # per persona from personas/<id>/chat_history.json on first access.
        # See _load_history / _save_history / delete_history for persistence.
        self.chat_histories: Dict[str, List[Dict[str, str]]] = {}
        # Backwards-compat alias for chat() — points at the active persona's
        # history once a persona is loaded.
        self.chat_history: List[Dict[str, str]] = []
        self.args: PlayAIdesArgs = args
        self.expected_animations = set()
        # Tracks animation names the frontend has actually loaded. The
        # post-load play branch consults this so configured-but-missing
        # clip names (or a missing DEFAULT_IDLE_ANIMATION) gracefully
        # degrade to whatever clips are available, instead of sending
        # name=<unknown> and leaving the model T-posed.
        self.loaded_animations: set = set()

        from ha_client import HAClient
        self.ha_client: Optional[HAClient] = None
        if args.ha_url and args.ha_token:
            self.ha_client = HAClient(args.ha_url, args.ha_token)
            logger.info("HA client configured for %s", args.ha_url)
        elif args.ha_url or args.ha_token:
            logger.warning(
                "HA partially configured (need both ha_url and ha_token); "
                "HA features disabled."
            )

        # Per-persona conversation_id cache for HA's multi-turn context.
        # Cleared on persona swap by Task 9 hook.
        self._ha_conversation_ids: dict[str, str] = {}

        for persona in args.persona:
            self._load_persona_from_file(persona)
            break  # currently only support one persona at a time

        if not self.ha_client:
            for p in self.list_personas():
                if p.get("house_words"):
                    logger.warning(
                        "Persona %r has house_words but HA is not configured; "
                        "delegation will be disabled.",
                        p.get("name", "?"),
                    )

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
        # Keep the legacy chat_history alias pointing at the active
        # persona's history (so any caller that reads self.chat_history
        # directly still works during the transition).
        active_id = self.current_persona.name.strip().lower().replace(" ", "_")
        self.chat_history = self._load_history(active_id)
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

    def delete_persona(self, persona_id: str) -> bool:
        """Permanently delete a persona's directory.

        Returns True if the persona existed and was removed. False if no
        persona by that id was found. Refuses path-traversal attempts and
        silently no-ops if the requested id is the currently-active one
        (the running session would crash if we yanked its files out).
        """
        if not persona_id or "/" in persona_id or "\\" in persona_id or persona_id in {".", ".."}:
            logger.warning("Refusing to delete persona with suspicious id: %r", persona_id)
            return False
        if (self.current_persona
                and self.current_persona.name.strip().lower().replace(" ", "_") == persona_id):
            logger.warning("Refusing to delete the currently-active persona: %s", persona_id)
            return False
        p_dir = os.path.join("personas", persona_id)
        if not os.path.isdir(p_dir):
            return False
        import shutil
        shutil.rmtree(p_dir)
        logger.info("Deleted persona: %s", persona_id)
        return True

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
            self.incarnation_server.send_command("load_model", {
                "url": p.avatar.model_url,
                "spawn_point": list(p.avatar.spawn_point or []),
                "camera_target": list(p.avatar.camera_target or []),
            })

        else:
            logger.info("No avatar configured for this persona.")

    def load_default_animations(self):
        # We send set_background when the client connects and sends model_loaded,
        # ensuring the client is actually ready to receive it. Multi-TV: route
        # to clients bound to this persona id only.
        if not self.current_persona:
            return
        active_id = self.current_persona.name.strip().lower().replace(" ", "_")
        if self.current_persona.avatar:
            bg_url = self.current_persona.avatar.background_url
            if bg_url:
                logger.info(f"Sending set_background for avatar: {bg_url}")
                self.incarnation_server.broadcast_to_persona(
                    active_id, "set_background", {"url": bg_url},
                )

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
                        self.incarnation_server.broadcast_to_persona(
                            active_id, "load_vrma_animation",
                            {"url": anim_url, "name": anim_name},
                        )

    def _resolve_clip_name(self, preferred: Optional[str]) -> str:
        """Pick an animation name to play, gracefully degrading when the
        preferred or default name isn't actually loaded.

        Resolution order:
          1. `preferred` (caller's intro_animation or idle_animation), if loaded
          2. DEFAULT_IDLE_ANIMATION, if loaded
          3. First loaded clip alphabetically (resilient to any VRMA pack —
             generic "VRMA_01.vrma" filenames work without persona config)
          4. DEFAULT_IDLE_ANIMATION as a last-ditch (won't actually play but
             the frontend logs "[AnimationManager] clip not found" cleanly)
        """
        if preferred and preferred in self.loaded_animations:
            return preferred
        if DEFAULT_IDLE_ANIMATION in self.loaded_animations:
            return DEFAULT_IDLE_ANIMATION
        if self.loaded_animations:
            return sorted(self.loaded_animations)[0]
        return DEFAULT_IDLE_ANIMATION

    def _history_path(self, persona_id: str):
        """Path to a persona's chat_history.json. Path-traversal guarded."""
        from pathlib import Path
        if not persona_id or "/" in persona_id or "\\" in persona_id or persona_id in {".", ".."}:
            raise ValueError(f"Suspicious persona_id: {persona_id!r}")
        return Path("personas") / persona_id / "chat_history.json"

    def _load_history(self, persona_id: str) -> List[Dict[str, str]]:
        """Load a persona's chat history from disk, cap at the most recent
        CHAT_HISTORY_CAP messages, store in chat_histories, and return it.
        Missing file → empty list. Idempotent."""
        if persona_id in self.chat_histories:
            return self.chat_histories[persona_id]
        path = self._history_path(persona_id)
        history: List[Dict[str, str]] = []
        if path.exists():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read %s: %s — starting empty", path, e)
                history = []
        if len(history) > CHAT_HISTORY_CAP:
            history = history[-CHAT_HISTORY_CAP:]
        self.chat_histories[persona_id] = history
        return history

    def _save_history(self, persona_id: str):
        """Persist a persona's chat history atomically via tempfile + os.replace.
        If os.replace raises, the original file is left intact."""
        import tempfile
        path = self._history_path(persona_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        history = self.chat_histories.get(persona_id, [])
        # Write to a sibling tempfile, then atomically rename over the target.
        with tempfile.NamedTemporaryFile(
            mode="w", dir=str(path.parent), delete=False,
            prefix=".chat_history.", suffix=".json.tmp",
        ) as tf:
            json.dump(history, tf, ensure_ascii=False, indent=2)
            tmp_path = tf.name
        try:
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def delete_history(self, persona_id: str):
        """Clear a persona's history both in memory and on disk.
        Not exposed to the WS in v1 — callable for future /forget commands."""
        self.chat_histories.pop(persona_id, None)
        path = self._history_path(persona_id)
        if path.exists():
            path.unlink()

    def set_persona(self, persona_id: str) -> Optional[Persona]:
        """Reload the active persona at runtime.

        Loads personas/<id>/persona.json, runs _validate_persona, swaps
        current_persona, and ensures the per-persona chat history is
        loaded into chat_histories. Idempotent: no-op if id matches the
        currently-active persona.

        Path-traversal guarded the same way delete_persona is. Raises
        PersonaLoadError on any failure (the WS handler turns this into
        a persona_changed{ok: false, error}).
        """
        if not persona_id or "/" in persona_id or "\\" in persona_id or persona_id in {".", ".."}:
            raise PersonaLoadError(f"Suspicious persona_id: {persona_id!r}")

        # Idempotency: same id as the currently-active persona → no-op.
        if (self.current_persona and
                self.current_persona.name.strip().lower().replace(" ", "_") == persona_id):
            # Still ensure history is loaded.
            self._load_history(persona_id)
            return self.current_persona

        path = os.path.join("personas", persona_id, "persona.json")
        if not os.path.exists(path):
            raise PersonaLoadError(f"Persona not found: {persona_id}")

        # Reset HA conversation context on every persona change so the next
        # session starts a fresh HA context.
        self._ha_conversation_ids.pop(persona_id, None)

        # Re-use the existing loader (raises PersonaLoadError on bad input).
        self._load_persona_from_file(path)
        self._load_history(persona_id)
        return self.current_persona

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

        if msg_type == "user_input":
            text = (payload.get("text") or "").strip()
            if not text:
                return
            persona_id = (payload.get("persona_id") or "").strip() or None
            try:
                self.chat(text, persona_id=persona_id)
            except Exception as e:
                logger.exception(f"user_input chat() failed: {e}")
            return

        if msg_type == "set_active_persona":
            requested_id = (payload.get("id") or "").strip()
            prev_id = (self.current_persona.name.strip().lower().replace(" ", "_")
                       if self.current_persona else None)
            try:
                persona = self.set_persona(requested_id)
            except (PersonaLoadError, ValueError) as e:
                # Error case: the requesting client just bound to requested_id
                # via the WS endpoint; route the failure back to that client
                # only. No-op for other TVs.
                self.incarnation_server.broadcast_to_persona(
                    requested_id, "persona_changed",
                    {"ok": False, "error": str(e)},
                )
                return

            # All persona-scoped messages route to clients bound to the new
            # persona id (the requesting client is now bound to it; other
            # TVs showing other personas are unaffected). Spec §3 multi-TV.
            self.incarnation_server.broadcast_to_persona(
                requested_id, "persona_changed",
                {"ok": True, "persona": persona.model_dump()},
            )

            # If we actually swapped, tell the browser to unload the old VRM
            # and load the new one. Same persona → skip (model is still loaded).
            if prev_id != requested_id:
                self.incarnation_server.broadcast_to_persona(
                    requested_id, "unload_model", {},
                )
                if persona.avatar and persona.avatar.model_url:
                    self.incarnation_server.broadcast_to_persona(
                        requested_id, "load_model",
                        {
                            "url": persona.avatar.model_url,
                            "spawn_point": list(persona.avatar.spawn_point or []),
                            "camera_target": list(persona.avatar.camera_target or []),
                        },
                    )
                # Background carries on the existing flat-image path until Phase 5.
                if persona.avatar and persona.avatar.background_url:
                    self.incarnation_server.broadcast_to_persona(
                        requested_id, "set_background",
                        {"url": persona.avatar.background_url},
                    )
                # Different persona: post-load animation flow handles intro
                # replay once load_default_animations finishes (existing
                # Phase-1 code).
            else:
                # Same persona re-summon (e.g. wake-after-dismiss). Model
                # is still loaded; just replay the intro clip directly.
                intro = (persona.avatar.intro_animation
                         if (persona.avatar) else None)
                if intro:
                    self.incarnation_server.broadcast_to_persona(
                        requested_id, "play_animation",
                        {"name": intro, "loop": False},
                    )

            # History rehydration (deferred chat-panel UI lands in Phase 5;
            # frame is sent now so phase-4 clients can stash it). Per spec
            # line 361, sent ONLY to the requesting client.
            self.incarnation_server.broadcast_to_persona(
                requested_id, "history_loaded",
                {
                    "persona_id": requested_id,
                    "history": list(self.chat_histories.get(requested_id, [])),
                },
            )
            return

        if msg_type == "dismiss_persona":
            # The WS endpoint already cleared this client's binding registry
            # entry; PlayAIdes itself has no further action — chat history
            # is preserved on disk per spec §2 dismiss subsection.
            logger.info("Persona dismissed (binding cleared by WS layer)")
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

        if msg_type == "delete_persona":
            pid = payload.get("id")
            if pid:
                ok = self.delete_persona(pid)
                self.incarnation_server.send_command(
                    "persona_deleted",
                    {"id": pid, "ok": ok},
                )
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
                    self.loaded_animations.add(anim_name)
                    logger.info(f"Animation {anim_name} loaded. Expected animations: {self.expected_animations}")
                    if anim_name in self.expected_animations:
                        self.expected_animations.remove(anim_name)

                if not self.expected_animations:
                    intro = (self.current_persona.avatar.intro_animation
                             if (self.current_persona and self.current_persona.avatar)
                             else None)
                    fallback_idle = (self.current_persona.avatar.idle_animation
                                     if (self.current_persona and self.current_persona.avatar)
                                     else None)
                    clip_name = self._resolve_clip_name(intro or fallback_idle)
                    # Loop only when we did NOT successfully play the configured
                    # intro (intros are one-shot greetings; idles loop).
                    is_intro = bool(intro) and clip_name == intro
                    logger.info(f"All auto-loaded animations finished loading. Playing clip: {clip_name}")
                    active_id = self.current_persona.name.strip().lower().replace(" ", "_")
                    self.incarnation_server.broadcast_to_persona(
                        active_id, "play_animation",
                        {"name": clip_name, "loop": False if is_intro else True},
                    )
            if state == "animation_finished":
                anim_name = payload.get("name")
                logger.info(f"Animation {anim_name} finished playing.")
                configured_idle = (self.current_persona.avatar.idle_animation
                                   if (self.current_persona and self.current_persona.avatar)
                                   else None)
                idle_anim = self._resolve_clip_name(configured_idle)
                logger.info(f"Switching to idle animation '{idle_anim}' and focusing camera...")
                active_id = self.current_persona.name.strip().lower().replace(" ", "_")
                self.incarnation_server.broadcast_to_persona(
                    active_id, "play_animation",
                    {"name": idle_anim, "loop": True, "crossFade": 0.5},
                )
                self.incarnation_server.broadcast_to_persona(
                    active_id, "focus_camera", {},
                )
            if state == "model_loaded":
                # Push the active persona's matching config to clients bound
                # to this persona — TVs showing OTHER personas should keep
                # their own activePersona state. Spec §3 multi-TV memory.
                if self.current_persona:
                    active_id = self.current_persona.name.strip().lower().replace(" ", "_")
                    self.incarnation_server.broadcast_to_persona(
                        active_id, "persona_active",
                        {
                            "name": self.current_persona.name,
                            "wake_words": list(self.current_persona.wake_words or []),
                            "dismiss_words": list(self.current_persona.dismiss_words or []),
                        },
                    )
                self.load_default_animations()

    def chat(self, user_input: str, persona_id: Optional[str] = None) -> str:
        if not self.current_persona:
            return "No persona loaded."

        # Resolve the persona to route this turn against. Defaults to active.
        target_id = persona_id or self.current_persona.name.strip().lower().replace(" ", "_")

        # Ensure that persona's history is loaded (lazy from disk).
        history = self._load_history(target_id)

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

        history.append({"role": "user", "content": user_input})

        # ─ HA delegation via house_words ────────────────────────────────
        from match_keywords import match_keyword_prefix
        house_words = self.current_persona.house_words or []
        matched, residual = match_keyword_prefix(user_input, house_words)
        if matched and self.ha_client:
            agent_id = (
                self.current_persona.ha_agent_id
                or self.args.ha_default_agent_id
            )
            conv_id = self._ha_conversation_ids.get(target_id)
            ha_resp = self.ha_client.converse(
                residual, agent_id=agent_id, conversation_id=conv_id,
            )
            if ha_resp.conversation_id:
                self._ha_conversation_ids[target_id] = ha_resp.conversation_id
            response = ha_resp.speech_text
            if (
                ha_resp.success
                and self.current_persona.rephrase_ha_response
            ):
                rephrase_prompt = (
                    f"You are {self.current_persona.name}. "
                    f"Rephrase this in your voice, keeping the meaning "
                    f"intact: {ha_resp.speech_text}"
                )
                try:
                    response = self.llm.chat(
                        [{"role": "user", "content": rephrase_prompt}],
                        system_prompt=None,
                    )
                except Exception as e:
                    logger.warning(
                        "Rephrase LLM call failed, falling back to verbatim: %s", e,
                    )
                    response = ha_resp.speech_text
        else:
            # ─ Existing persona-LLM path (unchanged) ────────────────────
            response = self.llm.chat(history, system_prompt=system_prompt)

        # Broadcast the reply text to any connected viewer so its subtitle
        # band can render before TTS audio arrives. No-op if the
        # incarnation server isn't running (CLI-only mode).
        if self.incarnation_server is not None:
            # Broadcast only to clients bound to this persona — every TV
            # showing Silver sees Silver's reply; TVs showing other personas
            # are unaffected. (Falls back gracefully when no clients are bound.)
            self.incarnation_server.broadcast_to_persona(
                target_id,
                "assistant_message",
                {"text": response, "persona_id": target_id},
            )

        if self.args.use_voice:
            if not (self.current_persona.persona_voice
                    and self.current_persona.persona_voice.speaker_uuid):
                logger.warning(
                    "Persona %s has no voice config; skipping lip_sync",
                    self.current_persona.name,
                )
            elif self.args.use_avatar and self.incarnation_server:
                import urllib.parse
                safe_text = urllib.parse.quote(response)
                # Use the proxy endpoint — the browser will play audio and do lip sync
                proxy_url = f"http://localhost:8765/api/tts/proxy?text={safe_text}&speaker_id={self.current_persona.persona_voice.speaker_uuid}"
                if self.current_persona.language:
                    proxy_url += f"&language={urllib.parse.quote(self.current_persona.language)}"

                logger.info(f"Sending start_lip_sync: {proxy_url}")
                # Route to the same persona's bound clients only — spec §3.
                self.incarnation_server.broadcast_to_persona(
                    target_id, "start_lip_sync", {"url": proxy_url},
                )
                # Audio playback and lip sync are handled by the browser.
                # Lip sync auto-stops when the audio stream ends.
            else:
                # No avatar — play audio on the server side
                self.tts.generate_speech_stream(SpeechGenerationRequest(
                    text=response,
                    speaker_id=self.current_persona.persona_voice.speaker_uuid,
                    language=self.current_persona.language or "English")
                )

        history.append({"role": "assistant", "content": response})

        # Trim to cap and persist atomically.
        if len(history) > CHAT_HISTORY_CAP:
            history[:] = history[-CHAT_HISTORY_CAP:]
        self._save_history(target_id)

        return response
            