/**
 * viewerConfig.js — parse URL params into a frozen Config object.
 *
 * Read ONCE at viewer boot. URL changes after boot require a reload —
 * keeps the surface tiny and the state machine simpler.
 *
 * Schema (matches docs/superpowers/specs/2026-04-24-viewer-redesign-design.md §7):
 *
 *   ?persona=<id>                 // boot persona
 *   ?activation=wake|continuous   // voice activation mode (phase 2+)
 *   ?cinematic=0|1                // master overlay kill-switch
 *   ?mic=0|1                      // show mic indicator
 *   ?subtitles=0|1                // show subtitle band
 *   ?nameplate=0|1                // show persona nameplate
 *   ?chat=closed|open             // chat panel initial (phase 5+)
 *   ?ws=<url>                     // websocket URL override
 *   ?api=<url>                    // REST base URL override
 */

const DEFAULTS = Object.freeze({
    persona: null,
    activation: 'wake',
    cinematic: false,
    mic: true,
    subtitles: true,
    nameplate: false,
    chat: 'closed',
    wsUrl: 'ws://localhost:8765/ws',
    apiBase: 'http://localhost:8765',
});

/** Parse a URLSearchParams flag like "0" / "1" / "true" / "false" / undefined. */
function parseBool(value, fallback) {
    if (value === null || value === undefined) return fallback;
    const v = String(value).toLowerCase();
    if (v === '0' || v === 'false' || v === 'off') return false;
    if (v === '1' || v === 'true'  || v === 'on')  return true;
    return fallback;
}

/** Build a frozen Config from `window.location.search` (or any URLSearchParams-like). */
export function loadConfig(search = window.location.search) {
    const p = new URLSearchParams(search);

    const config = {
        persona:     p.get('persona') || DEFAULTS.persona,
        activation:  (p.get('activation') === 'continuous') ? 'continuous' : 'wake',
        cinematic:   parseBool(p.get('cinematic'), DEFAULTS.cinematic),
        mic:         parseBool(p.get('mic'),       DEFAULTS.mic),
        subtitles:   parseBool(p.get('subtitles'), DEFAULTS.subtitles),
        nameplate:   parseBool(p.get('nameplate'), DEFAULTS.nameplate),
        chat:        (p.get('chat') === 'open') ? 'open' : 'closed',
        wsUrl:       p.get('ws')  || DEFAULTS.wsUrl,
        apiBase:     p.get('api') || DEFAULTS.apiBase,
    };

    // Master kill-switch: ?cinematic=1 forces all overlays off regardless
    // of their individual flags.
    if (config.cinematic) {
        config.mic = false;
        config.subtitles = false;
        config.nameplate = false;
    }

    return Object.freeze(config);
}
