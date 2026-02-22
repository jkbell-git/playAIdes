from pydantic import BaseModel
from typing import Optional


class Speaker(BaseModel):
    id: str
    name: str
    gender: str
    language: str
    description: str # this is the instruct string based during voice design
    ref_audio_file: str = ""
    ref_text_file: str = ""
    ref_instruct_file: str = ""


class SpeechGenerationRequest(BaseModel):
    
    text: str
    speaker_id: str
    language: str = "English"
    #output_path: Optional[str] = None
    emotion: Optional[list[str]] = None

#this is used to create a speaker
class VoiceDesignRequest(BaseModel):     
    text: str 
    language: str = "English"
    instruct: str    
    name: str
    gender: str
    