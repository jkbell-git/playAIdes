from pydantic import BaseModel

class Psyhe(BaseModel):
    traits: list[str]

class Avatar(BaseModel):
    model_url: str # this can also be a local file path
    animations_url: str # this can also be a local folder path

class Voice(BaseModel):
    voice_url: str # this can also be a local file path

class Memories(BaseModel):
    memory_url: str # this can also be a local file path

class Persona(BaseModel):
    name: str    
    avatar: Avatar
    voice: Voice
    psyche: Psyhe
    memories: Memories
    