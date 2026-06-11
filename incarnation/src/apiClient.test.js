import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from './apiClient.js';

describe('ApiClient', () => {
  beforeEach(() => { global.fetch = vi.fn(); });

  it('createPersona posts the body with the bearer token to /api/v1', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 'x' }) });
    const api = new ApiClient('the-key');
    await api.createPersona('New Friend', 'hello');
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/personas');
    expect(opts.method).toBe('POST');
    expect(opts.headers.Authorization).toBe('Bearer the-key');
    expect(JSON.parse(opts.body)).toEqual({ name: 'New Friend', description: 'hello' });
  });

  it('omits the Authorization header when no key is configured (dev mode)', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    await new ApiClient().listPersonas();
    const [, opts] = global.fetch.mock.calls[0];
    expect(opts.headers.Authorization).toBeUndefined();
  });

  it('prefixes a configured base and encodes ids in paths', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    const api = new ApiClient(null, 'http://host:8765');
    await api.getPersona('a b');
    expect(global.fetch.mock.calls[0][0]).toBe('http://host:8765/api/v1/personas/a%20b');
  });

  it('deletePersona resolves null on 204 without reading a body', async () => {
    const json = vi.fn();
    global.fetch.mockResolvedValue({ ok: true, status: 204, json });
    expect(await new ApiClient().deletePersona('x')).toBeNull();
    expect(json).not.toHaveBeenCalled();
  });

  it('replaceTriggers PUTs the bare array', async () => {
    global.fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    const trig = [{ on: { phrase: 'p' }, do: { skill: 's', params: {} } }];
    await new ApiClient().replaceTriggers('a', trig);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toBe('/api/v1/personas/a/triggers');
    expect(opts.method).toBe('PUT');
    expect(JSON.parse(opts.body)).toEqual(trig);
  });

  it('throws the server detail string on an error status', async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: 'cannot delete the active persona' }),
    });
    await expect(new ApiClient().deletePersona('a'))
      .rejects.toThrow('cannot delete the active persona');
  });

  it('falls back to method/path/status when the error body is not a string', async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ loc: [] }] }) });
    await expect(new ApiClient().updatePersona('a', {}))
      .rejects.toThrow('PUT /personas/a -> 422');
  });
});
