#currently copy pasted from voice_generation_server/voice.py 
#will need to refactor to be more modular
from pydantic import BaseModel
import requests
from typing import Protocol,runtime_checkable,Optional
from datetime import datetime
import os
from voice_generation.voice_server.service.voice_server_api import SpeechGenerationRequest,VoiceDesignRequest
import sounddevice as sd
import numpy as np
# class SpeechGenerationRequest(BaseModel):    
#     text: str
#     speaker_id: str
#     language: str = "English"   
#     emotion: Optional[list[str]] = None

# #this is used to create a speaker
# class VoiceDesignRequest(BaseModel):     
#     text: str 
#     language: str = "English"
#     instruct: str    
#     name: str
#     gender: str
    
@runtime_checkable
class PersonaTTS(Protocol):
    def generate_voice(self, voice_design_request: VoiceDesignRequest) -> str| None:
        pass

    def generate_speech(self, speech_generation_request: SpeechGenerationRequest,output_path:Optional[str] = None) -> None:
        pass

class Qwen3TTS_local:
    BASE_URL = "http://localhost:8008"
    def __init__(self):
        pass
    def generate_voice(self, voice_design_request: VoiceDesignRequest) -> Speaker:        
        id = None
        response = requests.post(f"{self.BASE_URL}/design", json=voice_design_request.model_dump())
        
        if response.status_code == 200:
            id = response.json()["speaker_id"]
            print("Successfully designed voice. Saved to: test_design_output.wav")
        else:
            print(f"Failed to design voice. Status: {response.status_code}, Error: {response.text}")
        return id
    
    def generate_speech_file(self, speech_generation_request: SpeechGenerationRequest,output_path:Optional[str] = None) -> str:
        output_file = None
        if output_path is None:
            output_path = f"outputs/tts/temp/{speech_generation_request.speaker_id}"
            os.makedirs(output_path, exist_ok=True)

        output_file  = f"{output_path}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        response = requests.post(f"{self.BASE_URL}/generate_file", json=speech_generation_request.model_dump())
    
        if response.status_code == 200:
            with open(output_file, "wb") as f:
                f.write(response.content)
            print(f"Successfully generated speech. Saved to: {output_file}")
        else:
            print(f"Failed to generate speech. Status: {response.status_code}, Error: {response.text}")
        
        return output_file

    def generate_speech_stream(self, speech_generation_request: SpeechGenerationRequest,output_path:Optional[str] = None) -> str:
        SAMPLE_RATE = 24000 
        CHANNELS = 1
        with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16') as stream:
            print(f"Streaming and playing: '{speech_generation_request.text}'")     
            with requests.post(f"{self.BASE_URL}/generate_stream",json=speech_generation_request.model_dump(), stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=2048):
                    if chunk:
                        # Convert raw bytes back to numpy array
                        audio_data = np.frombuffer(chunk, dtype=np.int16)
                        # Send directly to your local speakers
                        stream.write(audio_data)
    
        # output_file = None
        # if output_path is None:
        #     output_path = f"outputs/tts/temp/{speech_generation_request.speaker_id}"
        #     os.makedirs(output_path, exist_ok=True)

        # output_file  = f"{output_path}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        # response = requests.post(f"{self.BASE_URL}/generate", json=speech_generation_request.model_dump())
    
        # if response.status_code == 200:
        #     with open(output_file, "wb") as f:
        #         f.write(response.content)
        #     print(f"Successfully generated speech. Saved to: {output_file}")
        # else:
        #     print(f"Failed to generate speech. Status: {response.status_code}, Error: {response.text}")
        
        #return output_file