from pydantic import BaseModel, model_validator
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
    animations_url: Optional[str] = None # this can also be a local folder path
    idle_animation: Optional[str] = "idle" # default idle animation name
    intro_animation: Optional[str] = None # plays once on activation, before idle
    animation_list: Optional[List[str]] = None # we need to get the animation list from the model and also
    #add animations we have loaded
    background_url: Optional[str] = None
    spawn_point: Optional[List[float]] = None
    camera_target: Optional[List[float]] = None

class Voice(BaseModel): #optional
    #speaker: Speaker # this can also be a local file path
    voice: Optional[str] = None          # registry voice UUID (was speaker_uuid)
    voice_instruct: Optional[list[str]] = None
    def is_voice_valid(self) -> bool:
        return self.voice is not None
#probably start as a local file but VectorDB and embedding is were I really want to do 
#we will need some kind of compress or collapse to reduce ths size of tokens we will be 
#passing.
class Memories(BaseModel):
    memories: str # this can also be a local file path
    # probably need a memory type for retrieval
    # need to add a method for compaction
    # need a method for adding memories

class AnimationClip(BaseModel):
    """A custom uploaded animation bound to a persona (creator page /
    animation_uploaded). Top-level `animations` in persona.json."""
    name: str
    url: str

class TriggerOn(BaseModel):
    phrase: Optional[str] = None          # deterministic voice-phrase match
    event: Optional[str] = None           # inbound event name (Plan 2)
    match: Optional[dict] = None          # shallow payload conditions (Plan 2)

    @model_validator(mode="after")
    def require_phrase_or_event(self) -> "TriggerOn":
        if self.phrase is None and self.event is None:
            raise ValueError("TriggerOn must set at least one of 'phrase' or 'event'")
        return self

class TriggerDo(BaseModel):
    skill: str
    params: dict = {}

class Trigger(BaseModel):
    on: TriggerOn
    do: TriggerDo

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
    animations: Optional[List[AnimationClip]] = None  # custom uploads (creator)
    wake_words: Optional[List[str]] = None
    dismiss_words: Optional[List[str]] = None
    is_default: bool = False
    house_words: List[str] = []
    skills: List[str] = []                # enabled skill names (the flat skill-tree)
    triggers: List[Trigger] = []
    rephrase_ha_response: bool = False
    ha_agent_id: Optional[str] = None
