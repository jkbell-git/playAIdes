from datetime import datetime
import torch
import uuid
from abc import ABC, abstractmethod
from voice_server_api import SpeechGenerationRequest, VoiceDesignRequest, Speaker
import soundfile as sf
from qwen_tts import Qwen3TTSModel
import logging
from pathlib import Path
# Note: The actual qwen_tts imports would go here in a real environment
# from qwen_tts import Qwen3TTSModel


class BaseTTSEngine(ABC):
    DEFAULT_OUTPUT_PATH = "outputs/tts"
    @abstractmethod
    def generate_speech_file(self, request: SpeechGenerationRequest, speaker: Speaker)-> tuple[str:str]:
        pass
    @abstractmethod
    def generator_speech_stream(self, request: SpeechGenerationRequest, speaker: Speaker):
        pass    
    @abstractmethod
    def generate_voice_design(self, request: VoiceDesignRequest)-> Speaker:
        pass

class Qwen3TTSEngine(BaseTTSEngine):
    MODEL_NAME="QWEN3-TTS"

    def __init__(self, design_model_path: str = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", 
                base_model_path: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                attn_implementation:str="flash_attention_2",
                output_path: str = BaseTTSEngine.DEFAULT_OUTPUT_PATH):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logging.info(f"Device: {self.device}")
        self.dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        # we need to get the device here
        self.output_path = output_path
        if self.device == "cuda":
            self.device_map = "cuda:0"
            self.attn_implementation=attn_implementation
        else:
            self.device_map = "cpu"
            self.attn_implementation=""
        
        logging.info(f"Device map: {self.device_map}")
        logging.info(f"Dtype: {self.dtype}")
        logging.info(f"Attn implementation: {self.attn_implementation}")
        #dont load a model yet just store stuff about the models
        self._model = None
        self.current_model = ""
        self.design_model_path = design_model_path
        self.base_model_path = base_model_path
        self.attn_implementation = attn_implementation
        self.cached_voice_prompts = {}
        
    #generates a speaker and saves relevent files for voice cloning
    def generate_voice_design(self, request: VoiceDesignRequest) -> Speaker:
        """
        Implements voice design based on instruction prompts.
        """
        logging.info(f"Generating voice design for text:{self.design_model_path} {self.device_map} {self.dtype} {self.attn_implementation}...")
        if self.current_model != self.design_model_path:
            self._model = Qwen3TTSModel.from_pretrained(                
                self.design_model_path,
                device_map=self.device_map,
                dtype=torch.bfloat16,
                attn_implementation=self.attn_implementation,
            )
            # store the model we are holding in memory
            self.current_model = self.design_model_path
            logging.info(f"Model loaded: {self.design_model_path}")
        
        wavs, sr = self._model.generate_voice_design(
            text=request.text,
            language=request.language,
            instruct=request.instruct)
        logging.info(f"Generated voice design for text: {request.text} {request.language} {request.instruct}")
        
        speaker_id = str(uuid.uuid4())
        ref_audio = f"{self.output_path}/{speaker_id}_ref.wav"   
        sf.write(ref_audio, wavs[0], sr)   
        logging.info(f"Saved voice design to {self.output_path}/{speaker_id}_ref.wav")
        
        ref_instruct= f"{self.output_path}/{speaker_id}_ref_instruct.txt"        
        with open(ref_instruct, "w") as f:
            f.write(request.instruct)
        
        ref_text = f"{self.output_path}/{speaker_id}_ref_text.txt"        
        with open(ref_text, "w") as f:
            f.write(request.text)

        return Speaker(
            id=speaker_id,
            name=request.name,
            gender=request.gender,
            language=request.language,
            description=request.instruct,
            ref_audio_file=ref_audio,
            ref_text_file=ref_text,
            ref_instruct_file=ref_instruct
        )
    def _cached_voice_prompt(self,speaker: Speaker):
        
        if speaker.id not in self.cached_voice_prompts:            
            self.cached_voice_prompts[speaker.id] = self._model.create_voice_clone_prompt(
                ref_audio=speaker.ref_audio_file,
                ref_text=Path(speaker.ref_text_file).read_text(encoding="utf-8")
            )
        return self.cached_voice_prompts[speaker.id]
    #generates speech from a speaker and text return ref audio file, and text
    def generate_speech_file(self, request: SpeechGenerationRequest, speaker: Speaker) -> tuple[str:str]:
        """
        Implements voice cloning/speech generation using a reference audio.
        """
        logging.info(f"Generating speech for text: {request.text} {speaker.language} {speaker.ref_audio_file} {speaker.ref_text_file}")
        if self.current_model != self.base_model_path:
            self._model = Qwen3TTSModel.from_pretrained(
                self.base_model_path,
                device_map=self.device_map,
                dtype=self.dtype,
                attn_implementation=self.attn_implementation,
            )
            # store the model we are holding in memory
            self.current_model = self.base_model_path
            logging.info(f"Model loaded: {self.base_model_path}")
        # generate the speech   
        voice_prompt = self._cached_voice_prompt(speaker)
        wavs, sr = self._model.generate_voice_clone(
            text=request.text,
            language="English",
            voice_clone_prompt= voice_prompt
            #ref_audio=speaker.ref_audio_file,
            # ref_text=Path(speaker.ref_text_file).read_text(encoding="utf-8")
        )
        
        key= datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_file = f"{self.output_path}/{speaker.id}_{key}.wav"        
        text_file = f"{self.output_path}/{speaker.id}_{key}.txt"   
        
        sf.write(audio_file, wavs[0], sr)
        with open(text_file, "w") as f:
            f.write(request.text)
        logging.info(f"Generated speech for text: {request.text} {speaker.language} {speaker.ref_audio_file} {speaker.ref_text_file}")
        return (audio_file, text_file)
        
    #generate a streaming response with an iter    
    def generator_speech_stream(self, request: SpeechGenerationRequest,speaker: Speaker):        
        logging.info(f"streaming speech for text: {request.text} {speaker.language} {speaker.ref_audio_file} {speaker.ref_text_file}")
        
        if self.current_model != self.base_model_path:
            self._model = Qwen3TTSModel.from_pretrained(
                self.base_model_path,
                device_map=self.device_map,
                dtype=self.dtype,
                attn_implementation=self.attn_implementation,
            )
            # store the model we are holding in memory
            self.current_model = self.base_model_path
            logging.info(f"Model loaded: {self.base_model_path}")
        
        
        voice_prompt = self._cached_voice_prompt(speaker)
        yield from self._model.generate_voice_clone(
            text=request.text,
            language=request.language if request.language else speaker.language,
            voice_clone_prompt= voice_prompt,
            emit_every_frames=12,decode_window_frames=80,
            first_chunk_emit_every=5, first_chunk_frames=48 
            # ref_audio=speaker.ref_audio_file,
            # ref_text=Path(speaker.ref_text_file).read_text(encoding="utf-8")
        )
        
        #key= datetime.now().strftime("%Y%m%d_%H%M%S")
        #audio_file = f"{self.output_path}/{speaker.id}_{key}.wav"        
        #text_file = f"{self.output_path}/{speaker.id}_{key}.txt"   
        
        #with open(text_file, "w") as f:
        #f.write(request.text)
        #logging.info(f"Generated speech for text: {request.text} {speaker.language} {speaker.ref_audio_file} {speaker.ref_text_file}")
        #return (audio_file, text_file)   
