import sys
import os
from playAIdes import PlayAIdes
from model_interfaces import OllamaLLM

def main():
    print("Initializing PlayAIdes...")
    
    # Initialize Core
    # We can default to Ollama, but user might want to configure this later.
    # For now, hardcoded to Ollama as per plan.
    ai = PlayAIdes(llm_interface=OllamaLLM())
    
    # Load Persona
    persona_path = "personas/handy.json"
    if not os.path.exists(persona_path):
        print(f"Error: Persona file '{persona_path}' not found.")
        return

    ai.load_persona_from_file(persona_path)
    
    if not ai.current_persona:
        print("Failed to load persona. Exiting.")
        return

    print(f"Chatting with {ai.current_persona.name}. Type 'exit' or 'quit' to stop.")
    print("-" * 50)

    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
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
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
