# Integrations Console — v1 design (generic provider seam + Home Assistant)

- **Status:** Designed 2026-06-08 (brainstormed) · awaiting implementation plan
- **Type:** Feature design / spec
- **Related:** `docs/frontend-architecture.md` (React-per-page decision), `skills/` framework,
  `ha_client.py`, `bin/silver-launch.py`

## Context

playAIdes integrates external services today by **hardcoding** them: the camera entity is baked
into `persona.json` / `data/control.html` / `ha/*.yaml`, the Fire-TV launch targets are a `BOXES`
dict in `bin/silver-launch.py`, and the Home Assistant connection comes from `HA_URL` / `HA_TOKEN`
in `.env`. There is no UI to manage any of this, and adding or repointing a device means editing
source.

We want a **system-level config console** that lets the operator connect external services,
**scan** them to discover what they expose, and **map** those into playAIdes capabilities — starting
with Home Assistant, but **not coupled to HA**. The operator has described a large future surface
(other IoT, web APIs, and AI agents), so the design must keep HA behind a generic seam.

This is distinct from **per-persona skill assignment** (`enabled_skills`), which is explicitly out
of scope here.

## Goal

A React config console + backend that lets the operator:
1. Connect & configure an external service (HA first), with health status.
2. **Scan** a connected service to discover its entities.
3. **Map** discovered entities to playAIdes capabilities (PiP camera, launch targets, say-target,
   triggerable scripts), replacing the hardcoded values.
4. Test-fire a mapping to verify it before relying on it.

## Scope

**In scope (v1):**
- A generic **provider seam** (`connect/health`, `discover`, `invoke`).
- **One** concrete provider: Home Assistant (wrapping `ha_client.py`).
- A backend-owned **config store** + a separate **secrets store** + a one-time **migration seed**.
- New FastAPI endpoints for providers / config / secret / scan / mappings / health / invoke.
- A **React** console page (master–detail layout), added to the Vite MPA.
- A contained refactor so the launch/camera/say features **read mappings from the store**.

**Out of scope:**
- **TTS / voice** anything (another agent is actively rebuilding the TTS service — avoid collisions).
- Per-persona skill enable/disable (`enabled_skills`).
- v2/v3 providers (below) — designed *not to be boxed out*, but not built.

**Decomposition / roadmap (tracked in `CONTINUITY.md`):**
- **v2:** a Web-API provider (calendar, weather — REST; leans on the existing declarative http-skill
  mechanism).
- **v3:** an Agent provider (Hermes-style agents that *act*, e.g. write a web service). Genuinely
  different shape; design when real.

## Key decisions

- **Audience = single operator now, extensible later (option C).** Auth reuses the existing
  `require_api_key` gate — no user accounts. The data model leaves room for a future user/scope
  dimension without reshaping.
- **Approach = thin provider seam (option ①).** Build the seam, implement only HA; let the framework
  *emerge* from the second real provider rather than guessing it now.
- **UI = master–detail (layout A).** Provider list in a left sidebar; right panel with
  Connection / Discovered / Mappings tabs. Chosen for how the provider surface will grow.
- **Secrets = separate backend-owned file** (`config/secrets.json`), not the shared `.env`. The
  backend can rewrite its own file atomically without risking the hand-maintained `.env`.
- **Secret handling = write-only.** The token is POSTed once, persisted server-side, **never
  returned** to the browser; the UI shows only "set ✓" + live health. Validation is by HA
  health-probe, never by echoing the value. (This never passes through the agent/chat.)
- **Migration seed = included.** Makes the cutover to "store is source of truth" seamless.

## Architecture

### Provider seam

A minimal Python interface (ABC), deliberately small so HA's needs shape it without over-fitting:

```
Provider:
    id / kind            # "homeassistant"
    config_schema        # fields needed to connect (e.g. base_url); secrets referenced, not inlined
    health() -> Status   # reachable + authenticated? carries a reason on failure
    discover() -> [Item] # normalized, grouped: {id, domain, name, capabilities}
    invoke(capability, target, args) -> result
```

A **fake provider** implementing this interface is built for tests — it locks the seam contract and
serves as the template for v2/v3.

### Home Assistant provider

`providers/homeassistant.py`, wrapping the existing `ha_client.py`:
- `health()` → `ha_client.health_check()`; distinguishes timeout vs 401-auth vs non-JSON.
- `discover()` → `GET /api/states`, normalized and grouped by domain (`camera.*`, `media_player.*`,
  `script.*`, `light.*`, `sensor.*`, …).
- `invoke()` → HA service calls / `ha_client.camera_url()` / the launch sequence.

### Capability mapping

playAIdes capabilities are **generic keys** bound to `(provider, entity)`:
`pip_camera`, `say_target`, `launch_targets[]`, `scripts[]`. The same shape works for any future
provider. This layer is what replaces the hardcoded camera entity and `BOXES`.

### Config store (`config/integrations.json`, gitignored)

```jsonc
{
  "providers": {
    "homeassistant": {
      "kind": "homeassistant", "enabled": true,
      "config": { "base_url": "http://homeassistant.local:8123" }   // token NOT here
    }
  },
  "mappings": {
    "pip_camera":     { "provider": "homeassistant", "entity": "camera.printer_gym_camera_hd_stream" },
    "say_target":     { "provider": "homeassistant", "entity": "media_player.fire_tv_bedroom" },
    "launch_targets": [ { "provider": "homeassistant", "entity": "media_player.fire_tv_192_168_0_233", "label": "bedroom" } ],
    "scripts":        [ { "provider": "homeassistant", "entity": "script.silver_greet", "label": "greet" } ]
  }
}
```

A `config_store` module owns typed load/save with **atomic writes** (temp + rename). It is the single
source of truth read by both the API and the existing features.

### Secrets store (`config/secrets.json`, gitignored)

Holds `homeassistant.token`. Write-only via the API; never returned. The token **resolver** reads
this file first and falls back to env `HA_TOKEN` for back-compat, so existing setups keep working.

### Migration seed

On first run only (when `config/integrations.json` is absent), the backend writes an initial store
from today's hardcoded values: HA `base_url`/token from env, the camera entity bound to `pip_camera`,
the three `BOXES` Fire TVs as `launch_targets`. Runs once; afterward the file is authoritative.

### API surface

All routes behind the existing `require_api_key`:

| Method & path | Purpose |
|---|---|
| `GET /api/integrations` | list providers + health/status |
| `POST /api/integrations/{id}/config` | set non-secret connection config (e.g. base_url) |
| `POST /api/integrations/{id}/secret` | set credential (write-only, never echoed) |
| `GET /api/integrations/{id}/health` | probe connection + auth |
| `POST /api/integrations/{id}/scan` | run `discover()`, return grouped entities |
| `GET\|PUT /api/integrations/{id}/mappings` | get/set capability → entity mappings |
| `POST /api/integrations/{id}/invoke` | test-fire a capability (preview camera / run script) |

### Frontend

- New React page (e.g. `incarnation/console.html` + `src/console/`), added as a Vite MPA entry.
- **Infra fix:** create `incarnation/vite.config.js` with `rollupOptions.input` listing all entry
  points (`index`, `creator`, `design-preview`, `console`) — the MPA build is currently
  unconfigured. Add `@vitejs/plugin-react` + `react`/`react-dom`. (Confirm during planning how
  `creator.html`/`design-preview.html` are served today so nothing regresses.)
- Styled with the shared CSS theme tokens (framework-agnostic layer per `frontend-architecture.md`).
- Master–detail layout (A): sidebar provider list + tabbed detail (Connection / Discovered / Mappings).
- Auth via the existing API key.

## Data flow

1. **Connect** — `POST …/config` + `POST …/secret` → persisted → `GET …/health` → "connected ✓".
2. **Scan** — `POST …/scan` → HA `GET /api/states` → normalized/grouped → UI shows entities.
3. **Map** — user binds capabilities to entities → `PUT …/mappings` → persisted.
4. **Test-fire** — `POST …/invoke` confirms a mapping works before it's relied on.
5. **Consume** — launch/camera/say read mappings from the store at runtime.

## Error handling

- HA unreachable / bad token → health reports a reason (timeout / 401-auth / non-JSON); scan & invoke
  return structured errors surfaced in the UI.
- Empty scan → "no entities in that domain", not a failure.
- **Stale mapping** (entity removed in HA) → flagged "unresolved" in the UI; features degrade
  gracefully. This is also the hook to fix the existing *"camera offline fails silently"* known issue.
- Atomic writes for both store files → no corruption on a mid-write crash.
- All endpoints behind `require_api_key`; the secret is never echoed.

## Blast radius (the contained refactor)

For mappings to matter, these must read from the store instead of hardcoded IDs:
- `bin/silver-launch.py` — `BOXES` → `launch_targets` from the store.
- Camera entity references (`data/control.html` default, `incarnation_server.py` launch/camera paths).
- The "say-on-TV" target.

Kept strictly clear of any TTS/voice code. The migration seed makes this cutover non-breaking.

## Testing (TDD)

- **Unit:** HA `discover()` normalization (mock `/api/states` → grouped items); `config_store`
  load/save + atomic write + migration seed; token resolver (secrets file vs env fallback); mapping
  resolution + stale handling.
- **Integration:** the new FastAPI routes against a mocked HA (mirrors `tests/integration/
  test_event_endpoint.py`, `test_voice_endpoint.py`); verify the secret endpoint is write-only.
- **Seam contract:** a fake provider implementing the interface — locks the seam, templates v2/v3.
- **Frontend:** light component tests via the existing vitest setup; minimal for v1.

## Open items for the plan

- Confirm how `creator.html` / `design-preview.html` are built/served today before adding the Vite
  MPA config, so existing pages don't regress.
- Exact normalized `Item` shape and which HA domains to surface in v1 (camera, media_player, script
  at minimum).
- Whether `invoke` test-fire for "show camera" reuses the existing camera-PiP path end-to-end.
