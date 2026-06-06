import asyncio
import json
import logging
import threading
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
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


# `or` (not the dict default) so an explicitly-empty env var — set in
# docker-compose.test.yml to skip live tests — still resolves to a usable
# default URL for offline mocking via respx.
TTS_BASE = os.environ.get("TTS_URL") or "http://localhost:8009"
WHISPER_BASE = os.environ.get("WHISPER_URL") or "http://localhost:9000"


class IncarnationServer:
    def __init__(self, host="0.0.0.0", port=8765, on_message_callback=None,
                 state_provider=None, event_handler=None):
        self.host = host
        self.port = port
        self.on_message_callback = on_message_callback
        self.state_provider = state_provider
        # (name, payload) -> {"matched": bool, "skill"?: str}; the orchestrator's
        # PlayAIdes.handle_event. Called off the event loop (POST /api/event).
        self.event_handler = event_handler
        # Multi-client support (Phase 4): every connected WebSocket lives in
        # `_clients`; bindings map each socket to the persona id it's
        # currently displaying so we can route assistant_message broadcasts.
        self._clients: set = set()
        self._bindings: dict = {}   # WebSocket → persona_id
        # Captured on first WS connect so threadsafe broadcasts can dispatch
        # onto the loop where the WS protocol lives (uvicorn thread in
        # production, TestClient portal in tests).
        self._ws_loop = None
        self.message_queue: list = []

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
            # Bundled VRM models/animations referenced by load_model: the viewer
            # requests them at /models/<id>/<file>.vrm. Without this mount the
            # production build 404s every model (dev/Vite serves public/ at root).
            if os.path.exists("incarnation/dist/models"):
                self.app.mount("/models", StaticFiles(directory="incarnation/dist/models"), name="models")
            # Same root-relative-asset gap for VRMA animations (/vrma/animations/
            # *.vrma — the intro/idle clips) and the scene background (/scene/*).
            if os.path.exists("incarnation/dist/vrma"):
                self.app.mount("/vrma", StaticFiles(directory="incarnation/dist/vrma"), name="vrma")
            if os.path.exists("incarnation/dist/scene"):
                self.app.mount("/scene", StaticFiles(directory="incarnation/dist/scene"), name="scene")

            @self.app.get("/")
            async def serve_index():
                from fastapi.responses import FileResponse
                return FileResponse("incarnation/dist/index.html")
        else:
            logger.warning("incarnation/dist not found. Production build will not be served.")

        if not os.environ.get("PLAYAIDES_API_KEY"):
            logger.warning(
                "PLAYAIDES_API_KEY not set — HA trigger endpoints accept "
                "any request (dev mode). Set the env var in any non-local "
                "deployment."
            )

        self._setup_routes()

        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def _setup_routes(self):

        # ── Auth dependency ───────────────────────────────────────────────────
        def require_api_key(authorization: Optional[str] = Header(default=None)):
            expected = os.environ.get("PLAYAIDES_API_KEY")
            if not expected:
                # Dev mode: no auth configured. Logged once at startup elsewhere.
                return
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="missing bearer token")
            if authorization.removeprefix("Bearer ") != expected:
                raise HTTPException(status_code=401, detail="invalid bearer token")

        # ── HA trigger endpoints ──────────────────────────────────────────────
        @self.app.post("/api/personas/{persona_id}/activate")
        async def activate_persona(persona_id: str, _auth=Depends(require_api_key)):
            if self.on_message_callback:
                self.on_message_callback({
                    "type": "set_active_persona",
                    "payload": {"id": persona_id},
                })
            return {"ok": True, "active_persona_id": persona_id}

        @self.app.post("/api/dismiss")
        async def dismiss(_auth=Depends(require_api_key)):
            self._bindings.clear()
            self.broadcast_to_all("unload_model", {})
            logger.info("HA-driven dismiss: cleared bindings, broadcast unload_model")
            return {"ok": True}

        class EventBody(BaseModel):
            name: str
            payload: dict = {}

        @self.app.post("/api/event")
        async def post_event(body: EventBody, _auth=Depends(require_api_key)):
            """Generic inbound-event intake (spec §3.6) — anything that can POST
            (HA automation, email watcher, n8n, a cron elsewhere) wires a trigger.
            Routes to the active persona's event triggers via the orchestrator.
            Run off the event loop (asyncio.to_thread) so a blocking bash/http
            skill never stalls the WS loop; _dispatch_skill's WS sends are still
            scheduled threadsafe back onto this loop."""
            if self.event_handler is None:
                raise HTTPException(status_code=503, detail="event handling unavailable")
            return await asyncio.to_thread(self.event_handler, body.name, body.payload)

        @self.app.get("/api/state")
        async def get_state():
            active = None
            if self.state_provider:
                try:
                    active = self.state_provider().get("active_persona_id")
                except Exception as e:
                    logger.warning("state_provider failed: %s", e)
            return {
                "active_persona_id": active,
                "bound_client_count": len(self._bindings),
            }

        # ── Health ───────────────────────────────────────────────────────────
        @self.app.get("/health")
        async def health():
            return {"status": "ok"}

        # ── WebSocket ────────────────────────────────────────────────────────
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            logger.info("Incarnation client connected via WebSocket")
            self._clients.add(websocket)
            # Capture the loop the WS protocol lives on so broadcast helpers
            # (which may be called from any thread) can schedule sends here.
            self._ws_loop = asyncio.get_running_loop()

            # Drain any boot-time queued messages to this fresh client.
            while self.message_queue:
                msg_str = self.message_queue.pop(0)
                try:
                    await websocket.send_text(msg_str)
                except Exception:
                    break

            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {raw}")
                        continue

                    msg_type = msg.get("type")
                    payload = msg.get("payload", {}) or {}

                    # Bind / unbind happen at the socket level, not via the
                    # PlayAIdes callback (the callback can also see them — it
                    # uses set_active_persona to swap current_persona).
                    if msg_type == "set_active_persona":
                        pid = payload.get("id")
                        if pid:
                            self._bindings[websocket] = pid
                            logger.info(f"WS bound to persona {pid}")
                    elif msg_type == "dismiss_persona":
                        self._bindings.pop(websocket, None)
                        logger.info("WS persona binding cleared")

                    logger.info(f"Incarnation message: {msg}")
                    if self.on_message_callback:
                        self.on_message_callback(msg)
            except WebSocketDisconnect:
                logger.info("Incarnation client disconnected")
            finally:
                self._clients.discard(websocket)
                self._bindings.pop(websocket, None)

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

        # ── STT Proxy (browser → Whisper container) ──────────────────────────
        @self.app.post("/api/stt/proxy")
        async def proxy_stt(audio: UploadFile = File(...)):
            """
            Forwards an audio upload to the Whisper container and returns
            its transcription + detected language. Symmetric with
            /api/tts/proxy: the Whisper container is never directly
            reachable from the browser.
            """
            try:
                audio_bytes = await audio.read()
                async with httpx.AsyncClient() as client:
                    upstream = await client.post(
                        f"{WHISPER_BASE}/asr",
                        files={"audio_file": (audio.filename or "clip.wav",
                                              audio_bytes,
                                              audio.content_type or "audio/wav")},
                        params={"output": "json"},
                        timeout=30.0,
                    )
                if upstream.status_code != 200:
                    logger.error(f"STT upstream error: {upstream.status_code} {upstream.text!r}")
                    raise HTTPException(
                        status_code=502,
                        detail=f"STT upstream error: {upstream.status_code}",
                    )
                data = upstream.json()
                return {
                    "text": data.get("text", "").strip(),
                    "language": data.get("language", ""),
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.exception(f"STT Proxy error: {e}")
                raise HTTPException(status_code=502, detail=f"STT Proxy error: {e}")

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

    def send_command(self, cmd_type: str, payload: dict = None):
        """Legacy single-client API. Now broadcasts to ALL connected
        clients — Phase 4 broadcast-to-persona is via broadcast_to_persona.

        When no clients are connected, queues the message so it can be
        flushed to the next client that connects (preserves Phase 1–3
        boot-time behavior)."""
        if FastAPI is None:
            logger.error("FastAPI is not installed.")
            return

        msg = {"type": cmd_type}
        if payload:
            msg["payload"] = payload
        msg_str = json.dumps(msg)

        if not self._clients:
            logger.info(f"No client connected. Queuing: {cmd_type}")
            self.message_queue.append(msg_str)
            return

        for ws in list(self._clients):
            self._safe_send_text(ws, msg_str)

    def broadcast_to_persona(self, persona_id: str, cmd_type: str, payload: dict = None):
        """Send a WS frame to every connected client bound to persona_id.
        No-op if no clients match (e.g. the persona has been dismissed
        on every TV)."""
        msg = {"type": cmd_type, "payload": payload or {}}
        msg_str = json.dumps(msg)
        targets = [ws for ws, pid in list(self._bindings.items()) if pid == persona_id]
        for ws in targets:
            self._safe_send_text(ws, msg_str)

    def broadcast_to_all(self, cmd_type: str, payload: dict = None):
        """Send a WS frame to every connected client, regardless of binding."""
        msg = {"type": cmd_type, "payload": payload or {}}
        msg_str = json.dumps(msg)
        for ws in list(self._clients):
            self._safe_send_text(ws, msg_str)

    def _safe_send_text(self, websocket, msg_str: str):
        """Best-effort send; drops the client on any send failure (likely
        disconnected mid-broadcast). Schedules the send on the WS event
        loop via run_coroutine_threadsafe so this is safe to call from
        any thread."""
        loop = self._ws_loop
        if loop is None or not loop.is_running():
            logger.warning("WS event loop not running; dropping broadcast.")
            return
        try:
            asyncio.run_coroutine_threadsafe(websocket.send_text(msg_str), loop)
        except Exception as e:
            logger.warning(f"Broadcast send failed, dropping client: {e}")
            self._clients.discard(websocket)
            self._bindings.pop(websocket, None)
