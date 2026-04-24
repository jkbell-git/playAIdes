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
        this._initContext();

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

        /** @type {WeakMap<HTMLAudioElement, MediaElementAudioSourceNode>} */
        this._elementSourcesMap = new WeakMap();
    }

    /**
     * Explicitly resume the AudioContext.
     * MUST be called from a user gesture (e.g. click) to unlock audio in browsers.
     */
    async resume() {
        await this._ensureContextResumed();
    }

    _initContext() {
        if (!this._ctx) {
            this._ctx = new (window.AudioContext || window.webkitAudioContext)();
            console.log('[LipSync] AudioContext initialized. State:', this._ctx.state);
        }
    }

    async _ensureContextResumed() {
        this._initContext();
        if (this._ctx.state === 'suspended') {
            console.log('[LipSync] Resuming AudioContext...');
            await this._ctx.resume();
            console.log('[LipSync] AudioContext resumed. State:', this._ctx.state);
        }
    }

    // ── Public API ──────────────────────────────────────────────────────────

    async startFromAudioElement(audioEl) {
        this.stop();
        await this._ensureContextResumed();

        this._analyser = this._ctx.createAnalyser();
        this._analyser.fftSize = 256;
        this._freqData = new Uint8Array(this._analyser.frequencyBinCount);

        // Connect: audioElement → analyser → destination (speakers)
        // Note: A MediaElementSource can only be created ONCE per element.
        if (!this._elementSourcesMap.has(audioEl)) {
            const source = this._ctx.createMediaElementSource(audioEl);
            this._elementSourcesMap.set(audioEl, source);
        }
        
        this._elementSource = this._elementSourcesMap.get(audioEl);
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
     * The audio is played through the browser speakers and analyzed for lip sync.
     *
     * Uses a hidden <audio> element to support streaming playback.
     * @param {string} url
     */
    async startFromUrl(url) {
        this.stop();
        await this._ensureContextResumed();

        // Loud warning if the AudioContext is still suspended here.
        // This is the #1 cause of "audio streams but nothing plays":
        // MediaElementAudioSourceNode routes the <audio> through Web
        // Audio, and if the context is suspended the whole pipeline is
        // silent — bytes stream, server logs 200 OK, but no sound.
        if (this._ctx.state !== 'running') {
            console.warn(
                '[LipSync] ⚠ AudioContext is "%s" — audio will NOT play. ' +
                'Click anywhere on the browser tab to unlock it.',
                this._ctx.state
            );
        }

        this._analyser = this._ctx.createAnalyser();
        this._analyser.fftSize = 256;
        this._freqData = new Uint8Array(this._analyser.frequencyBinCount);

        const audio = new Audio(url);
        audio.crossOrigin = "anonymous";

        // Some browsers require the element to be in the DOM for certain features
        audio.style.display = 'none';
        document.body.appendChild(audio);

        // Reuse existing MediaElementSource if we've seen this element before
        if (!this._elementSourcesMap.has(audio)) {
            const source = this._ctx.createMediaElementSource(audio);
            this._elementSourcesMap.set(audio, source);
        }

        this._elementSource = this._elementSourcesMap.get(audio);
        this._elementSource.connect(this._analyser);
        // Connect to destination so audio plays through browser speakers
        this._analyser.connect(this._ctx.destination);

        this._boundAudioEl = audio;
        this._active = true;

        audio.addEventListener('ended', this._onAudioEnded);
        audio.addEventListener('error', (e) => {
            // Only log if we didn't just stop it ourselves
            if (this._active && this._boundAudioEl === audio) {
                console.error('[LipSync] Audio stream error:', e);
                this.stop();
            }
        });

        try {
            await audio.play();
            console.log('[LipSync] Started audio playback + lip sync for stream:', url);
        } catch (err) {
            // AbortError is expected if stop() is called before play() finishes
            if (err.name !== 'AbortError') {
                console.error('[LipSync] Failed to play audio stream:', err);
                this.stop();
            }
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
            
            // Explicitly stop playback/streaming for URL mode
            try {
                this._boundAudioEl.pause();
                this._boundAudioEl.src = "";
                this._boundAudioEl.load();
                if (this._boundAudioEl.parentNode) {
                    this._boundAudioEl.parentNode.removeChild(this._boundAudioEl);
                }
            } catch (e) { /* ignore cleanup errors */ }
            
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

        // We do NOT close the context here so we can reuse it
        /*
        if (this._ctx) {
            this._ctx.close().catch(() => {});
            this._ctx = null;
        }
        */

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

        // Use TimeDomainData for cleaner amplitude (volume) analysis
        this._analyser.getByteTimeDomainData(this._freqData);

        let sum = 0;
        for (let i = 0; i < this._freqData.length; i++) {
            const amplitude = Math.abs(this._freqData[i] - 128); // 128 is neutral in Uint8 bytes
            sum += amplitude;
        }
        const rawVolume = sum / (this._freqData.length * 128);

        // Smooth the volume to reduce jitter
        this._smoothVolume += (rawVolume - this._smoothVolume) * (1 - this.smoothing);

        // Occasional debug log
        if (this._smoothVolume > 0.05 && Math.random() < 0.01) {
            console.log(`[LipSync] Volume: ${this._smoothVolume.toFixed(3)} (Raw: ${rawVolume.toFixed(3)})`);
        }

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
