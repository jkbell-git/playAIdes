import { scene, camera, renderer, controls, clock } from './scene.js';
import { Incarnation } from './incarnation.js';
import { ConnectionManager } from './connectionManager.js';

/**
 * main.js — Incarnation service entry point.
 *
 * Sets up the render loop, instantiates the Incarnation orchestrator,
 * and connects to PlayAIdes via WebSocket.
 */

// ── UI references ───────────────────────────────────────────────────────────
const statusOverlay = document.getElementById('status-overlay');
const statusText = document.getElementById('status-text');

function setStatus(state, text) {
  statusOverlay.className = state; // '', 'connected', 'loading'
  statusText.textContent = text;
}

// ── Incarnation & connection ────────────────────────────────────────────────
const incarnation = new Incarnation();
const connection = new ConnectionManager();

// Determine WebSocket URL from query params or default
// e.g. ?ws=ws://localhost:8765
const params = new URLSearchParams(window.location.search);
const wsUrl = params.get('ws') || 'ws://localhost:8765';

// ── Wire connection events to incarnation ───────────────────────────────────
connection.addEventListener('connected', () => {
  setStatus('connected', 'Connected to PlayAIdes');
});

connection.addEventListener('disconnected', () => {
  setStatus('', 'Disconnected — reconnecting…');
});

connection.addEventListener('error', () => {
  setStatus('', 'Connection error');
});

// Route all typed commands to the incarnation orchestrator
connection.addEventListener('load_model', async (e) => {
  try {
    setStatus('loading', 'Loading model…');
    const info = await incarnation.handleCommand('load_model', e.detail);
    setStatus('connected', 'Model loaded');
    // Report available animations/morphs back to PlayAIdes
    connection.send('status', { state: 'model_loaded', ...info });
  } catch (err) {
    console.error('[main] Failed to load model:', err);
    setStatus('connected', 'Model load failed');
    connection.send('status', { state: 'error', error: err.message });
  }
});

connection.addEventListener('play_animation', (e) => {
  incarnation.handleCommand('play_animation', e.detail);
});

connection.addEventListener('stop_animation', (e) => {
  incarnation.handleCommand('stop_animation', e.detail);
});

connection.addEventListener('set_expression', (e) => {
  incarnation.handleCommand('set_expression', e.detail);
});

connection.addEventListener('clear_expressions', (e) => {
  incarnation.handleCommand('clear_expressions', e.detail);
});

connection.addEventListener('play_viseme_sequence', (e) => {
  incarnation.handleCommand('play_viseme_sequence', e.detail);
});

// ── Render loop ─────────────────────────────────────────────────────────────
function animate() {
  requestAnimationFrame(animate);

  const delta = clock.getDelta();

  controls.update();
  incarnation.update(delta);
  renderer.render(scene, camera);
}

// ── Bootstrap ───────────────────────────────────────────────────────────────
setStatus('', 'Connecting…');
connection.connect(wsUrl);
animate();

console.log('[Incarnation] Service started — ws:', wsUrl);
