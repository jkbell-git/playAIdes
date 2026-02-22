import requests
import os
from playsound3 import playsound
from voice_server_api import VoiceDesignRequest, SpeechGenerationRequest
import sounddevice as sd
import numpy as np

BASE_URL = "http://localhost:8008"
id = ""generate_speech
def test_voice_design():
     print("Testing Voice Design...")
     payload = VoiceDesignRequest(
          text= "Hello Master, I am your Servant And Protector.",
          language="English",
          instruct="Female British voice. You are a Knight of the Round Table. Speak in a dignified tone that show your elegance and professionalism",
          name="Artoria",
          gender="Female"
     )
     response = requests.post(f"{BASE_URL}/design", json=payload.model_dump())
     
     if response.status_code == 200:
          global id
          id = response.json()["speaker_id"]
          print(f"Successfully designed voice {payload.name}. ID: " + id)
     else:
          print(f"Failed to design voice. Status: {response.status_code}, Error: {response.text}")

def test_speech_generation_file():
     print("\nTesting Speech Generation (File)...")
     payload = SpeechGenerationRequest(
          text= "Hello master, for today tasks you have the following: a meeting at noon and a workout in the evening.",
          speaker_id=id,
          language="English",
          emotion=["neutral"]
     )
     # using the generate_file endpoint since we aren't streaming it in this script
     response = requests.post(f"{BASE_URL}/generate_file", json=payload.model_dump())
     
     if response.status_code == 200:
          filename = "test_speech_output_file.wav"
          with open(filename, "wb") as f:
               f.write(response.content)
          print(f"Successfully generated speech file. Saved to: {filename}")
          print("Playing generated audio file...")
          playsound(filename)
     else:
          print(f"Failed to generate speech file. Status: {response.status_code}, Error: {response.text}")

def test_speech_generation_stream():
     SAMPLE_RATE = 24000 
     CHANNELS = 1
     print("\nTesting Speech Generation (Stream)...")
     payload = SpeechGenerationRequest(
          text= "Streaming is working perfectly, master. Have a good day.",
          speaker_id=id,
          language="English",
          emotion=["neutral"]
     )
     # streaming the response
     with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16') as stream:
          print(f"Streaming and playing: '{payload.text}'")     
          with requests.post(f"{BASE_URL}/generate_stream",json=payload.model_dump(), stream=True) as r:
               r.raise_for_status()
               for chunk in r.iter_content(chunk_size=2048):
                    if chunk:
                         # Convert raw bytes back to numpy array
                         audio_data = np.frombuffer(chunk, dtype=np.int16)
                         # Send directly to your local speakers
                         stream.write(audio_data)
    
     
     #print(f"generate streaming speech. Status: {response.status_code}, Error: {response.text}")

if __name__ == "__main__":
     # Ensure the server is running before executing this
     test_voice_design()
     #test_speech_generation_file()
     test_speech_generation_stream()
