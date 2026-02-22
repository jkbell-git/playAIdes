import requests
import os

BASE_URL = "http://localhost:8008"

def test_voice_design():
    print("Testing Voice Design...")
    payload = {
        "text": "hello Im your handy assistant ask me anything and I can help you",
        "language": "English",
        "instruct": "Female British voice. Speak in a dignified tone that show your elegance and professionalism",
        "output_path": "outputs",
        "name":"Artoria",
        "gender":"Female"
    }
    response = requests.post(f"{BASE_URL}/design", json=payload)
    
    if response.status_code == 200:
        with open("test_design_output.wav", "wb") as f:
            f.write(response.content)
        print("Successfully designed voice. Saved to: test_design_output.wav")
    else:
        print(f"Failed to design voice. Status: {response.status_code}, Error: {response.text}")

def test_speech_generation():
    print("\nTesting Speech Generation...")
    payload = {
        "output_path": "outputs",
        "text": "Hello master, for today tasks you have the following: a meeting at noon and a workout in the evening.",
        "speaker": {
            "name": "Artoria",
            "gender": "Female",
            "language": "English",
            "description":"Female British voice. Speak in a dignified tone that show your elegance and professionalism",
            "ref_audio_file": "outputs/Artoria_ref.wav",
            "ref_text_file": "outputs/Artoria_ref_text.txt",
            "ref_instruct_file": "outputs/Artoria_ref_instruct.txt"
        },
        # "emotion": ["neutral"],
        # "language": "English"
    }
    response = requests.post(f"{BASE_URL}/generate", json=payload)
    
    if response.status_code == 200:
        with open("test_speech_output.wav", "wb") as f:
            f.write(response.content)
        print("Successfully generated speech. Saved to: test_speech_output.wav")
    else:
        print(f"Failed to generate speech. Status: {response.status_code}, Error: {response.text}")

if __name__ == "__main__":
    # Ensure the server is running before executing this
    test_voice_design()
    test_speech_generation()
