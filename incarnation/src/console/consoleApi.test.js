import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ConsoleApi } from './consoleApi.js';

describe('ConsoleApi', () => {
  beforeEach(() => { global.fetch = vi.fn(); });

  it('sends the bearer token and posts the secret write-only to /api/v1', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    const api = new ConsoleApi('the-key');
    await api.setSecret('homeassistant', 'token', 'shh');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/integrations/homeassistant/secret');
    expect(opts.method).toBe('POST');
    expect(opts.headers.Authorization).toBe('Bearer the-key');
    expect(JSON.parse(opts.body)).toEqual({ key: 'token', value: 'shh' });
  });

  it('scan returns the grouped payload', async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ groups: { camera: [] } }) });
    const api = new ConsoleApi('k');
    const out = await api.scan('homeassistant');
    expect(out).toEqual({ groups: { camera: [] } });
  });
});
