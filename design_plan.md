# PlayAides
Is a framework for creating and managing AI personas that can be interacted. they will be visulized through and visusal web browser.


## Persona(s) 
Personas will be entities of PlayAIdes and consist of the following:

- 3D avatar that is visulized in a web browser
- LLM Responses used to personify the persona
- Optional Voice that will be a TTS model of the LLM response
````
                 Stimulus Input 
                        │
                        ▼
        ┌────────────────────────────────────┐
        │   LLM Core Brain / Pesona Manager  │
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
````

# Software Services 

### PlayAIdes
- This will be a python application that will be used to create and manage personas it will also be the brains of all the other components it should be able to run multiple personas at once and commuicate with the other componets using http /web sockets. this will implement all the logic for personas and the routing to persona componets.
- The PlayAIdes will communicate with LLM(s) and tts models as well as send data to the avatar and voice components using http /websockets.

### incarnation 
This will be the js web browser service that will give personas a body to inhabit its own component
  - implemented using three.js
  - will support displaying the 3D model for the persona
  - will support lip sync for the 3D model
  - will support animations for the 3D model
  - will support web sockets for real time communication with PlayAIdes
  - will support http for communication with PlayAIdes
  - will support multiple personas at once(Future)
  - will support multiple 3D models at once(Future)
  - will support multiple voice models at once(Future)

### Persona Componets
1. 3d avatar - this will use the incarnations service andwill give personas a body to inhabit its own component
        1. Web frontend 
        2. 3D model viewer using three.js
        3. 
        4. will have lip sync for the 3D model
        5. A sperate dashboard to change settings 
        
2. voice - this will be a voice tts integration for the avatar independent component that will interact with some sort of tts model or services

### LLM Inteface 
python package that can commuicate with local hosted or cloud based LLM's and tts models. 
