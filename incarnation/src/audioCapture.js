/**
 * audioCapture.js — mic capture + energy-threshold VAD.
 *
 * Lifecycle:
 *   const cap = new AudioCapture({ silenceThreshold: 0.02, ... });
 *   cap.addEventListener('voicestart', () => { ... });
 *   cap.addEventListener('voiceend', (e) => sttSend(e.detail.blob));
 *   await cap.start();   // requests mic permission
 *
 * `detectVoiceState` is exported as a pure function so the bouncing
 * between silent / voice states can be unit-tested without DOM APIs.
 */

const DEFAULTS = Object.freeze({
    silenceThreshold: 0.02,   // RMS energy [0,1] below this is "silence"
    minVoiceMs: 200,          // need this much sustained voice before voicestart
    silenceMs: 800,           // need this much sustained silence before voiceend
    pollIntervalMs: 50,       // how often we sample the analyser
    fftSize: 1024,
});

/**
 * Pure VAD state machine — call once per audio sample tick.
 *
 * @param {object} args
 * @param {number} args.energy             RMS energy of the current sample
 * @param {number} args.silenceThreshold
 * @param {boolean} args.currentlyVoice
 * @param {number|null} args.voiceStartedAt   ms timestamp when a candidate voice run began
 * @param {number|null} args.silenceStartedAt ms timestamp when a candidate silence run began
 * @param {number} args.now
 * @param {number} args.minVoiceMs
 * @param {number} args.silenceMs
 *
 * @returns {{event: 'voicestart'|'voiceend'|null, currentlyVoice: boolean,
 *           voiceStartedAt: number|null, silenceStartedAt: number|null}}
 */
export function detectVoiceState({
    energy, silenceThreshold,
    currentlyVoice, voiceStartedAt, silenceStartedAt,
    now, minVoiceMs, silenceMs,
}) {
    const isVoice = energy >= silenceThreshold;

    if (!currentlyVoice) {
        // Looking for sustained voice to fire voicestart.
        if (isVoice) {
            if (voiceStartedAt === null) {
                return { event: null, currentlyVoice: false,
                         voiceStartedAt: now, silenceStartedAt: null };
            }
            if (now - voiceStartedAt >= minVoiceMs) {
                return { event: 'voicestart', currentlyVoice: true,
                         voiceStartedAt, silenceStartedAt: null };
            }
            return { event: null, currentlyVoice: false,
                     voiceStartedAt, silenceStartedAt: null };
        }
        // Below threshold — clear any pending voice run.
        return { event: null, currentlyVoice: false,
                 voiceStartedAt: null, silenceStartedAt: null };
    }

    // Already in voice — looking for sustained silence to fire voiceend.
    if (!isVoice) {
        if (silenceStartedAt === null) {
            return { event: null, currentlyVoice: true,
                     voiceStartedAt, silenceStartedAt: now };
        }
        if (now - silenceStartedAt >= silenceMs) {
            return { event: 'voiceend', currentlyVoice: false,
                     voiceStartedAt: null, silenceStartedAt: null };
        }
        return { event: null, currentlyVoice: true,
                 voiceStartedAt, silenceStartedAt };
    }
    // Voice resumed — cancel any pending silence run.
    return { event: null, currentlyVoice: true,
             voiceStartedAt, silenceStartedAt: null };
}

/** Compute RMS energy [0,1] from a Float32 time-domain frame. */
function rms(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
}

export class AudioCapture extends EventTarget {
    constructor(options = {}) {
        super();
        this.config = { ...DEFAULTS, ...options };
        this.stream = null;
        this.audioContext = null;
        this.analyser = null;
        this.recorder = null;
        this.pollTimer = null;
        this._chunks = [];
        this._vadState = {
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
        };
    }

    async start() {
        if (this.stream) return;   // idempotent
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true },
        });
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = this.audioContext.createMediaStreamSource(this.stream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = this.config.fftSize;
        source.connect(this.analyser);

        // Pick a mime type the browser supports. webm/opus is universal in
        // Chromium; Firefox prefers ogg/opus. Whisper handles both.
        let mimeType = 'audio/webm;codecs=opus';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'audio/ogg;codecs=opus';
        }
        this.recorder = new MediaRecorder(this.stream, { mimeType });
        this.recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) this._chunks.push(e.data);
        };
        this.recorder.onstop = () => {
            const blob = new Blob(this._chunks, { type: this.recorder.mimeType });
            const peakEnergy = this._lastPeakEnergy || 0;
            this._lastPeakEnergy = 0;
            this._chunks = [];
            this.dispatchEvent(new CustomEvent('voiceend', {
                detail: { blob, peakEnergy },
            }));
        };

        const buf = new Float32Array(this.analyser.fftSize);
        this.pollTimer = setInterval(() => this._tick(buf), this.config.pollIntervalMs);
    }

    _tick(buf) {
        this.analyser.getFloatTimeDomainData(buf);
        const energy = rms(buf);
        // Track peak energy across the current voice run so users running
        // with `?debug=1` can sanity-check the silenceThreshold against the
        // actual mic levels they're producing.
        if (energy > (this._peakEnergy || 0)) this._peakEnergy = energy;

        const next = detectVoiceState({
            energy,
            silenceThreshold: this.config.silenceThreshold,
            currentlyVoice: this._vadState.currentlyVoice,
            voiceStartedAt: this._vadState.voiceStartedAt,
            silenceStartedAt: this._vadState.silenceStartedAt,
            now: performance.now(),
            minVoiceMs: this.config.minVoiceMs,
            silenceMs: this.config.silenceMs,
        });
        this._vadState = {
            currentlyVoice: next.currentlyVoice,
            voiceStartedAt: next.voiceStartedAt,
            silenceStartedAt: next.silenceStartedAt,
        };

        if (next.event === 'voicestart') {
            this._chunks = [];
            this._peakEnergy = energy;
            this.recorder.start();
            this.dispatchEvent(new CustomEvent('voicestart'));
        } else if (next.event === 'voiceend') {
            // Surface the peak energy alongside the recorder.stop so callers
            // can correlate "Whisper heard nothing" with "the mic level
            // never crossed the threshold meaningfully."
            const peak = this._peakEnergy || 0;
            this._peakEnergy = 0;
            this.recorder.stop();   // triggers onstop → emits voiceend with blob
            // Stash the peak on the recorder so onstop's blob event can
            // include it in the detail payload.
            this._lastPeakEnergy = peak;
        }
    }

    async stop() {
        if (this.pollTimer) clearInterval(this.pollTimer);
        if (this.recorder && this.recorder.state !== 'inactive') this.recorder.stop();
        if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
        if (this.audioContext) await this.audioContext.close();
        this.stream = null;
        this.audioContext = null;
        this.analyser = null;
        this.recorder = null;
    }
}
