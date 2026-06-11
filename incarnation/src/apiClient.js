// Shared REST client for the playAIdes /api/v1 surface — the ICD's
// consumer-side seed (spec 2026-06-10 D4), starting with the persona resource.
// Plain JS, no framework: importable by vanilla pages (creator.js) and React
// (console) alike. Mold: console/consoleApi.js — same bearer-header handling,
// except the header is omitted entirely when no key is configured so dev-mode
// pages (PLAYAIDES_API_KEY unset) work without one.

const BASE = '/api/v1';

export class ApiClient {
  constructor(apiKey = null, base = '') {
    this.apiKey = apiKey;
    this.base = base;
  }

  async _req(method, path, body) {
    const headers = { 'Content-Type': 'application/json' };
    if (this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;
    const res = await fetch(`${this.base}${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      // Surface FastAPI's {detail: "..."} when it's a plain string (404/409);
      // 422 detail is a list of error objects — fall back to the terse form.
      const detail = await res.json().then((d) => d?.detail).catch(() => null);
      throw new Error(typeof detail === 'string' ? detail : `${method} ${path} -> ${res.status}`);
    }
    return res.status === 204 ? null : res.json();
  }

  listPersonas() { return this._req('GET', '/personas'); }
  getPersona(id) { return this._req('GET', `/personas/${encodeURIComponent(id)}`); }
  createPersona(name, description = '') {
    return this._req('POST', '/personas', { name, description });
  }
  updatePersona(id, doc) {
    return this._req('PUT', `/personas/${encodeURIComponent(id)}`, doc);
  }
  deletePersona(id) { return this._req('DELETE', `/personas/${encodeURIComponent(id)}`); }
  getTriggers(id) { return this._req('GET', `/personas/${encodeURIComponent(id)}/triggers`); }
  replaceTriggers(id, list) {
    return this._req('PUT', `/personas/${encodeURIComponent(id)}/triggers`, list);
  }
}
