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
import { AudioCapture } from './audioCapture.js';
import { SttClient } from './sttClient.js';
import { matchPhrase } from './transcriptMatcher.js';

// ── Boot ────────────────────────────────────────────────────────────────────
const config = loadConfig();
console.log('[viewer] config:', config);

const stateMachine = new ViewerState(State.EMPTY);
const overlays = new ViewerOverlays(document, config, stateMachine);
const incarnation = new Incarnation();
const connection = new ConnectionManager();
const audioCapture = new AudioCapture();
const stt = new SttClient(config.apiBase);

// Last user utterance text — populated when STT returns, attached to the
// THINKING state's meta so the subtitle band can render it (greyed).
let lastUserUtterance = '';

// Active persona's matching config — populated by the server-pushed
// `persona_active` WS message after the avatar finishes loading.
let activePersona = { name: '', wake_words: [], dismiss_words: [] };

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

connection.addEventListener('persona_active', (e) => {
    activePersona = {
        name: e.detail?.name || '',
        wake_words: Array.isArray(e.detail?.wake_words) ? e.detail.wake_words : [],
        dismiss_words: Array.isArray(e.detail?.dismiss_words) ? e.detail.dismiss_words : [],
    };
    overlays.setPersonaName(activePersona.name);
    console.log('[viewer] persona_active:', activePersona);
});

// LipSyncManager fires this when the audio element ends or pauses.
incarnation.lipSyncManager.onAudioEnd(() => {
    if (stateMachine.current === State.SPEAKING) {
        safeTransition(State.AMBIENT);
    }
});

// ── Voice input → LISTENING → THINKING → user_input WS send ───────────────
audioCapture.addEventListener('voicestart', () => {
    // AMBIENT → LISTENING: normal active-conversation flow.
    // EMPTY: no UI transition (state machine forbids EMPTY → LISTENING by
    // design); the audio is still being recorded and will be sent to STT
    // on voiceend. The voiceend handler then checks for the wake word
    // before re-summoning the persona.
    if (stateMachine.current === State.AMBIENT) {
        safeTransition(State.LISTENING);
    }
});

audioCapture.addEventListener('voiceend', async (e) => {
    const wasListening = stateMachine.current === State.LISTENING;
    if (wasListening) {
        safeTransition(State.THINKING, { lastUtterance: '…' });
    }
    try {
        const { text } = await stt.transcribe(e.detail.blob);
        const transcript = (text || '').trim();
        if (!transcript) {
            if (wasListening) safeTransition(State.AMBIENT);
            return;
        }

        // 1. Dismiss check — always runs, regardless of activation mode.
        if (activePersona.dismiss_words.length) {
            const dismiss = matchPhrase(transcript, activePersona.dismiss_words);
            if (dismiss.matched) {
                console.log('[viewer] dismiss matched:', dismiss.phrase);
                // Already-EMPTY → safeTransition will warn and no-op (allowed).
                safeTransition(State.EMPTY);
                return;
            }
        }

        // 2. Wake-word gate — applied in `wake` mode OR when in EMPTY.
        let userInput = transcript;
        const inEmpty = stateMachine.current === State.EMPTY;
        const needsWake = config.activation === 'wake' || inEmpty;

        if (needsWake) {
            const wake = matchPhrase(transcript, activePersona.wake_words);
            if (!wake.matched) {
                console.log('[viewer] wake-mode drop, no wake-word in:', transcript);
                if (wasListening || stateMachine.current === State.THINKING) {
                    safeTransition(State.AMBIENT);
                }
                return;
            }
            userInput = wake.residual;
            console.log('[viewer] wake matched:', wake.phrase, '→ residual:', userInput);
        }

        // 3. Re-summon from EMPTY: state-only transition; intro-anim replay
        // is Phase 4 work.
        if (inEmpty) {
            safeTransition(State.INTRO);
            safeTransition(State.AMBIENT);
        }

        // 4. If wake-only utterance (no residual), just acknowledge — stay AMBIENT.
        if (!userInput) {
            return;
        }

        // 5. Update THINKING meta with the actual user message and forward.
        if (stateMachine.current === State.THINKING) {
            stateMachine.dispatchEvent(new CustomEvent('change', {
                detail: {
                    prev: State.THINKING, next: State.THINKING,
                    prevMeta: { lastUtterance: '…' },
                    meta: { lastUtterance: userInput },
                },
            }));
        }
        lastUserUtterance = userInput;
        connection.send('user_input', { text: userInput });
    } catch (err) {
        console.error('[viewer] STT failed:', err);
        if (stateMachine.current === State.LISTENING || stateMachine.current === State.THINKING) {
            safeTransition(State.AMBIENT);
        }
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
    try {
        await audioCapture.start();
        console.log('[viewer] mic + audio unlocked');
    } catch (err) {
        // Permission denied or no mic — viewer remains usable but no voice in.
        console.warn('[viewer] mic unavailable:', err);
    }
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
