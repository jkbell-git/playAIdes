#!/usr/bin/env python3
"""
silver-launch — bring the playAIdes (Silver) kiosk viewer up on a Fire TV.

Replicates the proven ha/silver_launch.yaml sequence by calling the Home
Assistant REST API directly, so it works whether or not the HA scripts/package
are installed:

    1. media_player.turn_on      CEC power-on + wake the Fire TV
    2. androidtv.adb_command     am force-stop com.amazon.cloud9   (Silk)
    3. androidtv.adb_command     am start … VIEW the kiosk URL in Silk
    4. wait for Silk + the page to load
    5. androidtv.adb_command     input tap X Y   (the trusted gesture that
                                 unlocks audio autoplay — keyevent does NOT work)

Credentials: HA_URL + HA_TOKEN are read from the environment; if either is
unset they're loaded from the project .env. The token is used only in the
Authorization header and is NEVER printed.

Usage:
    bin/silver-launch.py [bedroom|box8|living]          # default: bedroom
    bin/silver-launch.py bedroom --wait 12 --tap 960 540
    bin/silver-launch.py bedroom --url 'http://192.168.0.7:8765/?kiosk=1'
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Fire TV media_player entities (the Android Debug Bridge integration targets
# the same entity for adb_command). See ha/silver_launch.yaml.
BOXES = {
    "bedroom": "media_player.fire_tv_192_168_0_233",
    "box8":    "media_player.fire_tv_192_168_0_8",
    "living":  "media_player.fire_tv_192_168_0_234",
}
DEFAULT_URL = "http://192.168.0.7:8765/?kiosk=1&nameplate=1"
SILK = "com.amazon.cloud9"  # Amazon Silk browser package


def _load_env_file(path):
    """Parse KEY=VALUE lines from a .env file. Values are kept in-process only."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def _creds():
    url = os.environ.get("HA_URL")
    tok = os.environ.get("HA_TOKEN")
    if not url or not tok:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
        env = _load_env_file(env_path)
        url = url or env.get("HA_URL")
        tok = tok or env.get("HA_TOKEN")
    if not url or not tok:
        sys.exit("HA_URL / HA_TOKEN not found in the environment or .env")
    return url.rstrip("/"), tok


def _call(base, token, service, data):
    """POST to HA /api/services/<domain>/<service>; return a short status string."""
    req = urllib.request.Request(
        f"{base}/api/services/{service}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return f"OK {r.status}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}"
    except Exception as e:  # noqa: BLE001 — surface any transport error compactly
        return f"ERR {e}"


def main():
    ap = argparse.ArgumentParser(description="Launch the Silver kiosk viewer on a Fire TV via Home Assistant.")
    ap.add_argument("box", nargs="?", default="bedroom", choices=list(BOXES),
                    help="which Fire TV (default: bedroom)")
    ap.add_argument("--url", default=os.environ.get("VIEWER_URL", DEFAULT_URL),
                    help="viewer URL to open")
    ap.add_argument("--tap", nargs=2, type=int, default=[960, 540], metavar=("X", "Y"),
                    help="audio-unlock tap coords (default 960 540 = 1080p centre)")
    ap.add_argument("--menu-presses", type=int, default=2,
                    help="KEYCODE_MENU (82) presses to hide Silk's address/toolbar (0 = skip)")
    ap.add_argument("--wait", type=int, default=10,
                    help="seconds to wait for Silk + the page before the tap")
    a = ap.parse_args()

    base, token = _creds()
    entity = BOXES[a.box]

    def adb(cmd):
        return _call(base, token, "androidtv/adb_command", {"entity_id": entity, "command": cmd})

    print(f"Launching Silver on {a.box} ({entity}) → {a.url}")
    print("  1/6 power on (CEC)        :", _call(base, token, "media_player/turn_on", {"entity_id": entity}))
    time.sleep(2)
    print("  2/6 force-stop Silk       :", adb(f"am force-stop {SILK}"))
    time.sleep(1)
    print("  3/6 open Silk → viewer    :", adb(f'am start -a android.intent.action.VIEW -d "{a.url}" {SILK}'))
    print(f"  4/6 wait {a.wait}s for load …")
    time.sleep(a.wait)
    print(f"  5/6 tap {a.tap[0]},{a.tap[1]} (audio)  :", adb(f"input tap {a.tap[0]} {a.tap[1]}"))
    # Silk keeps its URL/toolbar visible. A *touch* swipe is ignored (Fire TV is
    # remote-driven) and DPAD_DOWN (keycode 20) scrolling did NOT hide it. Pressing the
    # remote's Menu / hamburger button DOES hide the bar (~2 presses by hand) — replicate
    # that with KEYCODE_MENU (keycode 82).
    if a.menu_presses > 0:
        time.sleep(1)
        for _ in range(a.menu_presses):
            adb("input keyevent 82")   # KEYCODE_MENU — toggles Silk's address/toolbar away
            time.sleep(0.6)
        print(f"  6/6 MENU x{a.menu_presses} (hide bar)   : sent")
    else:
        print("  6/6 hide toolbar          : skipped (--menu-presses 0)")
    print(f"done — Silver should be on the {a.box} TV.")


if __name__ == "__main__":
    main()
