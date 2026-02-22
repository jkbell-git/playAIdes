FROM local-qwen3-tts:latest 

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    sqlite3 \
    sox \
    libsox-fmt-all \
    libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
#COPY . .

# Expose the API port
EXPOSE 8008

# Command to run the server
#CMD ["python", "voice_server.py"]
