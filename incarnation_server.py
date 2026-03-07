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

import persona_db


class PersonaCreate(BaseModel):
    name: str
    description: str = ""


class VoiceDesignRequest(BaseModel):
    persona_id: str
    name: str
    gender: str = "Female"
    language: str = "English"
    instruct: str
    sample_text: str


class VoiceGenerateRequest(BaseModel):
    speaker_id: str
    text: str
    language: str = "English"


TTS_BASE = "http://localhost:8008"


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

        # Init database
        persona_db.init_db()

        self.app = FastAPI(title="Incarnation Server")

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Ensure data directories exist
        os.makedirs("data/avatars", exist_ok=True)
        os.makedirs("data/animations", exist_ok=True)
        os.makedirs("data/backgrounds", exist_ok=True)
        os.makedirs("data/personas", exist_ok=True)

        self.app.mount("/data", StaticFiles(directory="data"), name="data")
        self._setup_routes()

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _setup_routes(self):

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

        # ── Persona CRUD ──────────────────────────────────────────────────────
        @self.app.get("/api/personas")
        async def list_personas():
            return persona_db.list_personas()

        @self.app.post("/api/personas", status_code=201)
        async def create_persona(body: PersonaCreate):
            try:
                return persona_db.create_persona(body.name, body.description)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get("/api/personas/{persona_id}")
        async def get_persona(persona_id: str):
            p = persona_db.get_persona(persona_id)
            if p is None:
                raise HTTPException(status_code=404, detail="Persona not found")
            return p

        @self.app.delete("/api/personas/{persona_id}", status_code=204)
        async def delete_persona(persona_id: str):
            if not persona_db.delete_persona(persona_id):
                raise HTTPException(status_code=404, detail="Persona not found")

        # ── Model upload ──────────────────────────────────────────────────────
        @self.app.post("/api/personas/{persona_id}/model")
        async def upload_persona_model(persona_id: str, file: UploadFile = File(...)):
            p = persona_db.get_persona(persona_id)
            if p is None:
                raise HTTPException(status_code=404, detail="Persona not found")

            folder = f"data/personas/{persona_id}/model"
            os.makedirs(folder, exist_ok=True)
            file_path = os.path.join(folder, file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            url = f"http://localhost:{self.port}/data/personas/{persona_id}/model/{file.filename}"
            record = persona_db.attach_model(persona_id, file.filename, file_path, url)
            return record

        # ── Animation upload ──────────────────────────────────────────────────
        @self.app.post("/api/personas/{persona_id}/animations")
        async def upload_persona_animation(persona_id: str, file: UploadFile = File(...)):
            p = persona_db.get_persona(persona_id)
            if p is None:
                raise HTTPException(status_code=404, detail="Persona not found")

            folder = f"data/personas/{persona_id}/animations"
            os.makedirs(folder, exist_ok=True)
            file_path = os.path.join(folder, file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            name = os.path.splitext(file.filename)[0]
            url = f"http://localhost:{self.port}/data/personas/{persona_id}/animations/{file.filename}"
            record = persona_db.attach_animation(persona_id, name, file.filename, file_path, url)
            return record

        @self.app.delete("/api/personas/{persona_id}/animations/{animation_id}", status_code=204)
        async def delete_persona_animation(persona_id: str, animation_id: str):
            if not persona_db.delete_animation(animation_id):
                raise HTTPException(status_code=404, detail="Animation not found")

        # ── Legacy upload endpoints (kept for backward compat) ────────────────
        @self.app.post("/api/upload/avatar")
        async def upload_avatar(file: UploadFile = File(...)):
            file_path = os.path.join("data/avatars", file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            url = f"http://localhost:{self.port}/data/avatars/{file.filename}"
            return {"filename": file.filename, "url": url}

        @self.app.post("/api/upload/animation")
        async def upload_animation(file: UploadFile = File(...)):
            file_path = os.path.join("data/animations", file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            url = f"http://localhost:{self.port}/data/animations/{file.filename}"
            name = os.path.splitext(file.filename)[0]
            return {"filename": file.filename, "url": url, "name": name}

        @self.app.post("/api/upload/background")
        async def upload_background(file: UploadFile = File(...)):
            file_path = os.path.join("data/backgrounds", file.filename)
            with open(file_path, "wb") as buf:
                shutil.copyfileobj(file.file, buf)
            url = f"http://localhost:{self.port}/data/backgrounds/{file.filename}"
            return {"filename": file.filename, "url": url}

        # ── Voice proxy ───────────────────────────────────────────────────────
        @self.app.get("/api/voice/speakers")
        async def list_speakers():
            return persona_db.list_voices()

        @self.app.post("/api/voice/design")
        async def design_voice(body: VoiceDesignRequest):
            payload = {
                "text": body.sample_text,
                "language": body.language,
                "instruct": body.instruct,
                "name": body.name,
                "gender": body.gender,
            }
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(f"{TTS_BASE}/design", json=payload)
            except httpx.ConnectError:
                raise HTTPException(status_code=503, detail="TTS voice server is not reachable (localhost:8008)")

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"TTS error: {resp.text}")

            speaker_id = resp.json().get("speaker_id")
            if not speaker_id:
                raise HTTPException(status_code=500, detail="TTS did not return a speaker_id")

            # Persist to DB only if a persona_id was provided
            voice_record = None
            if body.persona_id:
                p = persona_db.get_persona(body.persona_id)
                if p:
                    voice_record = persona_db.upsert_voice(
                        persona_id=body.persona_id,
                        speaker_id=speaker_id,
                        name=body.name,
                        gender=body.gender,
                        language=body.language,
                        instruct=body.instruct,
                    )

            return {"speaker_id": speaker_id, "voice": voice_record}

        @self.app.post("/api/voice/generate")
        async def generate_speech(body: VoiceGenerateRequest):
            payload = {
                "text": body.text,
                "speaker_id": body.speaker_id,
                "language": body.language,
            }
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(f"{TTS_BASE}/generate_file", json=payload)
            except httpx.ConnectError:
                raise HTTPException(status_code=503, detail="TTS voice server is not reachable (localhost:8008)")

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"TTS error: {resp.text}")

            audio_bytes = resp.content
            return StreamingResponse(
                iter([audio_bytes]),
                media_type="audio/wav",
                headers={"Content-Disposition": "inline; filename=speech.wav"},
            )

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
