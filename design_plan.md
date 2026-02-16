# PlayAides
Is a framework for creating and managing AI personas that can be interacted with. they will be visulized through and visusal web browser.


## Persona(s) 
Personas will be entities of PlayAIdes and consist of the following:
### Persona Components
- Avatar: 3D avatar that is visulized in a web browser
- Actions: LLM Responses used to personify the Persona
- Voice: Optional Voice that will be sourced from a TTS model (Future)
- Memory: this will be used to store the Personas memories and will be used to give the Persona a sense of self and continuity. Most likely a vector database to start with.(Future)
- Psyche: A prompt of traits and characteristics that will be used to personify the Persona

### Persona Requirements
- Personas should be able to interact with User
- Personas should be able to interact with other Personas(Future)
- Personas should be able to remember past interactions (Future)
- Personas should be able to learn from interactions(Future)
- Personas should be able to have a sense of time and place (Future)
- Personas should be able to use tools to interact with the world (Future)
- Personas should have a clear distiction between roleplaying and there actual actions. (I.E given access to a file there personality would want to delete. We need to ensure this does not happen.) I would want this reenforced by the LLM prompt. Maybe some kind of safety check before using tools.(Future)
### Presona Stimulus
- User Input(Text, Voice,Actions(Future))
- Software triggered events : Optional (API calls, Other Personas, etc) Rate Limit (Future)
- Time based events: Optional (Future)
- Location based events: Optional (Future)
## Core loop of PlayAIdes
````
                 Stimulus Input 
                        │
                        ▼
        ┌────────────────────────────────────┐
        │   LLM Core Brain / PlayAides Core  │
        └────────────────────────────────────┘
                         │
                         ▼
             Persona Selection Layer
                         │
                         ▼
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
      Avatar A         Avatar B         Avatar C
    (voice + 3D)     (voice + 3D)     (voice + 3D)
         │               │               │
         └───────────────┼───────────────┘
                         ▼
        Updated Selected Personas components
````

# Software Services 

## PlayAIdes
- This will be a python application that will be used to create and manage personas it will also be the brains of all the other components it should be able to run multiple personas at once and communicate with the other components using http /web sockets. this will implement all the logic for personas and the routing to persona components.
- The PlayAIdes will communicate with LLM(s) and tts models as well as send data to the avatar and voice components using http /websockets. PlayAIdes will use the Model Inference Interface to communicate with LLM(s) and tts models.
- PlayAIdes will direct all persona related services :
  - Incaration services
  - LLM services
  - TTS services

## incarnation 
This will be the js web browser service that will give personas a body to inhabit its own component
- Requirements:
  - will support displaying the 3D model for the Persona
    - ~~Local 3D model File (glTF/GLB, VRM, etc)~~
    - Cloud based 3D model (Future)
    - will support  http or web sockets for real time communication with PlayAIdes
      - a rough api is currently in place and testable with incarnation/test_incarnation.py
    - Support an optional separate dashboard for the Persona incarnation configuration
    - Voice file playback(Optional) maybe we do this in Python instead of JS?
    - will support lip sync for the 3D model(Future)  
    - will support multiple personas at once(Future)
    - will support multiple 3D models at once(Future)
  
  Features we need soon:
  - will be a standalone service that can be run in a web browser (Started currently demo that supports one model and playing anamations)
    - need to add a way to add background images(Future)
    - add a idle animation that loads on default (Future)
    - would be cool to support unreal or unity (Future)
    - dashboard for configuration(Future)
    - will be configured from PlayAIdes using json 
    
  - implemented using three.js and vite for now
    - first draft successfully runs in a web browser
    - Known issues: 
      - Miximo models mapping to VRM sucks
      - I dont really understand 3d Model Files XD
  
  - features with rough prototypes:    
    - will support animations for the 3D model - 
    - will support expressions for the 3D model
    - will support visemes for the 3D model
  
  

# Interfaces
## Model Inferance Interface 
python package that will be used to communicate with local hosted or cloud based LLM's and tts models. local models will be supported using Ollama VLLM. Open models can be supported using the OpenAI API or other compatible APIs. 
## Json websocket and http Interface
PlayAides will communicate with the incarnation services using a Json Interface. This interface will be used to send data to the avatar and voice components as well as receive data from the avatar and voice components. 