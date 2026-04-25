import { describe, it, expect } from 'vitest';
import { detectVoiceState } from './audioCapture.js';

describe('detectVoiceState', () => {
    it('returns silent when energy is below threshold', () => {
        const result = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
            now: 1000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(result.event).toBe(null);
        expect(result.currentlyVoice).toBe(false);
    });

    it('emits voicestart after sustained voice above threshold', () => {
        // First tick crosses threshold, voiceStartedAt is set, no event yet.
        const t1 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
            now: 1000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t1.event).toBe(null);
        expect(t1.voiceStartedAt).toBe(1000);

        // 250ms later, still above threshold → voicestart fires.
        const t2 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: t1.voiceStartedAt,
            silenceStartedAt: null,
            now: 1250,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe('voicestart');
        expect(t2.currentlyVoice).toBe(true);
    });

    it('emits voiceend after sustained silence following voice', () => {
        // Already in voice, silence just started.
        const t1 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: null,
            now: 2000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t1.event).toBe(null);
        expect(t1.silenceStartedAt).toBe(2000);

        // 900ms later, still silent → voiceend fires.
        const t2 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: t1.silenceStartedAt,
            now: 2900,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe('voiceend');
        expect(t2.currentlyVoice).toBe(false);
    });

    it('cancels pending voicestart if energy drops before minVoiceMs', () => {
        const t1 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: null,
            silenceStartedAt: null,
            now: 1000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t1.voiceStartedAt).toBe(1000);

        // 100ms later, energy drops back below threshold → voiceStartedAt clears.
        const t2 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: false,
            voiceStartedAt: t1.voiceStartedAt,
            silenceStartedAt: null,
            now: 1100,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe(null);
        expect(t2.voiceStartedAt).toBe(null);
    });

    it('cancels pending voiceend if voice resumes before silenceMs', () => {
        const t1 = detectVoiceState({
            energy: 0.005,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: null,
            now: 2000,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        // Brief silence pause, then voice returns within 300ms.
        const t2 = detectVoiceState({
            energy: 0.05,
            silenceThreshold: 0.02,
            currentlyVoice: true,
            voiceStartedAt: 0,
            silenceStartedAt: t1.silenceStartedAt,
            now: 2300,
            minVoiceMs: 200,
            silenceMs: 800,
        });
        expect(t2.event).toBe(null);
        expect(t2.silenceStartedAt).toBe(null);
    });
});
