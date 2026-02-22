from pydantic import BaseModel
#from  voice_generation.voice_api
#the Following classes are used to define the persona
# Most likely the will be to be based to the acting LLM/ AI model
# weather it be via prompt or some MCP tool calling system
# we want a clear layer of abstraction between the persona 

from typing import List, Optional

class Psyche(BaseModel): #quirks, traits things that makie this persona unique
    traits: List[str]

class Avatar(BaseModel): #optional
    model_url: str # this can also be a local file path
    animations_url: str # this can also be a local folder path
    animation_list: List[str] # we need to get the animation list from the model and also
    #add animations we have loaded

class Voice(BaseModel): #optional
    #speaker: Speaker # this can also be a local file path
    speaker_uuid: Optional[str] = None
    def is_voice_valid(self) -> bool:
        return self.speaker_uuid is not None
#probably start as a local file but VectorDB and embedding is were I really want to do 
#we will need some kind of compress or collapse to reduce ths size of tokens we will be 
#passing.
class Memories(BaseModel):
    memories: str # this can also be a local file path
    # probably need a memory type for retrieval
    # need to add a method for compaction
    # need a method for adding memories

#we are going to want to load this frrom a json file to start
class Persona(BaseModel):
    name: str    
    back_ground:str    
    psyche: Psyche
    gender: str
    language: str = "English"    
    avatar: Optional[Avatar] = None
    persona_voice: Optional[Voice] = None    
    memories: Optional[Memories] = None
    