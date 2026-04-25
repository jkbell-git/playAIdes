/**
 * sttClient.js — POSTs an audio blob to the server's /api/stt/proxy
 * and returns the transcription.
 *
 * The server forwards to the Whisper container; the browser never
 * talks to Whisper directly. Symmetric with the existing TTS proxy.
 */
export class SttClient {
    /** @param {string} apiBase  e.g. "http://localhost:8765" */
    constructor(apiBase) {
        this.apiBase = String(apiBase).replace(/\/+$/, '');
    }

    /**
     * Send an audio blob and resolve to the transcript.
     * @param {Blob} blob
     * @returns {Promise<{text: string, language: string}>}
     */
    async transcribe(blob) {
        const form = new FormData();
        form.append('audio', blob, 'utterance.webm');

        const response = await fetch(`${this.apiBase}/api/stt/proxy`, {
            method: 'POST',
            body: form,
        });
        if (!response.ok) {
            const detail = await response.text().catch(() => '');
            throw new Error(`STT proxy ${response.status}: ${detail || 'unknown error'}`);
        }
        return response.json();
    }
}
