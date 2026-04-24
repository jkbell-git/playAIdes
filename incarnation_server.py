import asyncio
import json
import logging
import threading
import os
import shutil

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import StreamingResponse
    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import httpx
except ImportError:
    FastAPI = None

import os
import shutil


class PersonaCreate(BaseModel):
    name: str
    description: str = ""


TTS_BASE = os.environ.get("TTS_URL", "http://localhost:8009")


class IncarnationServer:
    def __init__(self, host="0.0.0.0", port=8765, on_message_callback=None):
        self.host = host
        self.port = port
        self.on_message_callback = on_message_callback
        self.connected_client = None
        self.message_queue = []

        if FastAPI is None:
            logger.error("FastAPI is not installed. Cannot start Incarnation Server.")
            return

        self.app = FastAPI(title="Incarnation Server")

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        os.makedirs("personas", exist_ok=True)
        os.makedirs("data", exist_ok=True)
        os.makedirs("incarnation/public/outputs", exist_ok=True)
        os.makedirs("incarnation/public/vrma/animations", exist_ok=True)

        self.app.mount("/data", StaticFiles(directory="data"), name="data")
        self.app.mount("/personas", StaticFiles(directory="personas"), name="personas")
        self.app.mount("/outputs", StaticFiles(directory="incarnation/public/outputs"), name="outputs")
        self.app.mount("/default_animations", StaticFiles(directory="incarnation/public/vrma/animations"), name="default_animations")
        
        # Serve Vite production build if it exists
        if os.path.exists("incarnation/dist"):
            logger.info("Serving incarnation/dist production build")
            self.app.mount("/assets", StaticFiles(directory="incarnation/dist/assets"), name="assets")
            
            @self.app.get("/")
            async def serve_index():
                from fastapi.responses import FileResponse
                return FileResponse("incarnation/dist/index.html")
        else:
            logger.warning("incarnation/dist not found. Production build will not be served.")

        self._setup_routes()

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _setup_routes(self):

        # ── Health ───────────────────────────────────────────────────────────
        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

        # ── WebSocket ────────────────────────────────────────────────────────
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            logger.info("Incarnation client connected via WebSocket")
            self.connected_client = websocket

            while self.message_queue:
                msg = self.message_queue.pop(0)
                await self._send_to_client(msg)

            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                        logger.info(f"Incarnation message: {msg}")
                        if self.on_message_callback:
                            self.on_message_callback(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {raw}")
            except WebSocketDisconnect:
                logger.info("Incarnation client disconnected")
            finally:
                if self.connected_client == websocket:
                    self.connected_client = None

        # ── Fetch Default Animations ──────────────────────────────────────────
        @self.app.get("/api/default_animations")
        async def list_default_animations():
            folder = "incarnation/public/vrma/animations"
            os.makedirs(folder, exist_ok=True)
            files = []
            for f in os.listdir(folder):
                if f.endswith(".vrma"):
                    files.append({
                        "name": os.path.splitext(f)[0],
                        "url": f"http://localhost:{self.port}/default_animations/{f}"
                    })
            return {"animations": files}

        # ── Model upload ──────────────────────────────────────────────────────
        @self.app.post("/api/personas/{persona_id}/model")
        async def upload_persona_model(persona_id: str, file: UploadFile = File(...)):
            folder = f"personas/{persona_id}/avatar"
            os.makedirs(folder, exist_ok=True)
            file_path = os.path.join(folder, file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            
            url = f"http://localhost:{self.port}/personas/{persona_id}/avatar/{file.filename}"
            
            if self.on_message_callback:
                self.on_message_callback({
                    "type": "model_uploaded",
                    "payload": {
                        "persona_id": persona_id,
                        "url": url
                    }
                })
            return {"url": url, "filename": file.filename}

        # ── Animation upload ──────────────────────────────────────────────────
        @self.app.post("/api/personas/{persona_id}/animations")
        async def upload_persona_animation(persona_id: str, file: UploadFile = File(...)):
            folder = f"personas/{persona_id}/avatar/animations"
            os.makedirs(folder, exist_ok=True)
            file_path = os.path.join(folder, file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            name = os.path.splitext(file.filename)[0]
            url = f"http://localhost:{self.port}/personas/{persona_id}/avatar/animations/{file.filename}"
            
            if self.on_message_callback:
                self.on_message_callback({
                    "type": "animation_uploaded",
                    "payload": {
                        "persona_id": persona_id,
                        "url": url,
                        "name": name
                    }
                })
            return {"url": url, "name": name, "filename": file.filename}

        # ── Ref audio proxy (voice server → frontend) ────────────────────────
        @self.app.get("/api/speakers/{speaker_id}/ref_audio")
        async def proxy_ref_audio(speaker_id: str):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{TTS_BASE}/speakers/{speaker_id}/ref_audio", timeout=30.0)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                return StreamingResponse(
                    iter([resp.content]),
                    media_type="audio/wav",
                    headers={"Content-Disposition": f"inline; filename={speaker_id}_ref.wav"}
                )
            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"Voice server error: {e}")

        # ── TTS Stream Proxy ──────────────────────────────────────────────────
        @self.app.get("/api/tts/proxy")
        async def proxy_tts_stream(text: str, speaker_id: str, language: str = "English"):
            """
            Proxies a TTS generation request from GET (browser) to POST (voice server).
            Wraps the raw PCM L16 stream in a WAV header so the browser can play it.
            """
            try:
                payload = {
                    "text": text,
                    "speaker_id": speaker_id,
                    "language": language
                }

                async def pcm_to_wav_stream():
                    # WAV Header for L16 PCM 24000Hz Mono
                    # Using 0xFFFFFFFF for streaming sizes (unspecified length)
                    
                    sample_rate = 24000
                    bits_per_sample = 16
                    channels = 1
                    
                    header = bytearray(b"RIFF")
                    header.extend([0xFF, 0xFF, 0xFF, 0xFF]) # ChunkSize (unknown)
                    header.extend(b"WAVEfmt ")
                    header.extend([16, 0, 0, 0])          # Subchunk1Size
                    header.extend([1, 0])                 # AudioFormat (PCM)
                    header.extend([channels, 0])          # NumChannels
                    header.extend(sample_rate.to_bytes(4, 'little'))
                    byte_rate = sample_rate * channels * bits_per_sample // 8
                    header.extend(byte_rate.to_bytes(4, 'little'))
                    block_align = channels * bits_per_sample // 8
                    header.extend(block_align.to_bytes(2, 'little'))
                    header.extend(bits_per_sample.to_bytes(2, 'little'))
                    header.extend(b"data")
                    header.extend([0xFF, 0xFF, 0xFF, 0xFF]) # Subchunk2Size (unknown)
                    
                    yield bytes(header)

                    async with httpx.AsyncClient() as client:
                        async with client.stream("POST", f"{TTS_BASE}/generate_stream", json=payload, timeout=60.0) as resp:
                            if resp.status_code != 200:
                                logger.error(f"TTS server error: {resp.status_code}")
                                return
                            async for chunk in resp.aiter_bytes():
                                yield chunk

                return StreamingResponse(
                    pcm_to_wav_stream(),
                    media_type="audio/wav",
                    headers={
                        "Accept-Ranges": "none",
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive"
                    }
                )
            except Exception as e:
                logger.exception(f"TTS Proxy error: {e}")
                raise HTTPException(status_code=502, detail=f"TTS Proxy error: {e}")

    # ── Server lifecycle ──────────────────────────────────────────────────────
    def _run_server(self):
        config = uvicorn.Config(app=self.app, host=self.host, port=self.port, log_level="info")
        server = uvicorn.Server(config)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            loop.run_until_complete(server.serve())
        except Exception as e:
            logger.error(f"IncarnationServer failed to start: {e}")

    async def _send_to_client(self, msg_str):
        if self.connected_client:
            try:
                await self.connected_client.send_text(msg_str)
            except Exception as e:
                logger.exception(f"Failed to send message: {e}")

    def send_command(self, cmd_type: str, payload: dict = None):
        if FastAPI is None:
            logger.error("FastAPI is not installed.")
            return

        msg = {"type": cmd_type}
        if payload:
            msg["payload"] = payload
        msg_str = json.dumps(msg)

        if self.connected_client is None:
            logger.info(f"No client connected. Queuing: {cmd_type}")
            self.message_queue.append(msg_str)
        else:
            if hasattr(self, "loop") and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(self._send_to_client(msg_str), self.loop)
            else:
                logger.warning("Event loop not running yet. Queuing message.")
                self.message_queue.append(msg_str)
