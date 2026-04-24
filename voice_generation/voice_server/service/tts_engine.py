from datetime import datetime
import torch
import uuid
from abc import ABC, abstractmethod
from voice_server_api import SpeechGenerationRequest, VoiceDesignRequest, Speaker
import soundfile as sf
from qwen_tts import Qwen3TTSModel
import logging
from pathlib import Path
import gc
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
                output_path: str = BaseTTSEngine.DEFAULT_OUTPUT_PATH,
                optimize_for_streaming:bool=True,
                preload_base: bool = True):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        self.output_path = output_path
        if self.device == "cuda":
            self.attn_implementation = attn_implementation
        else:
            # flash-attention requires CUDA — fall back to the default eager impl.
            self.attn_implementation = None
        self.optimize_for_streaming = optimize_for_streaming
        logging.info(f"Device: {self.device}")
        logging.info(f"Dtype: {self.dtype}")
        logging.info(f"Attn implementation: {self.attn_implementation}")

        # No model in VRAM yet; lazy-loaded via _ensure_*_model().
        self._model = None
        self.current_model = ""
        self.design_model_path = design_model_path
        self.base_model_path = base_model_path
        self.cached_voice_prompts = {}

        # Preload the streaming/clone model so first request is fast and any
        # CUDA init failure is visible at boot (rather than buried inside a
        # streaming response 500).
        if preload_base:
            self._ensure_base_model()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _clear_vram(self):
        """Release the currently-loaded model and reset CUDA allocator."""
        self.current_model = ""
        self._model = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _load_model(self, path: str, dtype):
        """
        Load a Qwen3TTS model safely.

        `Qwen3TTSModel` is a wrapper (not an ``nn.Module``) so it has no
        ``.to()`` method — we have to rely on ``device_map`` to place
        weights on the GPU at load time.

        The catch: transformers sets ``low_cpu_mem_usage=True`` whenever
        ``device_map`` is provided, which leaves weights on the ``meta``
        device. With this specific transformers+accelerate combination,
        ``dispatch_model`` then calls ``model.to(device)`` on those meta
        tensors and blows up with:

            NotImplementedError: Cannot copy out of meta tensor; no data!

        Forcing ``low_cpu_mem_usage=False`` makes transformers materialise
        the weights on CPU first; accelerate's dispatch then has real
        tensors to move, and the meta path never fires.
        """
        logging.info(f"Loading TTS model: {path} → {self.device} ({self.dtype})")
        kwargs = {
            "dtype": dtype,
            # Force weight materialisation before dispatch. See docstring above.
            "low_cpu_mem_usage": False,
        }
        if self.device == "cuda":
            kwargs["device_map"] = "cuda"
        if self.attn_implementation:
            kwargs["attn_implementation"] = self.attn_implementation
        return Qwen3TTSModel.from_pretrained(path, **kwargs)

    def _ensure_base_model(self):
        """Make sure the streaming/clone model is loaded. Idempotent."""
        if self.current_model == self.base_model_path and self._model is not None:
            return
        self._clear_vram()
        self._model = self._load_model(self.base_model_path, self.dtype)
        self.current_model = self.base_model_path
        # Reset the voice-prompt cache — it holds tensors bound to the old model.
        self.cached_voice_prompts = {}
        logging.info(f"Base model ready: {self.base_model_path}")

    def _ensure_design_model(self):
        """Make sure the voice-design model is loaded. Idempotent."""
        if self.current_model == self.design_model_path and self._model is not None:
            return
        self._clear_vram()
        self._model = self._load_model(self.design_model_path, self.dtype)
        self.current_model = self.design_model_path
        self.cached_voice_prompts = {}
        logging.info(f"Design model ready: {self.design_model_path}")
    #generates a speaker and saves relevent files for voice cloning
    def generate_voice_design(self, request: VoiceDesignRequest) -> Speaker:
        """
        Implements voice design based on instruction prompts.
        """
        logging.info(f"Generating voice design → {request.name} ({request.language})")
        self._ensure_design_model()

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
        logging.info(f"Generating speech file → speaker={speaker.id} text={request.text[:60]!r}")
        self._ensure_base_model()
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
    def generator_speech_stream(self, request: SpeechGenerationRequest, speaker: Speaker):
        logging.info(f"Streaming speech → speaker={speaker.id} text={request.text[:60]!r}")
        self._ensure_base_model()
        # NOTE: streaming-optimisation compile path is disabled — it crashes
        # under the current torch/python versions in the container. Revisit
        # once the env is upgraded. See the old commented-out block in git
        # history for the intended configuration.

        voice_prompt = self._cached_voice_prompt(speaker)
        for audio_chunks,sr in self._model.stream_generate_voice_clone(
            text=request.text,
            language=request.language if request.language else speaker.language,
            voice_clone_prompt= voice_prompt,
            emit_every_frames=12,
            decode_window_frames=80,            
            first_chunk_emit_every=5,
            first_chunk_decode_window=48,
            first_chunk_frames=48 
            # ref_audio=speaker.ref_audio_file,
            # ref_text=Path(speaker.ref_text_file).read_text(encoding="utf-8")
        ):
            yield (audio_chunks,sr)
        
 