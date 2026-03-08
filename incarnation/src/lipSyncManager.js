/**
 * LipSyncManager — drives VRM viseme morph targets from audio in real-time.
 *
 * Uses the Web Audio API AnalyserNode to extract amplitude data each frame,
 * then maps that amplitude to mouth-shape (viseme) morph targets.
 *
 * Two source modes:
 *   1. Audio element — attach to an existing <audio> element (e.g. PersonaCreator)
 *   2. Audio URL     — fetch + decode audio, play it silently (no speaker output)
 *                      for analysis only (PlayAIdes is already playing the audio)
 */
export class LipSyncManager {
    /**
     * @param {import('./visemeManager.js').VisemeManager} visemeManager
     */
    constructor(visemeManager) {
        /** @type {import('./visemeManager.js').VisemeManager} */
        this.visemeManager = visemeManager;

        /** @type {AudioContext|null} */
        this._ctx = null;

        /** @type {AnalyserNode|null} */
        this._analyser = null;

        /** @type {Uint8Array|null} */
        this._freqData = null;

        /** @type {MediaElementAudioSourceNode|null} */
        this._elementSource = null;

        /** @type {AudioBufferSourceNode|null} */
        this._bufferSource = null;

        /** @type {boolean} */
        this._active = false;

        /** @type {HTMLAudioElement|null} */
        this._boundAudioEl = null;

        /**
         * Smoothed volume value (0–1) to avoid jittery mouth movement.
         * @type {number}
         */
        this._smoothVolume = 0;

        /**
         * Smoothing factor — higher = smoother but slower to respond.
         * @type {number}
         */
        this.smoothing = 0.4;

        /**
         * Volume threshold below which the mouth stays closed.
         * @type {number}
         */
        this.threshold = 0.01;
    }

    // ── Public API ──────────────────────────────────────────────────────────

    /**
     * Start lip-sync from an HTML <audio> element.
     * The audio continues to play through speakers as normal.
     * @param {HTMLAudioElement} audioEl
     */
    startFromAudioElement(audioEl) {
        this.stop();

        this._ctx = new (window.AudioContext || window.webkitAudioContext)();
        this._analyser = this._ctx.createAnalyser();
        this._analyser.fftSize = 256;
        this._freqData = new Uint8Array(this._analyser.frequencyBinCount);

        // Connect: audioElement → analyser → destination (speakers)
        this._elementSource = this._ctx.createMediaElementSource(audioEl);
        this._elementSource.connect(this._analyser);
        this._analyser.connect(this._ctx.destination);

        this._boundAudioEl = audioEl;
        this._active = true;

        // Auto-stop when audio ends
        audioEl.addEventListener('ended', this._onAudioEnded);
        audioEl.addEventListener('pause', this._onAudioEnded);

        console.log('[LipSync] Started from audio element');
    }

    /**
     * Start lip-sync from an audio URL.
     * The audio is fetched, decoded, and analyzed silently —
     * it does NOT play through speakers (PlayAIdes handles that).
     * @param {string} url
     */
    async startFromUrl(url) {
        this.stop();

        this._ctx = new (window.AudioContext || window.webkitAudioContext)();
        this._analyser = this._ctx.createAnalyser();
        this._analyser.fftSize = 256;
        this._freqData = new Uint8Array(this._analyser.frequencyBinCount);

        try {
            const response = await fetch(url);
            const arrayBuffer = await response.arrayBuffer();
            const audioBuffer = await this._ctx.decodeAudioData(arrayBuffer);

            this._bufferSource = this._ctx.createBufferSource();
            this._bufferSource.buffer = audioBuffer;

            // Connect: source → analyser only (no destination = silent)
            this._bufferSource.connect(this._analyser);
            // We do NOT connect to ctx.destination so no audio comes out of speakers

            this._bufferSource.onended = () => {
                console.log('[LipSync] Audio buffer finished');
                this._active = false;
                this.visemeManager.clearVisemes();
            };

            this._bufferSource.start(0);
            this._active = true;

            console.log('[LipSync] Started from URL (silent analysis):', url);
        } catch (err) {
            console.error('[LipSync] Failed to load audio from URL:', err);
            this.stop();
        }
    }

    /**
     * Stop lip-sync and clean up all audio resources.
     */
    stop() {
        this._active = false;

        if (this._boundAudioEl) {
            this._boundAudioEl.removeEventListener('ended', this._onAudioEnded);
            this._boundAudioEl.removeEventListener('pause', this._onAudioEnded);
            this._boundAudioEl = null;
        }

        if (this._bufferSource) {
            try { this._bufferSource.stop(); } catch (_) { /* already stopped */ }
            this._bufferSource.disconnect();
            this._bufferSource = null;
        }

        if (this._elementSource) {
            this._elementSource.disconnect();
            this._elementSource = null;
        }

        if (this._analyser) {
            this._analyser.disconnect();
            this._analyser = null;
        }

        if (this._ctx) {
            this._ctx.close().catch(() => {});
            this._ctx = null;
        }

        this._freqData = null;
        this._smoothVolume = 0;

        // Reset mouth to closed
        if (this.visemeManager) {
            this.visemeManager.clearVisemes();
        }

        console.log('[LipSync] Stopped');
    }

    /** @returns {boolean} Whether lip-sync is actively analyzing audio. */
    get isActive() {
        return this._active;
    }

    /**
     * Call every frame from the render loop.
     * Reads current audio amplitude and drives viseme morph targets.
     */
    update() {
        if (!this._active || !this._analyser || !this._freqData) return;

        // Get frequency data
        this._analyser.getByteFrequencyData(this._freqData);

        // Compute average volume (0–1)
        let sum = 0;
        for (let i = 0; i < this._freqData.length; i++) {
            sum += this._freqData[i];
        }
        const rawVolume = sum / (this._freqData.length * 255);

        // Smooth the volume to reduce jitter
        this._smoothVolume += (rawVolume - this._smoothVolume) * (1 - this.smoothing);

        // Apply visemes based on volume
        this._applyVisemes(this._smoothVolume);
    }

    // ── Private ─────────────────────────────────────────────────────────────

    /**
     * Map a normalized volume (0–1) to viseme morph-target weights.
     * @param {number} volume  0.0 (silence) to 1.0 (max)
     */
    _applyVisemes(volume) {
        // Clear all visemes first
        this.visemeManager.clearVisemes();

        if (volume < this.threshold) {
            // Silence — mouth closed
            this.visemeManager.setViseme('viseme_sil', 1);
            return;
        }

        // Normalize volume above threshold into 0–1 range
        const v = Math.min(1, (volume - this.threshold) / (1 - this.threshold));

        // Use time-based variation to avoid robotic repetition
        const t = performance.now() * 0.003;
        const variation = Math.sin(t) * 0.15 + Math.sin(t * 1.7) * 0.1;

        if (v < 0.3) {
            // Low volume — small mouth opening
            const w = v / 0.3;
            this.visemeManager.setViseme('viseme_PP', Math.max(0, (1 - w) * 0.5 + variation));
            this.visemeManager.setViseme('viseme_E', Math.max(0, w * 0.6 + variation * 0.5));
        } else if (v < 0.6) {
            // Medium volume — medium mouth opening
            const w = (v - 0.3) / 0.3;
            this.visemeManager.setViseme('viseme_E', Math.max(0, (1 - w) * 0.7 + variation * 0.3));
            this.visemeManager.setViseme('viseme_aa', Math.max(0, w * 0.7 + variation * 0.3));
            this.visemeManager.setViseme('viseme_I', Math.max(0, 0.3 + variation * 0.5));
        } else {
            // High volume — wide open mouth
            const w = (v - 0.6) / 0.4;
            this.visemeManager.setViseme('viseme_aa', Math.max(0, Math.min(1, 0.7 + w * 0.3 + variation * 0.2)));
            this.visemeManager.setViseme('viseme_O', Math.max(0, Math.min(1, w * 0.5 + variation * 0.3)));
        }
    }

    /** @private */
    _onAudioEnded = () => {
        console.log('[LipSync] Audio element ended/paused');
        this._active = false;
        if (this.visemeManager) {
            this.visemeManager.clearVisemes();
        }
    };
}
