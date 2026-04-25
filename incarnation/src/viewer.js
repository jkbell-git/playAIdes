/**
 * viewer.js — entry point for the new voice-driven viewer page.
 *
 * Reuses Incarnation + ConnectionManager + LipSyncManager unchanged.
 * Adds: ViewerState (state machine), ViewerOverlays (DOM rendering),
 * ViewerConfig (URL params).
 *
 * Phase 1 wires only INTRO / AMBIENT / SPEAKING — the LISTENING and
 * THINKING states will be reached in phase 2 once mic capture lands.
 */
import { scene, camera, renderer, controls, clock } from './scene.js';
import { Incarnation } from './incarnation.js';
import { ConnectionManager } from './connectionManager.js';
import { ViewerState, State } from './viewerState.js';
import { ViewerOverlays } from './viewerOverlays.js';
import { loadConfig } from './viewerConfig.js';

// ── Boot ────────────────────────────────────────────────────────────────────
const config = loadConfig();
console.log('[viewer] config:', config);

const stateMachine = new ViewerState(State.EMPTY);
const overlays = new ViewerOverlays(document, config, stateMachine);
const incarnation = new Incarnation();
const connection = new ConnectionManager();

// Pending text from the most recent assistant_message event — attached
// to the next SPEAKING transition so the subtitle band can render.
let pendingAssistantText = '';

// ── Connection + overlays ───────────────────────────────────────────────────
connection.addEventListener('connected', () => {
    overlays.setConnectionState('connected');
});
connection.addEventListener('disconnected', () => {
    overlays.setConnectionState('disconnected');
});
connection.addEventListener('error', () => {
    overlays.setConnectionState('error');
});

// ── Wire animation finished back to PlayAIdes (preserves existing flow) ────
incarnation.onAnimationFinished = (clipName) => {
    connection.send('status', { state: 'animation_finished', name: clipName });
};

// ── State transition helpers ────────────────────────────────────────────────
function safeTransition(next, meta) {
    try {
        stateMachine.transition(next, meta);
    } catch (err) {
        // Illegal transitions are warnings here, not crashes — phase 1
        // still has uncovered edges (e.g. SPEAKING → SPEAKING when a
        // user sends two messages back-to-back).
        console.warn('[viewer]', err.message);
    }
}

// ── WebSocket-driven transitions ────────────────────────────────────────────
connection.addEventListener('load_model', async (e) => {
    try {
        const info = await incarnation.handleCommand('load_model', e.detail);
        connection.send('status', { state: 'model_loaded', ...info });
        // We stay in EMPTY here — INTRO begins when the intro animation
        // actually starts playing (via play_animation below).
        if (incarnation.vrm) {
            const personaName =
                (incarnation.vrm.meta && incarnation.vrm.meta.title) ||
                e.detail.url?.split('/').pop()?.replace(/\.vrm$/i, '') ||
                'Persona';
            overlays.setPersonaName(personaName);
        }
    } catch (err) {
        console.error('[viewer] load_model failed:', err);
    }
});

connection.addEventListener('load_animation', async (e) => {
    const info = await incarnation.handleCommand('load_animation', e.detail);
    connection.send('status', { state: 'animation_loaded', ...info });
});
connection.addEventListener('load_mixamo_animation', async (e) => {
    const info = await incarnation.handleCommand('load_mixamo_animation', e.detail);
    connection.send('status', { state: 'animation_loaded', ...info });
});
connection.addEventListener('load_vrma_animation', async (e) => {
    const info = await incarnation.handleCommand('load_vrma_animation', e.detail);
    connection.send('status', { state: 'animation_loaded', ...info });
});

connection.addEventListener('play_animation', (e) => {
    const looped = e.detail?.loop !== false;
    incarnation.handleCommand('play_animation', e.detail);
    // Heuristic: a non-looped clip after EMPTY → INTRO transition.
    // A looped clip → AMBIENT.
    if (stateMachine.current === State.EMPTY) {
        if (looped) {
            // No intro configured; persona went straight to idle.
            safeTransition(State.INTRO);
            safeTransition(State.AMBIENT);
        } else {
            safeTransition(State.INTRO);
        }
    } else if (stateMachine.current === State.INTRO) {
        // The intro just got replaced by another animation — assume
        // it's the idle.
        if (looped) safeTransition(State.AMBIENT);
    }
});

// Existing onAnimationFinished hook → drive INTRO → AMBIENT.
const originalOnFinished = incarnation.onAnimationFinished;
incarnation.onAnimationFinished = (clipName) => {
    if (stateMachine.current === State.INTRO) {
        // Intro clip ended; PlayAIdes will respond with the idle clip,
        // but we eagerly transition so the UI doesn't stay on the
        // intro state visuals.
        safeTransition(State.AMBIENT);
    }
    if (originalOnFinished) originalOnFinished(clipName);
};

// ── assistant_message + start_lip_sync drive SPEAKING ──────────────────────
connection.addEventListener('assistant_message', (e) => {
    pendingAssistantText = e.detail?.text || '';
});

connection.addEventListener('start_lip_sync', (e) => {
    const fromAmbient = stateMachine.current === State.AMBIENT;
    if (!fromAmbient && stateMachine.current !== State.THINKING) {
        // Force-transition to AMBIENT first so the SPEAKING transition
        // is legal. This handles the case where the SPEAKING state
        // arrives while still in INTRO (server sent a chat reply during
        // the intro).
        try { safeTransition(State.AMBIENT); } catch (_) { /* fine */ }
    }
    safeTransition(State.SPEAKING, { text: pendingAssistantText });
    incarnation.handleCommand('start_lip_sync', e.detail);
});

connection.addEventListener('stop_lip_sync', () => {
    incarnation.handleCommand('stop_lip_sync', {});
    safeTransition(State.AMBIENT);
});

// LipSyncManager fires this when the audio element ends or pauses.
incarnation.lipSyncManager.onAudioEnd(() => {
    if (stateMachine.current === State.SPEAKING) {
        safeTransition(State.AMBIENT);
    }
});

// Generic catch-all for non-load_ commands (set_expression, focus_camera,
// set_background, etc.) — preserve existing behavior.
connection.addEventListener('message', (e) => {
    const msg = e.detail;
    if (msg.type
        && !msg.type.startsWith('load_')
        && msg.type !== 'play_animation'
        && msg.type !== 'start_lip_sync'
        && msg.type !== 'stop_lip_sync'
        && msg.type !== 'assistant_message') {
        incarnation.handleCommand(msg.type, msg.payload || {});
    }
});

// ── Audio Unlock ────────────────────────────────────────────────────────────
// First user gesture resumes AudioContext — same pattern as the previous
// main.js. Phase 2 will replace the listener-list with a richer mic flow.
const GESTURES = ['click', 'keydown', 'touchstart', 'pointerdown'];
async function unlockAudio() {
    GESTURES.forEach((t) => window.removeEventListener(t, unlockAudio, true));
    if (incarnation.lipSyncManager) {
        await incarnation.lipSyncManager.resume();
    }
    console.log('[viewer] audio unlocked');
}
GESTURES.forEach((t) => window.addEventListener(t, unlockAudio, true));

// ── Render loop ─────────────────────────────────────────────────────────────
function tick() {
    requestAnimationFrame(tick);
    const dt = clock.getDelta();
    controls.update();
    incarnation.update(dt);
    renderer.render(scene, camera);
}

// ── Connect + start ─────────────────────────────────────────────────────────
connection.connect(config.wsUrl);
tick();
console.log('[viewer] started — ws:', config.wsUrl);
