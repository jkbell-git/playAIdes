# HA-side: Silver kiosk launch + control buttons

Home Assistant artifacts that drive the playAIdes viewer on a Fire TV. Two files:

| File | What it is | Where it goes |
|---|---|---|
| `silver_launch.yaml` | `rest_command` + `script`s + a disabled draft motion automation | HA config (a package, or split into your existing files) |
| `silver_launch_dashboard.yaml` | A Lovelace card with one button per box + Greet/Camera/Hide | Pasted into a dashboard as a Manual card |

**Proven end-to-end on 2026-06-06** on the bedroom box
(`media_player.fire_tv_192_168_0_233`): power on → force-stop+open Silk → `input tap` →
**Silver appeared and spoke unattended (audio unlocked)** — confirmed both in the backend
logs (the viewer fetched the greet's `/api/tts/proxy` 200 OK) and by ear. All five HA
entities present; the `/api/event` contract (`demo_say` / `demo_camera` / `demo_dismiss`)
returns `matched: true`.

## Launch from the host CLI (no HA dashboard needed)

`bin/silver-launch.py` replicates this exact sequence by calling the HA REST API
directly, so it works whether or not the package below is installed in HA. It
reads `HA_URL` + `HA_TOKEN` from the environment or the project `.env` (the token
is only used in the Authorization header — never printed).

```bash
bin/silver-launch.py bedroom              # also: box8 | living  (default: bedroom)
bin/silver-launch.py bedroom --wait 12 --tap 960 540
bin/silver-launch.py bedroom --url 'http://192.168.0.7:8765/?kiosk=1&cmdlog=0'
```

If a box doesn't render at 1080p the audio-unlock tap may miss — pass `--tap X Y`.
This is how the launch is driven from the dev host; the HA scripts/dashboard
below are the in-HA equivalent (and the path for motion/automation triggers).

## What you get (all manual buttons — no real-world trigger yet)

- **Launch · .0.8 / Living Rm / Bedroom** — turn on the TV (CEC) → force-stop + open Silk
  to `http://192.168.0.7:8765/?kiosk=1` → wait → ADB `input tap` to unlock audio autoplay.
- **Greet** — Silver speaks a line (audio test).
- **Camera** — live HA camera (`camera.printer_gym_camera_live_view`) in the viewer's PiP.
- **Hide** — dismiss the PiP.

The launch sequence is one parameterized core script (`silver_launch_kiosk`); the three
per-box buttons are thin wrappers that call it with a different `target`.

## Install

1. **Scripts + rest_command.** Easiest: drop `silver_launch.yaml` into
   `<config>/packages/silver_launch.yaml`. If you've never used packages, add this once
   to `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
   Not using packages? Paste the `rest_command:` and `script:` blocks into
   `configuration.yaml` (or add the scripts via the UI), and the `automation:` block into
   `automations.yaml` / the UI.
2. **Check config & reload.** Developer Tools → YAML → *Check Configuration*, then
   *Restart* (or reload Scripts + Rest Commands + Automations individually).
3. **Dashboard buttons.** Open a dashboard → Edit → **+ Add card** → search **Manual** →
   paste `silver_launch_dashboard.yaml`.

## Test (do this order)

1. **Prove the event path first** — open the viewer somewhere (Fire TV, or a laptop at
   `http://192.168.0.7:8765/?kiosk=1`) so a client is *bound*, then press **Greet**.
   You should hear Silver. (This needs no ADB — it only exercises `rest_command`.)
2. **Prove a launch** — start with **Launch · .0.8** (the proven box). Watch the TV:
   it should power on, Silk should open the viewer, and ~8 s later the synthetic tap
   should let Silver's audio play unattended.
   - Prefer Developer Tools → **Actions** → run `script.silver_launch_box8` first if you
     want to watch each step / read errors.
3. **Then the other boxes** — Living Room / Bedroom are unverified; see caveats.

## Caveats / tuning

- **Tap coordinate.** `960,540` = center of a 1080p screen (proven on `.0.8`). If a box
  renders at a different resolution the tap may miss the page — pass `tap_x` / `tap_y`
  in that box's wrapper, or in Dev Tools when running the core script.
- **Wait time.** `wait_s` defaults to 10 s. A cold Silk launch on a box that was fully
  asleep may need more; bump it if the tap lands before the page is interactive.
- **Don't gate the tap on `bound_client_count`.** `/api/state`'s counter only counts
  viewers that send `set_active_persona`; the kiosk viewer receives broadcast events as a
  plain WS client *without* binding, so the counter can read `1`/`0` even though the viewer
  is loaded and working. Use the fixed `wait_s` delay (which the scripts do).
- **Force-stop before launch.** The core script `am force-stop`s Silk first so the `VIEW`
  intent navigates fresh — without it, an already-open Silk may just resume its last tab.
- **`media_player.turn_on`** wakes the Fire TV and powers the TV via CEC. If a stick is
  truly powered off (not just screen-asleep) ADB may be unreachable until it wakes —
  the 2 s post-power delay helps; increase it if `am start` fails on a cold box.
- **`androidtv.adb_command`** comes from the **Android Debug Bridge** integration (the
  ADB one — *not* "Android TV Remote", which can't send raw `input tap` / `am start`).
- **Audio unlock uses `input tap`, never `keyevent`.** Silk only treats a tap as the
  trusted user-gesture that resumes the AudioContext.

## Going live (later)

The `silver_launch_on_motion` automation in `silver_launch.yaml` is the motion → launch
flow, shipped **disabled** (`initial_state: false`) and pointed at the garage motion
sensor (the only one today, currently reporting `unknown`). When ready: pick your box
(edit the `script.silver_launch_*` it calls), ideally swap in a better-placed motion
sensor, then enable it.
