# playAIdes — Hardware Inventory & Voice / Sensor Configurations

A planning reference for adding a **room microphone** (and future sensors) to playAIdes,
matched against the hardware on hand. Researched & written 2026-06-06.

> See also: the mic-constraint memo `ha/` notes and the auto-memory
> `playaides-voice-input-mic-options`. TL;DR of the constraint below.

---

## ✅ Decision (2026-06-06)

- **Pi 5 = the HA server** (Assist pipeline already running) → *not* available as a satellite.
- **Room mic = a dedicated ESP32-S3 voice satellite** (I2S mic). **Hard requirement: the
  voice path must work WITHOUT Home Assistant** → it talks **straight to playAIdes** (Config B
  below). playAIdes already runs Whisper + LLM + TTS and is self-contained, so HA is *optional*.
  The HA route (Config A1: ESPHome → Assist → `/api/event`) is kept only as an alternative front door.
- **Same board carries sensors** — esp. an **LD2410(C) mmWave** for "am I in the room"
  (stationary presence, not just motion). Temp/humidity/lux optional; all via ESPHome → HA.
- **Camera stays OFF the voice board** — PSRAM/CPU contention + poor ESP32-cam quality. Use
  mmWave for presence; use the existing HA camera (which the persona already displays) for video.
- **Keep the classic ELEGOO ESP32 ×3** for sensor-only nodes; **the touchscreens** for wall
  control panels (native port of `control.html`).
- **Far-field caveat:** a single INMP441 is OK at bedroom distance; for better room pickup use
  an XMOS board (FutureProofHomes **Satellite1**) or dual-mic (**HA Voice PE** / ReSpeaker Lite).

---

## 0. The constraint that drives everything

- **The Fire TV mic and the Samsung TV mic are platform-locked.** Amazon reserves the Fire
  TV Cube / Alexa-remote mic for Alexa (no `android.hardware.microphone`, `RECORD_AUDIO`
  force-denied); Samsung reserves its remote mic for Bixby. Neither is reachable by our app.
  → **The mic must be external hardware we control.**
- **The pipeline already exists:** `mic → STT (Whisper :9000) → LLM → TTS → Fire TV viewer`.
  The viewer (`audioCapture.js` `getUserMedia`) only gets a mic on a *normal browser*
  (laptop/phone). For the room, the **mic decouples from the screen** — the Fire TV viewer
  becomes display-only; a separate device is the "ears."
- **Two ways the ears talk to playAIdes:**
  - **Route A — via Home Assistant:** mic device → HA **Assist** pipeline (wake word + STT)
    → HA automation `POST /api/event` (or converse) to playAIdes. *Least playAIdes code.*
  - **Route B — direct:** mic device → `POST /api/stt/proxy` (already exists) → transcript
    → small new backend hop `text → converse → broadcast speak to viewer`. *No HA in the
    voice path; a bit of backend glue.*

---

## 1. Hardware inventory & best role

| Board | Brain | Net | On-device wake word? | Audio in | Best role here |
|---|---|---|---|---|---|
| **ELEGOO ESP32** (WROOM-32, *the one you linked*) | Xtensa LX6 ×2 @240 MHz, ~520 KB RAM, **no PSRAM** | WiFi/BT4.2 | ❌ (no PSRAM) | I2S (GPIO) | Streaming voice sat (server-side wake word) · sensor nodes · control panel |
| **ESP32 touchscreens** | ESP32 or **ESP32-S3** + display | WiFi/BT | ✅ *if S3* | I2S (GPIO) | Wall control panel (replaces `control.html`) + optional wake-word sat |
| **Pi Pico / Pico W** | RP2040 ×2 @133 MHz, 264 KB | WiFi *(W only)* | ❌ | I2S / PDM via PIO | Sensor node · simple I2S audio streamer |
| **Arduino UNO R4** | Renesas M4 @48 MHz, 32 KB RAM (WiFi var. has an ESP32-S3 radio) | WiFi *(WiFi var.)* | ❌ | weak | Sensor node |
| **STM32** (generic) | Cortex-M, I2S/DFSDM, good DSP | depends on part | maybe (TFLite-micro) | I2S / PDM (GPIO) | Sensor node · audio DSP front-end (custom firmware) |
| **Arduino Giga R1 WiFi** | STM32H747 M7 @480 + M4, 8 MB SDRAM | WiFi/BT | ✅ possible (TFLite-micro) | I2S / PDM / analog | Capable edge node, **custom firmware** (no ESPHome) |
| **Arduino UNO Q** | **Debian Linux** (QRB2210 quad-A53) + STM32U585, 2–4 GB, 16 GB eMMC | WiFi5/BT5 | ✅ (Linux) | USB / analog | Compact **Linux voice satellite** (Wyoming) · sensor hub via its MCU |
| **Raspberry Pi 5** | Linux, quad-A76 @2.4 GHz, up to 16 GB | add-on/USB WiFi | ✅ (Linux) | USB / I2S HAT | ⭐ **Voice hub** — far-field mic + Wyoming, or run STT/wake/playAIdes locally |
| **BeagleBone Black** | Linux, A8 @1 GHz, 512 MB (USB WiFi dongle) | USB WiFi | weak | USB | Sensor / GPIO-IO hub (modest for STT) |

---

### Processing power vs HA dependency — the key board tradeoff

*Where the wake word + STT runs decides how much board you need:*
- **No HA (Config B):** the board runs wake word **on-device** + buffers audio → needs an
  **ESP32-S3 with PSRAM**. Classic ESP32 / UNO R4 / Pi Pico are too weak — no on-device wake word.
- **With HA (Config A):** HA does wake word (openWakeWord, server-side) + STT, so the board just
  **streams audio** → this "opens back up" the cheaper/weaker boards (your classic ELEGOO ESP32s,
  etc.) as satellites. *(Exactly the point: needing HA lowers the on-device bar.)*

**Sweet spot for "more power, still cheap":** an **ESP32-S3 N16R8** (16 MB flash / 8 MB PSRAM,
~$8–15) — far more capable than a UNO/Pico, and the *minimum* for on-device wake word.
- Higher tier: **ESP32-P4** (dual RISC-V @400 MHz, more RAM — heavier on-device audio/AI).
- Linux tier: **your UNO Q**, or a ~$15 **Pi Zero 2 W**, when you want full Linux on the satellite.

**Both front doors can coexist:** build the no-HA path (S3 → `/api/voice`) as primary **and** keep
`/api/event` open — so HA-routed cheap boards can *also* feed playAIdes later. Not locked in.

---

## 2. Microphones — GPIO (I2S) vs USB (your buy decision)

**The rule of thumb:** mic on a *microcontroller* → **I2S over GPIO**; mic on a *Linux board*
→ **USB** (and for a room, a far-field USB array).

| Mic | Bus | Far-field? | Pairs with | ~Cost | Notes |
|---|---|---|---|---|---|
| **INMP441** | I2S (GPIO) | ✗ (close/mid) | ESP32/S3, Pico, STM32, Giga | ~$5 | Budget DIY standard; no AEC |
| **ICS-43434 / SPH0645** | I2S (GPIO) | ✗ | same | ~$7 | Better SNR than INMP441 |
| **ReSpeaker Lite (2-mic)** | I2S | partial | ESP32-S3 (ESPHome-ready) | ~$15 | Nicer than bare INMP441; some processing |
| **Cheap USB mic / USB sound card + electret** | USB | ✗ | Pi 5, UNO Q, BeagleBone | ~$10 | Plug-and-play (ALSA); fine for close-talk |
| **ReSpeaker USB Mic Array v2.0** | USB | ✅✅ (4-mic, XMOS AEC + beamforming, ~6 ft) | Pi 5, UNO Q, any Linux/mini-PC | ~$70–80 | ⭐ Best room mic; hardware echo-cancel = "barge-in" while audio plays |
| **ReSpeaker 2-Mics Pi HAT** | I2S (HAT) | partial | Pi (any) | ~$10 | I2S on a Pi without USB |

**Far-field matters more than it seems** — a basic mic is fine on a desk and disappointing
across a living room. For a real room assistant, the **ReSpeaker USB Mic Array** (on the Pi 5)
is the standout; INMP441-on-ESP32 is great for cheap/close or distributed nodes.

---

## 3. End-to-end configurations (the menu)

### Voice-satellite configs

- **A1 — ESP32-S3 + I2S mic, ESPHome → HA Assist → playAIdes** *(cheap, on-device wake word)*
  Buy an **ESP32-S3** (PSRAM) + INMP441/ICS-43434 (or ReSpeaker Lite). ESPHome
  `voice_assistant` + `micro_wake_word`; HA automation forwards the transcript to
  `/api/event`. *Best cheap "Hey Silver" listener. Needs an S3 — not the linked classic ESP32.*

- **A2 — ELEGOO classic ESP32 + I2S mic, ESPHome (streaming) → HA Assist** *(uses a board you have)*
  Same as A1 but wake word runs **server-side** (openWakeWord on HA) since the WROOM-32 has no
  PSRAM. Works; slightly more network/latency, less snappy. Zero new hardware beyond the mic.

- **B — ESP32-S3 + I2S mic → playAIdes directly (NO Home Assistant)** ⭐ *(the required path)*
  The ESP32-S3 replaces the browser as the "mic client." The conversation engine already lives
  in playAIdes, so the board only delivers audio:
  ```
  ESP32-S3:  I2S mic → on-device wake word (Porcupine / ESP-SR) OR push-to-talk
             → record utterance (VAD) → HTTP POST audio
                              │
  playAIdes (self-contained): POST /api/voice  (NEW, ~40–60 lines, all reuse):
             1. audio → Whisper            (reuse /api/stt/proxy logic)
             2. match_keyword_prefix()     (wake/dismiss — reuse match_keywords.py)
             3. playAIdes.chat(text)       (LLM)
             4. TTS                         (voicebox)
             5. broadcast_to_all("speak")  ───────────► Fire TV avatar speaks + lip-syncs
  ```
  **Two ways to wire it:**
  - *Zero backend changes (proof):* ESP32 does `POST /api/stt/proxy`, then opens a WS to `/ws`
    and sends `user_input` — exactly what the browser does today. Works right now.
  - *Clean (recommended):* add **`POST /api/voice`** (audio in → all 5 steps server-side). The
    ESP32 becomes a dumb audio-uploader: one HTTP call per utterance.

  **Wake word with no HA and no runtime cloud:**
  - **Picovoice Porcupine** — type "Hey Silver", trains a model in seconds, runs on-device on the
    S3 (free tier). Best for a *custom* wake word.
  - **ESP-SR / WakeNet** (Espressif, on-device, free) — but only generic built-ins ("Hi ESP");
    a custom word needs a 500+ speaker dataset.
  - **Push-to-talk** button — zero ML, ideal for v1.

  The reply plays on the **TV avatar** (broadcast), so the ESP32 needs no speaker. Fully
  HA-independent; `/api/event` stays available if you ever *want* HA in front.

- **C — Pi 5 + ReSpeaker USB Mic Array → Wyoming satellite → HA Assist → playAIdes** ⭐ *(best room result)*
  `wyoming-satellite` on the Pi (auto-discovered by HA), far-field 4-mic + AEC, HA does wake
  word + STT, automation forwards transcript to playAIdes. Reuses your Pi 5; premium audio.

- **D — Pi 5 all-in-one (local)** *(most self-contained)*
  Pi 5 runs wake word + Whisper (+ optionally playAIdes services) locally with the ReSpeaker;
  mic → local STT → playAIdes converse. No dependence on the test Whisper container or HA.

- **E — Arduino UNO Q + USB mic → Wyoming (or local STT) → playAIdes** *(compact Linux sat)*
  Its Debian side runs `wyoming-satellite` or a small STT; tidier than a Pi 5 for a dedicated
  satellite, more capable than an ESP32.

- **F — Giga R1 / STM32 + I2S mic, custom firmware → `/api/stt/proxy`** *(advanced MCU)*
  The Giga's M7 @480 MHz can do real on-device DSP/VAD (even TFLite-micro wake word). No
  ESPHome support → all custom Arduino firmware (Route B style). For when you want a powerful
  MCU node without a Linux box.

### Display / control / sensor configs

- **G — ESP32 touchscreen as a wall control panel** — a native port of `control.html`
  (Show camera / Say / Hide / launch buttons); if it's an S3, double it as a wake-word sat.

- **H — Sensor fleet (future)** — UNO R4 / Pico / STM32 / BeagleBone as sensors feeding HA via
  **ESPHome** (ESP32/RP2040) or **MQTT**/custom, then HA automations → playAIdes `/api/event`
  (e.g. presence → launch viewer; motion/temo/door → persona reacts). Linux boards (Pi5/UNO Q/
  BBB) can host GPIO sensors directly too.

---

## 4. Recommendations

| Goal | Pick |
|---|---|
| Validate the whole loop **today**, $0 | Laptop/phone browser at `:8765` (mic already works there) |
| **Best room mic** (recommended) | **Config C** — Pi 5 + **ReSpeaker USB Mic Array v2.0** + Wyoming. Reuses your Pi 5. |
| **Cheapest "Hey Silver" listener** | **Config A1** — buy 1–2 **ESP32-S3** + INMP441; ESPHome. |
| Use the **boards you already have**, no buying except a mic | **A2** (ELEGOO ESP32 + INMP441, ESPHome streaming) or **E** (UNO Q + USB mic) |
| Keep HA out of the voice path | **B** (ESP32-S3 → `/api/stt/proxy`) or **D** (Pi 5 local) |
| Future sensors | **H** — ESPHome/MQTT nodes → HA → playAIdes events |

**Suggested first step:** Config **C** with the Pi 5 you already own. The only thing to buy is
the mic — and for a room, buy the **ReSpeaker USB Mic Array v2.0** (USB, far-field). Start with a
$10 USB mic if you just want to prove the chain. Keep the ELEGOO ESP32 3-pack for sensor nodes
(Config H) and a wall control panel — they're not wasted, just not the wake-word listener.

## 5. Shopping shortlist
- **Room mic (USB, far-field):** ReSpeaker USB Mic Array v2.0 — pairs with Pi 5 / UNO Q. *(buy this for Config C/E)*
- **Cheap I2S mic (GPIO):** INMP441 (or ICS-43434) — pairs with ESP32-S3 / Pico / Giga / STM32.
- **If you want on-device wake word cheaply:** one ESP32-**S3** devkit *with PSRAM* (the linked ELEGOO is classic ESP32 — fine for A2/sensors, not on-device wake word).
