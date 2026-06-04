import { describe, it, expect } from 'vitest';
import { loadConfig } from './viewerConfig.js';

describe('loadConfig — defaults', () => {
    it('returns documented defaults when search string is empty', () => {
        const cfg = loadConfig('');
        expect(cfg).toEqual({
            persona: null,
            activation: 'wake',
            cinematic: false,
            kiosk: false,
            mic: true,
            subtitles: true,
            nameplate: false,
            chat: 'closed',
            quality: 'high',
            pixelRatio: null,
            wsUrl: 'ws://localhost:8765/ws',
            apiBase: 'http://localhost:8765',
        });
    });
});

describe('loadConfig — cinematic master kill-switch', () => {
    it('?cinematic=1 forces mic/subtitles/nameplate to false even when individually set to 1', () => {
        const cfg = loadConfig('?cinematic=1&mic=1&subtitles=1&nameplate=1');
        expect(cfg.cinematic).toBe(true);
        expect(cfg.mic).toBe(false);
        expect(cfg.subtitles).toBe(false);
        expect(cfg.nameplate).toBe(false);
    });

    it('?cinematic=0 leaves individual overlay flags untouched', () => {
        const cfg = loadConfig('?cinematic=0&mic=1&subtitles=0&nameplate=1');
        expect(cfg.cinematic).toBe(false);
        expect(cfg.mic).toBe(true);
        expect(cfg.subtitles).toBe(false);
        expect(cfg.nameplate).toBe(true);
    });
});

describe('loadConfig — kiosk mode', () => {
    it('?kiosk=1 enables kiosk and defaults overlays off', () => {
        const cfg = loadConfig('?kiosk=1');
        expect(cfg.kiosk).toBe(true);
        expect(cfg.mic).toBe(false);
        expect(cfg.subtitles).toBe(false);
        expect(cfg.nameplate).toBe(false);
    });

    it('kiosk overlay defaults stay individually re-enableable (soft, not forced)', () => {
        const cfg = loadConfig('?kiosk=1&subtitles=1');
        expect(cfg.kiosk).toBe(true);
        expect(cfg.subtitles).toBe(true);   // explicit override wins
        expect(cfg.mic).toBe(false);        // others still default off
    });

    it('no kiosk leaves overlay defaults at their normal values', () => {
        const cfg = loadConfig('');
        expect(cfg.kiosk).toBe(false);
        expect(cfg.mic).toBe(true);
        expect(cfg.subtitles).toBe(true);
        expect(cfg.nameplate).toBe(false);
    });

    it('kiosk does not touch the cinematic flag', () => {
        expect(loadConfig('?kiosk=1').cinematic).toBe(false);
    });
});

describe('loadConfig — activation', () => {
    it('?activation=continuous parses to "continuous"', () => {
        expect(loadConfig('?activation=continuous').activation).toBe('continuous');
    });

    it('?activation=wake parses to "wake"', () => {
        expect(loadConfig('?activation=wake').activation).toBe('wake');
    });

    it('?activation=foo falls back to "wake"', () => {
        expect(loadConfig('?activation=foo').activation).toBe('wake');
    });

    it('missing activation falls back to "wake"', () => {
        expect(loadConfig('').activation).toBe('wake');
    });
});

describe('loadConfig — boolean parsing', () => {
    it('parses "1", "true", "on" as true', () => {
        expect(loadConfig('?nameplate=1').nameplate).toBe(true);
        expect(loadConfig('?nameplate=true').nameplate).toBe(true);
        expect(loadConfig('?nameplate=on').nameplate).toBe(true);
    });

    it('parses "0", "false", "off" as false', () => {
        expect(loadConfig('?mic=0').mic).toBe(false);
        expect(loadConfig('?mic=false').mic).toBe(false);
        expect(loadConfig('?mic=off').mic).toBe(false);
    });

    it('unrecognized value falls back to the default', () => {
        // mic default is true
        expect(loadConfig('?mic=xyz').mic).toBe(true);
        // nameplate default is false
        expect(loadConfig('?nameplate=xyz').nameplate).toBe(false);
    });

    it('missing flag uses the default', () => {
        expect(loadConfig('').mic).toBe(true);
        expect(loadConfig('').subtitles).toBe(true);
        expect(loadConfig('').nameplate).toBe(false);
        expect(loadConfig('').cinematic).toBe(false);
    });
});

describe('loadConfig — ws/api overrides', () => {
    it('?ws= overrides wsUrl', () => {
        const cfg = loadConfig('?ws=ws://example.com:9000/socket');
        expect(cfg.wsUrl).toBe('ws://example.com:9000/socket');
    });

    it('?api= overrides apiBase', () => {
        const cfg = loadConfig('?api=https://api.example.com');
        expect(cfg.apiBase).toBe('https://api.example.com');
    });
});

describe('loadConfig — chat', () => {
    it('?chat=open parses to "open"', () => {
        expect(loadConfig('?chat=open').chat).toBe('open');
    });

    it('?chat=closed parses to "closed"', () => {
        expect(loadConfig('?chat=closed').chat).toBe('closed');
    });

    it('?chat=foo falls back to "closed"', () => {
        expect(loadConfig('?chat=foo').chat).toBe('closed');
    });
});

describe('loadConfig — persona', () => {
    it('?persona=silver parses to "silver"', () => {
        expect(loadConfig('?persona=silver').persona).toBe('silver');
    });

    it('missing persona is null', () => {
        expect(loadConfig('').persona).toBe(null);
    });
});

describe('loadConfig — frozen result', () => {
    it('returned config is frozen', () => {
        const cfg = loadConfig('');
        expect(Object.isFrozen(cfg)).toBe(true);
    });

    it('mutating a property does not change the value', () => {
        const cfg = loadConfig('?mic=1');
        // In strict mode (ES modules) this throws; wrap to cover both strict and sloppy envs.
        try {
            cfg.mic = false;
        } catch (_) {
            // expected in strict mode
        }
        expect(cfg.mic).toBe(true);
    });
});
