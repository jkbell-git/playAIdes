import asyncio
import json
import logging
import threading

logger = logging.getLogger(__name__)

try:
    import websockets
except ImportError:
    websockets = None

class IncarnationServer:
    def __init__(self, host="0.0.0.0", port=8765, on_message_callback=None):
        self.host = host
        self.port = port
        self.on_message_callback = on_message_callback
        self.connected_client = None
        self.loop = asyncio.new_event_loop()
        self.message_queue = [] # Store messages sent before connection
        
        if websockets is None:
            logger.error("websockets package is not installed. Cannot start Incarnation Server.")
            return

        # Start the asyncio event loop in a daemon thread
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        
        async def run_server():
            async with websockets.serve(self._handler, self.host, self.port):
                logger.info(f"Incarnation WebSocket Server listening on ws://{self.host}:{self.port}")
                await asyncio.Future()  # run forever

        try:
            self.loop.run_until_complete(run_server())
        except Exception as e:
            logger.error(f"IncarnationServer failed to start: {e}")

    async def _handler(self, websocket):
        logger.info("Incarnation client connected")
        self.connected_client = websocket
        
        # Flush queue
        while self.message_queue:
            msg = self.message_queue.pop(0)
            await self._send_to_client(msg)
            
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                    if msg.get("type") == "status":
                        logger.info(f"Incarnation Status: {msg}")
                    else:
                        logger.info(f"Incarnation message: {msg}")
                    if self.on_message_callback:
                        self.on_message_callback(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Incarnation invalid JSON: {raw}")
        except websockets.ConnectionClosed:
            logger.info("Incarnation client disconnected")
        finally:
            if self.connected_client == websocket:
                self.connected_client = None

    async def _send_to_client(self, msg_str):
        if self.connected_client:
            try:
                await self.connected_client.send(msg_str)
            except Exception as e:
                logger.exception(f"Failed to send message: {e}")

    def send_command(self, cmd_type: str, payload: dict = None):
        if websockets is None:
            logger.error("websockets package is not installed.")
            return

        msg = {"type": cmd_type}
        if payload:
            msg["payload"] = payload
        
        msg_str = json.dumps(msg)
        
        if self.connected_client is None:
            logger.info(f"No client connected. Queuing command: {cmd_type}")
            self.message_queue.append(msg_str)
        else:
            # Schedule the coroutine in the running loop
            asyncio.run_coroutine_threadsafe(self._send_to_client(msg_str), self.loop)
