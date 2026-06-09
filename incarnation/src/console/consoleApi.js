// Thin fetch wrappers around the /api/v1/integrations* routes. All requests carry
// the API key; the secret POST is write-only (the value is never read back). This
// module is the console's slice of the frontend API client (the ICD's consumer side).

const BASE = '/api/v1/integrations';

export class ConsoleApi {
  constructor(apiKey, base = '') {
    this.apiKey = apiKey;
    this.base = base;
  }

  async _req(method, path, body) {
    const res = await fetch(`${this.base}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`);
    return res.json();
  }

  list() { return this._req('GET', BASE); }
  setConfig(id, config) { return this._req('POST', `${BASE}/${id}/config`, { config }); }
  setSecret(id, key, value) { return this._req('POST', `${BASE}/${id}/secret`, { key, value }); }
  health(id) { return this._req('GET', `${BASE}/${id}/health`); }
  scan(id) { return this._req('POST', `${BASE}/${id}/scan`); }
  getMappings(id) { return this._req('GET', `${BASE}/${id}/mappings`); }
  putMappings(id, mappings) { return this._req('PUT', `${BASE}/${id}/mappings`, { mappings }); }
  invoke(id, capability, target, args = {}) {
    return this._req('POST', `${BASE}/${id}/invoke`, { capability, target, args });
  }
}
