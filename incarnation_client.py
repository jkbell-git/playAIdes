import json
import threading
import asyncio
import logging
logger = logging.getLogger(__name__)
try:
    import websockets
except ImportError:
    websockets = None

class IncarnationClient:
    def __init__(self, uri="ws://localhost:8765"):
        self.uri = uri

    def send_command(self, cmd_type: str, payload: dict = None):
        """
        Sends a command to the Incarnation WebSocket server in a background thread.
        This won't block the main application.
        """
        if websockets is None:
            logger.error("websockets package is not installed. Cannot send to Incarnation.")
            return

        msg = {"type": cmd_type}
        if payload:
            msg["payload"] = payload

        def _run_in_thread():
            async def _send():
                try:
                    async with websockets.connect(self.uri) as websocket:
                        await websocket.send(json.dumps(msg))
                except Exception as e:
                    logger.exception(f"[IncarnationClient] Failed to send {cmd_type} to {self.uri}: {e}")
            
            # Using asyncio.run to execute the coroutine in this new thread
            asyncio.run(_send())

        # Start a short-lived daemon thread to run the asyncio event loop and send the message
        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()
