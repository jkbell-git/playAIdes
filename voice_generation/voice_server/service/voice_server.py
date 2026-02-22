from fastapi import FastAPI, HTTPException
#from fastapi.responses import StreamingResponse
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse , FileResponse, StreamingResponse
from voice_server_api import SpeechGenerationRequest, VoiceDesignRequest
from tts_engine import Qwen3TTSEngine, BaseTTSEngine
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging
import voice_database
import numpy
import torch
import struct
class LoadModelRequest(BaseModel):
    model_name: str

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app_data={}

@asynccontextmanager
async def lifespan(app:FastAPI):
    #initialize database
    try:
        logger.info("Initializing database...")        
        db = voice_database.VoiceDataBase()    

    except Exception as e:

        logger.error(f"Failed to initialize database: {e}")
        db = None
    
    app_data["DB"] = db 
    
    try:
        engine: BaseTTSEngine = Qwen3TTSEngine()
    except Exception as e:
        logger.error(f"Failed to initialize TTS Engine: {e}")
        engine = None
    
    app_data["TTS_ENGINE"] = engine   
    yield 
    #after app closes
    app_data.clear()

app = FastAPI(title="Voice Generation Server", lifespan=lifespan)


@app.post("/load_model")
async def load_model(request: LoadModelRequest):
    try:
        logger.info(f"Loading model: {request.model_name}...")
        if  Qwen3TTSEngine.MODEL_NAME.lower() in request.model_name.lower() :  
            if not isinstance(app_data["TTS_ENGINE"], Qwen3TTSEngine):
                app_data["TTS_ENGINE"] = Qwen3TTSEngine()
            else:
                logger.info(f"Model {request.model_name} already loaded")
        return {"status": "ok", "model_loaded": True}

    except Exception as e:
        logger.error(f"Error loading model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/design")
async def design_voice(request: VoiceDesignRequest):
    if app_data["TTS_ENGINE"] is None:
        raise HTTPException(status_code=503, detail="TTS Engine not initialized")
    
    try:
        logger.info(f"Designing voice with instructions: {request.instruct}...")
        speaker = app_data["TTS_ENGINE"].generate_voice_design(request)
        app_data["DB"].save_speaker(speaker)
        return JSONResponse({"speaker_id": speaker.id}, status_code=200)
    except Exception as e:
        logger.error(f"Error designing voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# async def audio_streamer()
#      """
#     Wrapper for FastAPI: Converts numpy arrays to raw bytes.
#     """
#     for audio_chunk, sr in voice_clone_generator(text):
#         # Convert float32 numpy array to 16-bit PCM bytes for standard players
#         # or use .tobytes() for raw data
#         if isinstance(audio_chunk, torch.Tensor):
#             audio_chunk = audio_chunk.cpu().numpy()
        
#         # Convert to 16-bit PCM for better compatibility
#         pcm_buffer = (audio_chunk * 32767).astype("int16").tobytes()
#         yield pcm_buffer

@app.post("/generate_stream")
async def generate_speech_stream(request: SpeechGenerationRequest):
    if app_data["TTS_ENGINE"] is None:
        raise HTTPException(status_code=503, detail="TTS Engine not initialized")
    
    try:
        logger.info(f"Generating speech for text: {request.text[:50]}...")
        speaker = app_data["DB"].get_speaker(request.speaker_id)
        if not speaker:
            raise HTTPException(status_code=404, detail=f"Speaker '{request.speaker_id}' not found")
        
        def audio_streamer():
            for audio_chunk,sr in app_data["TTS_ENGINE"].generator_speech_stream(request, speaker):
                #logger.info(f"audio chunk instance { audio_chunk} {sr}")
                #if isinstance(audio_chunk, torch.Tensor):
                #audio_chunk = audio_chunk.cpu().numpy()
                #logger.info(f"proccessing chunk")
                # Convert to 16-bit PCM for better compatibility
                pcm_buffer = (audio_chunk * 32767).astype("int16").tobytes()
                yield pcm_buffer
                # else:
                #     logger.error("cannont convert chunk")
                # if isinstance(audio_chunk, list):
                # # Convert list of integers to 16-bit PCM bytes
                #     yield struct.pack(f"{len(audio_chunk)}h", *audio_chunk)
                # # if audio_chunk:
                # #     yield audio_chunk

        return StreamingResponse(audio_streamer(),
        media_type="audio/l16; rate=24000; channels=1")
         #media_type="audio/wav")
    except Exception as e:
        logger.error(f"Error generating speech: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_file")
async def generate_speech_file(request: SpeechGenerationRequest):
    if app_data["TTS_ENGINE"] is None:
        raise HTTPException(status_code=503, detail="TTS Engine not initialized")
    
    try:
        logger.info(f"Generating speech file for text: {request.text[:50]}...")
        speaker = app_data["DB"].get_speaker(request.speaker_id)
        if not speaker:
            raise HTTPException(status_code=404, detail=f"Speaker '{request.speaker_id}' not found")
        generated_speech_wav, generated_speech_text = app_data["TTS_ENGINE"].generate_speech_file(request, speaker)
        
        return FileResponse(path=generated_speech_wav, media_type="audio/wav")
    except Exception as e:
        logger.error(f"Error generating speech file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok", "engine_loaded": app_data["TTS_ENGINE"] is not None}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
