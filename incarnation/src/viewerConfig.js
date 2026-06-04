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
 *   ?quality=high|low             // low = cap pixel ratio + drop shadows (weak GPUs)
 *   ?dpr=<number>                 // explicit render pixel ratio override (0.5–3)
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
    quality: 'high',
    pixelRatio: null,
});

// The backend (FastAPI WS + REST) listens on a fixed port; its HOST is derived
// from wherever this page was actually served. Loading the viewer from another
// device — a TV, a phone — then targets the right machine automatically, instead
// of that device's own "localhost". Frontend and backend are normally co-located;
// override per-URL with ?ws= / ?api= when they aren't.
const BACKEND_PORT = 8765;

/** Backend ws/http bases derived from the served origin (falls back to localhost off-DOM, e.g. in tests). */
function backendDefaults(loc = (typeof window !== 'undefined' ? window.location : null)) {
    const host = (loc && loc.hostname) || 'localhost';
    const secure = !!loc && loc.protocol === 'https:';
    return {
        wsUrl: `${secure ? 'wss' : 'ws'}://${host}:${BACKEND_PORT}/ws`,
        apiBase: `${secure ? 'https' : 'http'}://${host}:${BACKEND_PORT}`,
    };
}

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
    const backend = backendDefaults();
    const dpr = parseFloat(p.get('dpr'));

    const config = {
        persona:     p.get('persona') || DEFAULTS.persona,
        activation:  (p.get('activation') === 'continuous') ? 'continuous' : 'wake',
        cinematic:   parseBool(p.get('cinematic'), DEFAULTS.cinematic),
        mic:         parseBool(p.get('mic'),       DEFAULTS.mic),
        subtitles:   parseBool(p.get('subtitles'), DEFAULTS.subtitles),
        nameplate:   parseBool(p.get('nameplate'), DEFAULTS.nameplate),
        chat:        (p.get('chat') === 'open') ? 'open' : 'closed',
        quality:     (p.get('quality') === 'low') ? 'low' : DEFAULTS.quality,
        pixelRatio:  Number.isFinite(dpr) ? dpr : DEFAULTS.pixelRatio,
        wsUrl:       p.get('ws')  || backend.wsUrl,
        apiBase:     p.get('api') || backend.apiBase,
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

/**
 * Normalize an asset URL received from a backend command so it loads from
 * whatever host actually served the page. The backend builds some URLs with a
 * hardcoded http://localhost:<port> origin (see incarnation_server.py upload
 * routes); on a remote device "localhost" is that device itself, so the asset
 * 404s. This rewrites a localhost / 127.0.0.1 origin to the apiBase origin, and
 * leaves relative URLs (e.g. "models/x.vrm", served by the frontend) untouched.
 *
 * @param {string} url       URL or path from a backend command payload.
 * @param {string} apiBase   Backend base, e.g. "http://192.168.0.7:8765".
 * @returns {string}
 */
export function resolveAssetUrl(url, apiBase) {
    if (!url || typeof url !== 'string' || !apiBase) return url;
    return url.replace(/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i, apiBase.replace(/\/+$/, ''));
}
