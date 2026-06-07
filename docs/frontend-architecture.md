# Frontend Architecture — playAIdes

- **Status:** Decided 2026-06-07
- **Type:** Architecture decision (standing reference)
- **Related:** `docs/superpowers/specs/2026-06-07-ui-theme-system-camera-split-design.md`

## Context

playAIdes has several front-end surfaces with very different jobs and target devices:

- **Viewer / kiosk** — the 3D avatar. Runs on the **Fire TV (Silk, an older Chromium)**, is **performance-critical**, vanilla JS + Three.js + `@pixiv/three-vrm`, built with Vite (already a multi-page app: `index.html`, `creator.html` are separate entry points).
- **Existing creator** — the voice/character design page (`creator.html`/`creator.js`), vanilla.
- **Planned pages** — character creation, character customization, settings, and "a lot of" further scene/page ideas. These would target **PC + mobile (modern browsers)**, not the Fire TV.

Question raised: should we adopt React? Whole-project or per-page? Plus performance concerns and old-browser compatibility.

## Decision

1. **Multi-page app; tech chosen per surface.** Vite MPA, one entry point per page; each page picks its own UI approach. **Not all-or-nothing** — React and vanilla coexist in one repo/build.
2. **Kiosk / viewer stays vanilla + Three.js.** It targets the weak Fire TV Silk browser and is perf-critical; a UI framework is pure overhead there.
3. **New PC/mobile pages may use React.** Character creation, customization, settings, future scenes — these are form-heavy and state-rich on modern browsers, where React's declarative state model earns its keep.
4. **The CSS theme system is the shared, framework-agnostic layer.** The 3-layer design tokens (palette → semantic roles → theme recipes) are plain CSS custom properties; they style vanilla **and** React pages identically and give one theme switch across all surfaces.
5. **Shared logic lives in plain JS modules** (persona registry, WebSocket client, etc.), importable by both vanilla and React pages — no duplication.
6. **No hand-written "backup" pages for old browsers.** Instead:
   - **Segment by target:** the Fire TV only loads the vanilla pages it needs; it never loads the React pages, so there's nothing to "fall back" from.
   - If a React page ever *must* run on an old browser, use **`@vitejs/plugin-legacy`** (transpiled + polyfilled `nomodule` fallback), not a second implementation.
7. **3D inside React without react-three-fiber.** Existing vanilla Three.js scenes (e.g. `creatorScene.js`) can be mounted in a React component via a `ref` + effect. r3f is optional, not required — so the working 3D code is reusable as-is.

## Framework choice for the React surfaces

- **Default: React** — biggest ecosystem (color pickers, sliders, drag-drop — handy for customization) and the most transferable/learnable.
- **Escape hatch if mobile bundle size bites: Preact** (same API, ~4KB, one-line Vite alias swap). Svelte/Solid are viable compile-away alternatives but a different paradigm and another thing to learn.
- The existing vanilla `creator.html`/`creator.js` **stays vanilla**; migrate to React only if/when it grows painful — don't rewrite working code for uniformity.

## Performance rationale

- React is **not a speed win; it's a complexity-management win.** Keep the perf-critical weak-device surface (viewer) lean and vanilla; put a framework only where the device is capable and the UI is complex.
- 3D performance is dominated by Three.js / WebGL / VRM, not the UI layer.

## Consequences / when to revisit

- Adopt React **per new page, as those pages are designed** — each gets its own brainstorm/spec. Don't design them all up front.
- Revisit the kiosk's vanilla choice only if it ever grows a large, deeply-interactive menu system on capable hardware.

## Scope note

This note records **direction only**. Each new page is scoped individually when it's built. The immediate work (viewer theme system + camera split) is unaffected and stays vanilla.
