import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SttClient } from './sttClient.js';

describe('SttClient.transcribe', () => {
    let originalFetch;

    beforeEach(() => {
        originalFetch = global.fetch;
    });

    afterEach(() => {
        global.fetch = originalFetch;
    });

    it('POSTs the blob as multipart and returns the parsed JSON', async () => {
        const fakeFetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ text: 'hello there', language: 'en' }),
        });
        global.fetch = fakeFetch;

        const client = new SttClient('http://api.test:8765');
        const blob = new Blob(['fake-audio-bytes'], { type: 'audio/webm' });
        const result = await client.transcribe(blob);

        expect(result).toEqual({ text: 'hello there', language: 'en' });
        expect(fakeFetch).toHaveBeenCalledTimes(1);
        const [url, init] = fakeFetch.mock.calls[0];
        expect(url).toBe('http://api.test:8765/api/stt/proxy');
        expect(init.method).toBe('POST');
        expect(init.body).toBeInstanceOf(FormData);
        expect(init.body.get('audio')).toBeInstanceOf(Blob);
    });

    it('throws on non-2xx responses', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 502,
            text: async () => 'STT upstream error',
        });

        const client = new SttClient('http://api.test:8765');
        const blob = new Blob([''], { type: 'audio/webm' });
        await expect(client.transcribe(blob)).rejects.toThrow(/502/);
    });

    it('strips trailing slashes from the API base', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ text: '', language: '' }),
        });

        const client = new SttClient('http://api.test:8765/');
        await client.transcribe(new Blob([], { type: 'audio/webm' }));

        const [url] = global.fetch.mock.calls[0];
        expect(url).toBe('http://api.test:8765/api/stt/proxy');
    });
});
