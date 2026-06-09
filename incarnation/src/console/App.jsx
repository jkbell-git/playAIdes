import React, { useEffect, useState } from 'react';
import { ConsoleApi } from './consoleApi.js';
import { groupByDomain, setPipCameraSource, setPipUrlSource } from './mappingsModel.js';

// API key for local/dev use: pulled from the ?key= query param (kept out of source).
const API_KEY = new URLSearchParams(window.location.search).get('key') || '';
const PROVIDER = 'homeassistant';
const TABS = ['Connection', 'Discovered', 'Mappings'];

export function App() {
  const api = new ConsoleApi(API_KEY);
  const [tab, setTab] = useState('Connection');
  const [health, setHealth] = useState(null);
  const [groups, setGroups] = useState({});
  const [mappings, setMappings] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.health(PROVIDER).then(setHealth).catch(() => setHealth({ ok: false, reason: 'unreachable' }));
    api.getMappings(PROVIDER).then((r) => setMappings(r.mappings)).catch(() => {});
  }, []);

  async function savePip(nextState) {
    setMappings(nextState.mappings);
    await api.putMappings(PROVIDER, nextState.mappings);
  }

  async function onScan() {
    setBusy(true);
    try {
      const { groups } = await api.scan(PROVIDER);
      setGroups(groups);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="console">
      <aside className="console__sidebar">
        <h1 className="console__title">Integrations</h1>
        <button className="console__provider console__provider--active">Home Assistant</button>
      </aside>
      <main className="console__detail">
        <nav className="console__tabs">
          {TABS.map((t) => (
            <button
              key={t}
              className={`console__tab ${t === tab ? 'console__tab--active' : ''}`}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>

        {tab === 'Connection' && (
          <section className="console__panel">
            <p>Status: {health ? (health.ok ? 'connected ✓' : `offline — ${health.reason}`) : '…'}</p>
            <SecretForm api={api} onSaved={() => api.health(PROVIDER).then(setHealth)} />
          </section>
        )}

        {tab === 'Discovered' && (
          <section className="console__panel">
            <button onClick={onScan} disabled={busy}>{busy ? 'Scanning…' : 'Scan'}</button>
            {Object.entries(groupByDomain(Object.values(groups).flat())).map(([domain, items]) => (
              <div key={domain} className="console__group">
                <h3>{domain}</h3>
                <ul>{items.map((i) => <li key={i.id}>{i.name} <code>{i.id}</code></li>)}</ul>
              </div>
            ))}
          </section>
        )}

        {tab === 'Mappings' && (
          <section className="console__panel">
            <h3>PiP display source</h3>
            <p>
              Current: {mappings.pip
                ? (mappings.pip.kind === 'url'
                    ? `URL — ${mappings.pip.url}`
                    : `camera — ${mappings.pip.entity}`)
                : '(unset)'}
            </p>
            <PipSourceForm
              cameras={groups.camera || []}
              onPickCamera={(entity) => savePip(setPipCameraSource({ mappings }, PROVIDER, entity))}
              onPickUrl={(url, label) => savePip(setPipUrlSource({ mappings }, url, label))}
            />
            <p className="console__hint">
              say_target, launch_targets and scripts mappings follow the same pattern (single entity / lists).
            </p>
          </section>
        )}
      </main>
    </div>
  );
}

// PiP is a generic display slot: pick a discovered camera, OR enter a website/doc URL.
function PipSourceForm({ cameras, onPickCamera, onPickUrl }) {
  const [url, setUrl] = useState('');
  const [label, setLabel] = useState('');
  return (
    <div className="console__pip">
      <label>Camera source
        <select defaultValue="" onChange={(e) => e.target.value && onPickCamera(e.target.value)}>
          <option value="" disabled>Choose a discovered camera…</option>
          {cameras.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.id})</option>)}
        </select>
      </label>
      <form onSubmit={(e) => { e.preventDefault(); onPickUrl(url, label); setUrl(''); setLabel(''); }}>
        <label>URL source (website / document link)
          <input type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label>Label
          <input type="text" placeholder="dashboard" value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <button type="submit" disabled={!url}>Use this URL</button>
      </form>
    </div>
  );
}

function SecretForm({ api, onSaved }) {
  const [value, setValue] = useState('');
  return (
    <form
      className="console__secret"
      onSubmit={async (e) => {
        e.preventDefault();
        await api.setSecret(PROVIDER, 'token', value);
        setValue(''); // never keep the token in component state after save
        onSaved();
      }}
    >
      <label>HA token (write-only)
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <button type="submit" disabled={!value}>Save token</button>
    </form>
  );
}
