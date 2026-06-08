# Fire TV kiosk-browser options

Evaluated **2026-06-08** for the playAIdes viewer (a custom web app shown fullscreen on a
Fire TV). **Current choice: Silk** (the stock Fire TV browser). This doc records the
alternatives in case we want to switch later — "basic function works in Silk" is good
enough for now.

## Decision (2026-06-08): stay on Silk

`bin/silver-launch.py` opens the viewer in **Silk** and then sends **DPAD_DOWN key events**
(remote "scroll down") so Silk hides its URL/toolbar. Silk re-shows the bar on its ~6-hour
refresh — **acceptable**. Silk has **no true fullscreen / kiosk mode** (confirmed:
`requestFullscreen()` is not honored, and touch swipes are ignored — Fire TV is
remote-driven), but the viewer is functional, and no app install is required.

Switching to a dedicated kiosk browser is a **future** option (below) if the toolbar,
keep-awake, or remote-control story becomes a real pain.

## Options

| Browser | Install | Fullscreen / hides URL bar | Keep-awake | Remote control | Reception | Notes |
|---|---|---|---|---|---|---|
| **Silk** *(current)* | Built in | ✗ no true FS; scroll-to-hide only (URL bar returns ~every 6 h) | ✗ (we tap to wake/keep audio) | ADB via HA (`input tap` / `keyevent`) | Stock, stable | What we use; launch scrolls down to hide the bar |
| **Fully Kiosk** | ⚠ **Sideload** (Fire OS APK) | ✓ true fullscreen | ✓ | ✓ **REST API + official HA integration** | ⭐ Home-Assistant community favorite | Best fit; a few features need a one-time "Plus" license (else a watermark). Its REST API could replace our whole ADB launch dance |
| **TV Bro** | ⚠ Sideload | ✓ fullscreen | ~ | limited | Mixed — recurring fullscreen-video / custom-URL gripes | OK, not polished |
| **ClickSimply Kiosk** | ✓ **Amazon Appstore** (no sideload) | ✓ fullscreen, no bar | ✓ ("won't sleep") | — (set the URL once) | Lightly reviewed; functional | The no-sideload pick. Gripe: remote URL entry is fiddly — type it via the Fire TV phone app; it remembers the URL after |
| **Full Screen Browser** | ✓ Amazon Appstore | ✓ no menu bar | ? | — | Niche, sparse reviews | Minimal / bare-bones |

**Community consensus:** browser-based Fire TV kiosks are inherently a bit fragile (an
Amazon system update can disturb workarounds); the most-trusted option is **Fully Kiosk**,
which on Fire TV means a sideload.

## If we ever switch

- **Fully Kiosk** — strongest, and integrates best with our stack: its **REST API / HA
  integration** could replace the ADB `am start` + tap/keyevent sequence entirely
  (load the URL fullscreen + keep-awake, driven from HA or the backend). Cost: a sideload
  + a small Plus license for some features. This is the one people genuinely like.
- **ClickSimply Kiosk** — the no-sideload route: install from the Appstore, set the viewer
  URL once (via the Fire TV phone-app keyboard), done. Bare-bones but fullscreen + keep-awake.
- Either swap is a small change to `bin/silver-launch.py`: a different package name, and for
  Fully Kiosk, its REST API in place of `am start` + the ADB taps.

## Sources

- [Fully Kiosk — Home Assistant integration](https://www.home-assistant.io/integrations/fully_kiosk/)
- [Fully Kiosk on Fire = sideload APK (HA guide)](https://leonardosmarthomemakers.com/how-to-install-fully-kiosk-browser-on-fire-tablet-for-home-assistant/)
- [TV Bro — XDA thread](https://xdaforums.com/t/tv-bro-browser-for-android-based-tvs.3545295/)
- [ClickSimply Kiosk — Amazon Appstore](https://www.amazon.com/ClickSimply-Kiosk/dp/B073XWVMDT)
- [Full Screen Browser — Amazon Appstore](https://www.amazon.com/CecileApp-full-screen-browser/dp/B00NWKC620)
- [Silk has no fullscreen option (Amazon forum)](https://www.amazonforum.com/s/question/0D54P00006zStmFSAS/silk-browser-missing-full-screen-option)
- [ADB keyevent 20 = DPAD_DOWN (AFTVnews)](https://www.aftvnews.com/how-to-remotely-control-an-amazon-fire-tv-or-fire-tv-stick-via-adb/)
- [Fire TV signage/kiosk limitations](https://www.posterbooking.com/signage/digital-signage/hardware/amazon-fire-tv-stick/)
