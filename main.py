#!/usr/bin/env python3
import sys
import os
from playAIdes import PlayAIdes,PlayAIdesArgs
from model_interfaces import OllamaLLM
import pydantic

def main(services_args:PlayAIdesArgs):
    print("Initializing PlayAIdes...")
    
    # Initialize Core
    # We can default to Ollama, but user might want to configure this later.
    # For now, hardcoded to Ollama as per plan.
    ai = PlayAIdes(services_args)
    
    # Load Persona
    # only handles 1 person for now
    # persona_path = services_args.persona[0]
    # if not os.path.exists(persona_path):
    #     print(f"Error: Persona file '{persona_path}' not found.")
    #     return

    # #ai._load_persona_from_file(persona_path)
    
    # # if not ai.current_persona:
    # #     print("Failed to load persona. Exiting.")
    # #     return
    # if services_args.generate_voice:
    #     ai._setup_voice(ai.current_persona)
    

    print(f"Chatting with {ai.current_persona.name}. Type 'exit!' or 'quit!' to stop.")
    print("-" * 50)

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit!", "quit!"]:
                print("Goodbye!")
                break
            
            if not user_input.strip():
                continue

            response = ai.chat(user_input)
            

            print(f"{ai.current_persona.name}: {response}")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PlayAIdes")
    parser.add_argument("--persona", type=str, default="personas/Rin/tsundere.json", help="Path to persona file")
    parser.add_argument("--generate_voice",default=False, action="store_true", help="Generate voice for persona")
    parser.add_argument("--use_voice", default=False, action="store_true", help="Use voice for persona")
    args = parser.parse_args()
    casted_args = PlayAIdesArgs(persona=[args.persona],
    generate_voice=args.generate_voice,
    use_voice=args.use_voice)
    main(casted_args)
