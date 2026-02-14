#!/usr/bin/env python3
"""
test_incarnation.py — Simple test harness for the Incarnation WebSocket service.

Starts a WebSocket server on port 8765, waits for the Incarnation browser client
to connect, then sends commands interactively via a simple CLI menu.

Usage:
    pip install websockets     (if not already installed)
    python test_incarnation.py

Then open the Incarnation service in a browser:
    http://localhost:5173?ws=ws://localhost:8765

Commands:
    1. Load a model (provide path relative to incarnation/public/)
    2. Load an animation file (FBX/GLB/glTF)
    3. Load a Mixamo animation (auto-retargets for VRM)
    4. Play an animation by name
    5. Stop animation
    6. Set expressions (e.g. happy=0.8, angry=0.2)
    7. Clear expressions
    8. Send raw JSON command
    9. Quit
"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("websockets package required. Install with: pip install websockets")
    sys.exit(1)

PORT = 8765
# Holds the single connected client (Incarnation browser tab)
connected_client = None


async def handler(websocket):
    """Handle an incoming WebSocket connection from the Incarnation service."""
    global connected_client
    connected_client = websocket
    remote = websocket.remote_address
    print(f"\n✅ Incarnation client connected from {remote[0]}:{remote[1]}")

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                print(f"\n📩 Received: {json.dumps(msg, indent=2)}")
            except json.JSONDecodeError:
                print(f"\n📩 Received (raw): {raw}")
    except websockets.ConnectionClosed:
        print("\n❌ Incarnation client disconnected")
    finally:
        connected_client = None


async def send_command(cmd_type: str, payload: dict | None = None):
    """Send a JSON command to the connected Incarnation client."""
    if connected_client is None:
        print("⚠️  No Incarnation client connected. Open the browser first.")
        return
    msg = {"type": cmd_type}
    if payload:
        msg["payload"] = payload
    raw = json.dumps(msg)
    print(f"📤 Sending: {raw}")
    await connected_client.send(raw)


def parse_expressions(text: str) -> dict:
    """Parse 'happy=0.8, angry=0.2' into a dict."""
    result = {}
    for pair in text.split(","):
        pair = pair.strip()
        if "=" in pair:
            name, val = pair.split("=", 1)
            try:
                result[name.strip()] = float(val.strip())
            except ValueError:
                print(f"  ⚠️  Skipping invalid value: {pair}")
    return result


async def interactive_menu():
    """Run the interactive CLI menu in a loop."""
    print("\n" + "=" * 55)
    print("  Incarnation Test Harness")
    print("  Waiting for browser client on ws://localhost:" + str(PORT))
    print("=" * 55)

    while True:
        print("\n─── Commands ───────────────────────────────")
        print("  1. Load model")
        print("  2. Load animation")
        print("  3. Load Mixamo animation (VRM retarget)")
        print("  4. Play animation")
        print("  5. Stop animation")
        print("  6. Set expressions")
        print("  7. Clear expressions")
        print("  8. Send raw JSON")
        print("  9. Quit")
        print("────────────────────────────────────────────")

        try:
            choice = await asyncio.to_thread(input, "\nChoice [1-9]: ")
        except (EOFError, KeyboardInterrupt):
            break

        choice = choice.strip()

        if choice == "1":
            url = await asyncio.to_thread(
                input,
                "Model path relative to public/ (e.g. models/vroid_test_1/model_test_1.vrm): ",
            )
            if url.strip() == "":
                #url = "models/blue_fox/blue_fox.vrm"
                url = "models/fox_maid/fox_maid.vrm"
            await send_command("load_model", {"url": url.strip()})

        elif choice == "2":
            url = await asyncio.to_thread(
                input,
                "Animation file path relative to public/ (e.g. models/anamations/Quick_FormalBow.fbx): ",
            )
            name = await asyncio.to_thread(
                input, "Custom clip name (or press Enter to keep original): "
            )
            payload = {"url": url.strip()}
            if name.strip():
                payload["name"] = name.strip()
            await send_command("load_animation", payload)

        elif choice == "3":
            url = await asyncio.to_thread(
                input,
                "Mixamo FBX path relative to public/ (e.g. models/anamations/Quick_FormalBow.fbx): ",
            )
            if url.strip() == "":
                url = "models/anamations/Quick_FormalBow.fbx"
            name = await asyncio.to_thread(
                input, "Custom clip name (or press Enter for 'vrmAnimation'): "
            )

            payload = {"url": url.strip()}
            if name.strip() == "":
                name = "bow"
            payload["name"] = name.strip()
            
            await send_command("load_mixamo_animation", payload)

        elif choice == "4":
            name = await asyncio.to_thread(input, "Animation name: ")
            loop_str = await asyncio.to_thread(
                input, "Loop? [Y/n]: "
            )
            loop = loop_str.strip().lower() != "n"
            await send_command(
                "play_animation", {"name": name.strip(), "loop": loop}
            )

        elif choice == "5":
            await send_command("stop_animation")

        elif choice == "6":
            text = await asyncio.to_thread(
                input, "Expressions (e.g. happy=0.8, angry=0.2): "
            )
            expressions = parse_expressions(text)
            if expressions:
                await send_command("set_expression", {"expressions": expressions})
            else:
                print("  No valid expressions parsed.")

        elif choice == "7":
            await send_command("clear_expressions")

        elif choice == "8":
            raw = await asyncio.to_thread(input, "JSON: ")
            try:
                msg = json.loads(raw.strip())
                cmd_type = msg.pop("type", "unknown")
                await send_command(cmd_type, msg.get("payload", msg))
            except json.JSONDecodeError:
                print("  ⚠️  Invalid JSON.")

        elif choice == "9":
            print("Goodbye!")
            break

        else:
            print("  Invalid choice.")


async def main():
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await interactive_menu()


if __name__ == "__main__":
    asyncio.run(main())
