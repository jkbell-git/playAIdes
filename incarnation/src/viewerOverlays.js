/**
 * viewerOverlays.js — the DOM rendering side of the viewer.
 *
 * Owns three independently-toggleable overlay regions described in the
 * spec §4:
 *   • Mic / state indicator   — bottom-left dot whose color tracks state
 *   • Subtitle band           — bottom-center, only visible while SPEAKING
 *   • Name plate              — top-left chip with persona name + conn dot
 *
 * Overlays are toggled at construction time from the URL config; once
 * disabled, their elements stay hidden for the session.
 *
 * The state machine is the only event source we listen to; backend WS
 * events flow through the orchestrator which decides what state the
 * machine should be in.
 */

import { State } from './viewerState.js';

const SUBTITLE_FADE_MS = 2000;   // how long the subtitle stays visible after audio ends

export class ViewerOverlays {
    /**
     * @param {object} root — DOM root containing the overlay elements
     * @param {object} config — frozen Config from viewerConfig.loadConfig()
     * @param {import('./viewerState.js').ViewerState} state
     */
    constructor(root, config, state) {
        this.root = root;
        this.config = config;
        this.state = state;

        this.elMic       = root.querySelector('#mic-indicator');
        this.elSubtitle  = root.querySelector('#subtitle-band');
        this.elSubText   = root.querySelector('#subtitle-text');
        this.elNameplate = root.querySelector('#nameplate');
        this.elPName     = root.querySelector('#nameplate-name');
        this.elConnDot   = root.querySelector('#nameplate-conn');

        // Hide overlays the user opted out of (config.cinematic forces all off).
        if (!config.mic && this.elMic)             this.elMic.hidden       = true;
        if (!config.subtitles && this.elSubtitle)  this.elSubtitle.hidden  = true;
        if (!config.nameplate && this.elNameplate) this.elNameplate.hidden = true;

        this._subtitleTimer = null;

        state.addEventListener('change', (e) => this._onStateChange(e.detail));
    }

    /** Update name + connection status in the nameplate (no-op if hidden). */
    setPersonaName(name) {
        if (this.elPName) this.elPName.textContent = name || '—';
    }

    setConnectionState(kind) {
        // kind: 'connected' | 'disconnected' | 'error'
        if (!this.elConnDot) return;
        this.elConnDot.classList.remove('connected', 'disconnected', 'error');
        this.elConnDot.classList.add(kind);
    }

    // ── State-driven rendering ──────────────────────────────────────────

    _onStateChange({ next, meta }) {
        // Mic indicator: color/animation per state. CSS owns the actual
        // styling — we just attach a class.
        if (this.elMic && !this.elMic.hidden) {
            this.elMic.className = 'mic-indicator state-' + next.toLowerCase();
        }

        if (this.elSubtitle && !this.elSubtitle.hidden) {
            this._renderSubtitle(next, meta);
        }
    }

    _renderSubtitle(next, meta) {
        const setText = (text, klass) => {
            if (this.elSubText) this.elSubText.textContent = text;
            this.elSubtitle.classList.remove('user', 'placeholder');
            if (klass) this.elSubtitle.classList.add(klass);
        };

        clearTimeout(this._subtitleTimer);

        if (next === State.LISTENING) {
            const transcript = (meta && meta.lastUtterance) || '';
            setText(transcript || 'listening…', transcript ? 'user' : 'placeholder');
            this.elSubtitle.classList.add('visible');
            return;
        }
        if (next === State.THINKING) {
            const transcript = (meta && meta.lastUtterance) || '…';
            setText(transcript, 'user');
            this.elSubtitle.classList.add('visible');
            return;
        }
        if (next === State.SPEAKING) {
            setText((meta && meta.text) || '', null);
            this.elSubtitle.classList.add('visible');
            return;
        }
        // AMBIENT / EMPTY / INTRO — fade out over the next SUBTITLE_FADE_MS.
        this._subtitleTimer = setTimeout(() => {
            this.elSubtitle.classList.remove('visible');
            this.elSubtitle.classList.remove('user', 'placeholder');
        }, SUBTITLE_FADE_MS);
    }
}
