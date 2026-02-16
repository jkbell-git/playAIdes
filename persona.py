from pydantic import BaseModel

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

class Voice(BaseModel): #optional
    voice_url: str # this can also be a local file path

#probably start as a local file but VectorDB and embedding is were I really want to do 
#we will need some kind of compress or collapse to reduce ths size of tokens we will be 
#passing.
class Memories(BaseModel):
    memory_url: str # this can also be a local file path

#we are going to want to load this frrom a json file to start
class Persona(BaseModel):
    name: str    
    avatar: Optional[Avatar] = None
    voice: Optional[Voice] = None
    psyche: Psyche
    memories: Optional[Memories] = None
    