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
import { loadConfig, resolveAssetUrl } from './viewerConfig.js';
import { CameraDirector } from './cameraDirector.js';
import { createDebugPanel } from './debugPanel.js';
import { AudioCapture } from './audioCapture.js';
import { SttClient } from './sttClient.js';
import { matchPhrase } from './transcriptMatcher.js';
import { PersonasRegistry } from './personasRegistry.js';
import { WipeOverlay } from './wipeOverlay.js';
import { TranscriptModel } from './transcriptModel.js';
import { ChatPanel } from './chatPanel.js';
import { PipOverlay, pipViewFromMessage } from './pipOverlay.js';
// NOTE: stageLayout.js (the split-screen primitive) is parked for the future
// multi-3D-model "cast" view. It is intentionally NOT wired to the camera/PiP —
// a camera shows as a floating PiP, not a screen split.

// ── Boot ────────────────────────────────────────────────────────────────────
const config = loadConfig();
console.log('[viewer] config:', config);

// Kiosk / unattended TV mode (?kiosk=1): hide chrome via the body.kiosk CSS
// class and let the camera director own the camera (no user controls). The
// best-effort keep-awake + fullscreen ride on the first-gesture handler below.
const cameraDirector = new CameraDirector(camera, controls);
if (config.kiosk) {
    document.body.classList.add('kiosk');
    // Camera director intentionally NOT enabled — kiosk uses the same camera path
    // as windowed: focusOnHead (locked face shot) + frameFullBody (animations).
    // Lock orbit so the TV framing can't drift from a stray remote/CEC input; the
    // focus/animation shots still position the camera directly (update() ignores
    // the enabled flag).
    controls.enabled = false;
}

// Theme: drive the CSS [data-theme] layer. (The camera always shows as a floating PiP.)
document.body.dataset.theme = config.theme;

// Quality: low-power mode disables heavy FX (Fire TV ?quality=low).
if (config.quality === 'low') {
    document.body.classList.add('lowfx');
}

// ── Date badge (p5-basic top-left masthead) ──────────────────────────────────
const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
const DAYS   = ['SUN','MON','TUE','WED','THU','FRI','SAT'];
function _buildDateBadge() {
    const el = document.getElementById('date-badge');
    if (!el) return;
    const now = new Date();
    const mo  = MONTHS[now.getMonth()];
    const day = String(now.getDate()).padStart(2, '0');
    const dow = DAYS[now.getDay()];
    const hr  = now.getHours();
    const when = hr < 12 ? 'MORNING' : hr < 17 ? 'AFTERNOON' : hr < 21 ? 'EVENING' : 'NIGHT';
    el.innerHTML =
        `<div class="date-bg"></div>` +
        `<div class="date-row"><span class="date-m">${mo}</span><span class="date-d"><span>${day}</span></span><span class="date-dow">${dow}</span></div>` +
        `<div class="date-when">${when}</div>`;
}
_buildDateBadge();
setInterval(_buildDateBadge, 60_000);

// Dev aid: opt-in camera tuner (?debug=1) — sliders for height / target / distance
// with a live pose readout + copy, so a hand-framed shot can be read off and baked in.
createDebugPanel(camera, controls);

// Backend command payloads may carry a hardcoded http://localhost:8765 asset URL
// (uploaded personas); rewrite it to the host that served this page so models /
// animations / backgrounds load on remote devices (TVs). Relative URLs pass through.
const withResolvedUrl = (payload) =>
    (payload && payload.url) ? { ...payload, url: resolveAssetUrl(payload.url, config.apiBase) } : payload;

const stateMachine = new ViewerState(State.EMPTY);
const overlays = new ViewerOverlays(document, config, stateMachine);
const pip = new PipOverlay(document);
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

const personasRegistry = new PersonasRegistry();
const wipeOverlay = new WipeOverlay(document.getElementById('wipe-overlay'));

const transcriptModel = new TranscriptModel();
const chatPanel = new ChatPanel(document, transcriptModel, {
    initialOpen: config.chat === 'open',
});

// When the panel form is submitted, treat it like a voice transcription:
// send user_input and append the user line locally so it shows up
// immediately (assistant_message will append the reply).
function submitUserText(text) {
    const t = (text || '').trim();
    if (!t) return;
    transcriptModel.append({ role: 'user', content: t });
    // Tag the user_input with the active persona's id so multi-TV routing
    // delivers the reply to the right clients.
    const activeId = getActivePersonaId();
    connection.send('user_input', activeId ? { text: t, persona_id: activeId } : { text: t });
}
chatPanel.addEventListener('submit', (e) => submitUserText(e.detail.text));

// Unified bottom console (subtitle + text input) — stays visible in kiosk,
// where the side chat panel and subtitle band are hidden, so a remote TV can
// always read replies and type. Shares submitUserText + the transcript model.
const consoleLogEl = document.getElementById('console-log');
const consoleBarEl = document.getElementById('console-bar');
const consoleFormEl = document.getElementById('console-input-row');
const consoleInputEl = document.getElementById('console-input');
// Start idle so the dialogue box + its name tag stay hidden until there's a line to show.
consoleBarEl?.classList.add('console-idle');
if (consoleFormEl && consoleInputEl) {
    consoleFormEl.addEventListener('submit', (e) => {
        e.preventDefault();
        submitUserText(consoleInputEl.value);
        consoleInputEl.value = '';
    });
}
// Render the last few transcript messages as the bottom conversation log; the
// newest line is emphasized (it serves as the subtitle). Driven by the same
// TranscriptModel the (now-retired) side panel used, so voice, text, and loaded
// history all surface here.
// Auto-fade the log when idle so it doesn't blanket the avatar; a new message,
// input focus, or pointer/key activity brings it back for a few seconds.
let _consoleFadeTimer = null;
function pokeConsole() {
    if (!consoleLogEl) return;
    consoleLogEl.classList.remove('faded');
    consoleBarEl?.classList.remove('console-idle');
    clearTimeout(_consoleFadeTimer);
    _consoleFadeTimer = setTimeout(() => {
        consoleLogEl.classList.add('faded');
        consoleBarEl?.classList.add('console-idle');
    }, 8000);
}

const CONSOLE_LOG_LINES = 4;
function renderConsoleLog(e) {
    if (!consoleLogEl) return;
    const msgs = transcriptModel.messages.slice(-CONSOLE_LOG_LINES);
    consoleLogEl.replaceChildren();
    for (const m of msgs) {
        const line = document.createElement('div');
        line.className = 'console-msg ' + (m.role === 'user' ? 'user' : 'assistant');
        const who = m.role === 'user' ? 'You' : (m.persona_name || activePersona.name || 'Silver');
        line.textContent = `${who}: ${m.content}`;
        consoleLogEl.appendChild(line);
    }
    // Only reveal on a NEW message. On reload, history fills the log via
    // replaceAll but stays faded so old subtitles don't pop up on load.
    if (e && e.detail && e.detail.kind === 'append') pokeConsole();
}
transcriptModel.addEventListener('change', renderConsoleLog);
if (consoleInputEl) consoleInputEl.addEventListener('focus', pokeConsole);

// ── Command / debug log (p5-basic console under the PiP) ─────────────────────
// Shows the REAL stream of commands the backend drives the viewer with, so you
// can see what the persona is doing. Sanitized: secret-looking fields are
// redacted, URLs lose their query string, long values are truncated; noisy
// per-frame commands (visemes / expressions) are skipped.
const CMD_LOG_SKIP = new Set(['play_viseme_sequence', 'set_expression', 'clear_expressions', 'status']);
const CMD_LOG_MAX = 40;
const _cmdLogEl = document.getElementById('cmd-log');
let _cmdFadeTimer = null;
function _cmdSanitize(key, val) {
    if (/token|key|secret|auth|password|cookie|bearer|credential/i.test(key)) return '***';
    if (typeof val === 'string') {
        let s = val;
        // Never surface our host/IP — show the stable server id "playaides".
        if (/^https?:\/\//i.test(s)) { try { const u = new URL(s); s = 'playaides' + u.pathname; } catch (_) { /* leave as-is */ } }
        s = s.replace(/\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b/g, 'playaides');
        return s.length > 60 ? s.slice(0, 57) + '…' : s;
    }
    if (Array.isArray(val)) return `[${val.length}]`;
    if (val && typeof val === 'object') return '{…}';
    return String(val);
}
function _cmdSummary(payload) {
    if (!payload || typeof payload !== 'object') return '';
    return Object.entries(payload).slice(0, 4).map(([k, v]) => `${k}=${_cmdSanitize(k, v)}`).join('  ');
}
function pushCmdLog(msg) {
    if (!_cmdLogEl || !msg || !msg.type || CMD_LOG_SKIP.has(msg.type)) return;
    const line = document.createElement('div');
    line.className = 'cmd-line';
    const t = document.createElement('span'); t.className = 'cmd-t'; t.textContent = new Date().toTimeString().slice(0, 8);
    const ty = document.createElement('span'); ty.className = 'cmd-type'; ty.textContent = msg.type;
    const sm = document.createElement('span'); sm.className = 'cmd-sum'; sm.textContent = _cmdSummary(msg.payload);
    line.append(t, ty, sm);
    _cmdLogEl.appendChild(line);
    while (_cmdLogEl.children.length > CMD_LOG_MAX) _cmdLogEl.removeChild(_cmdLogEl.firstChild);
    _cmdLogEl.scrollTop = _cmdLogEl.scrollHeight;
    // Fade out like the subtitles after a few idle seconds.
    _cmdLogEl.classList.remove('faded');
    clearTimeout(_cmdFadeTimer);
    _cmdFadeTimer = setTimeout(() => _cmdLogEl.classList.add('faded'), 8000);
}
// Command log is opt-out via ?cmdlog=0 — hidden + unwired when disabled.
if (config.cmdLog && _cmdLogEl) {
    _cmdLogEl.classList.add('faded');   // start hidden until the first command
    connection.addEventListener('message', (e) => pushCmdLog(e.detail));
} else {
    document.body.classList.add('cmdlog-off');
}

// Pending text from the most recent assistant_message event — attached
// to the next SPEAKING transition so the subtitle band can render.
let pendingAssistantText = '';

// Holds the most recent history_loaded payload until persona_active has
// landed and we know the persona's name to tag assistant lines with.
let pendingHistory = null;

function _flushPendingHistory() {
    if (!pendingHistory || !activePersona.name) return;
    const tagged = pendingHistory.map((m) => ({
        ...m,
        persona_name: activePersona.name,
    }));
    transcriptModel.replaceAll(tagged);
    console.log('[viewer] transcript rehydrated, n=', tagged.length);
    pendingHistory = null;
}

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

/** Resolve the active persona's id from the registry by name match.
 *  Returns null if the registry isn't populated yet or the active
 *  persona's name doesn't match any known id. */
function getActivePersonaId() {
    return personasRegistry.all()
        .find((p) => p.name === activePersona.name)?.id || null;
}

stateMachine.addEventListener('change', (e) => {
    const next = e.detail.next;
    if (next === State.SPEAKING) {
        chatPanel.setInputEnabled(false);
    } else if (next === State.AMBIENT || next === State.EMPTY) {
        chatPanel.setInputEnabled(true);
    }
});

// ── WebSocket-driven transitions ────────────────────────────────────────────
connection.addEventListener('load_model', async (e) => {
    try {
        const info = await incarnation.handleCommand('load_model', withResolvedUrl(e.detail));
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
    const info = await incarnation.handleCommand('load_animation', withResolvedUrl(e.detail));
    connection.send('status', { state: 'animation_loaded', ...info });
});
connection.addEventListener('load_mixamo_animation', async (e) => {
    const info = await incarnation.handleCommand('load_mixamo_animation', withResolvedUrl(e.detail));
    connection.send('status', { state: 'animation_loaded', ...info });
});
connection.addEventListener('load_vrma_animation', async (e) => {
    const info = await incarnation.handleCommand('load_vrma_animation', withResolvedUrl(e.detail));
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
    if (pendingAssistantText) {
        transcriptModel.append({
            role: 'assistant',
            content: pendingAssistantText,
            persona_name: activePersona.name,
        });
    }
});

connection.addEventListener('history_loaded', (e) => {
    const history = Array.isArray(e.detail?.history) ? e.detail.history : [];
    pendingHistory = history;
    _flushPendingHistory();
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
    // The backend builds this audio URL with a hardcoded localhost:8765 origin
    // (playAIdes.speak_as_persona); rewrite localhost → apiBase so it resolves to
    // the serving host from a remote display (e.g. the Firestick), the same way
    // load_model/animation asset URLs are normalized above.
    incarnation.handleCommand('start_lip_sync', withResolvedUrl(e.detail));
});

connection.addEventListener('stop_lip_sync', () => {
    incarnation.handleCommand('stop_lip_sync', {});
    safeTransition(State.AMBIENT);
});

connection.addEventListener('show_pip', (e) => {
    // Camera shows as a comic-panel PiP on the left; body[data-pip] slides Silver
    // to the right (CSS). URL normalized so localhost feeds resolve on remote TVs.
    // The full screen split is reserved for the future multi-3D-model cast.
    const view = pipViewFromMessage('show_pip', withResolvedUrl(e.detail || {}));
    pip.apply(view);
    document.body.dataset.pip = view.visible ? 'on' : 'off';
});
connection.addEventListener('dismiss_pip', () => {
    pip.apply(pipViewFromMessage('dismiss_pip', {}));
    document.body.dataset.pip = 'off';
});

connection.addEventListener('persona_active', (e) => {
    activePersona = {
        name: e.detail?.name || '',
        wake_words: Array.isArray(e.detail?.wake_words) ? e.detail.wake_words : [],
        dismiss_words: Array.isArray(e.detail?.dismiss_words) ? e.detail.dismiss_words : [],
    };
    // A persona may carry its own look; apply it if present (server payload
    // extension — absent today, so this is a no-op until wired server-side).
    if (e.detail?.theme) document.body.dataset.theme = e.detail.theme;
    overlays.setPersonaName(activePersona.name);
    // Update p5-basic dialogue nametag.
    const nametag = document.querySelector('.console-nametag-text');
    if (nametag && activePersona.name) nametag.textContent = activePersona.name.toUpperCase();
    chatPanel.setPersona(
        activePersona.name,
        (activePersona.wake_words && activePersona.wake_words[0]) || '',
    );
    _flushPendingHistory();
    console.log('[viewer] persona_active:', activePersona);
});

connection.addEventListener('persona_changed', async (e) => {
    const ok = e.detail?.ok;
    if (!ok) {
        console.warn('[viewer] persona_changed error:', e.detail?.error);
        return;
    }
    const persona = e.detail?.persona;
    if (!persona) return;

    // If the new persona's id matches the currently-bound activePersona,
    // it's an idempotent swap — no wipe / unload needed.
    if (persona.name === activePersona.name) {
        console.log('[viewer] persona_changed (same persona, no wipe)');
        return;
    }

    console.log('[viewer] persona_changed → swap:', persona.name);
    if (persona) {
        chatPanel.setPersona(
            persona.name,
            (Array.isArray(persona.wake_words) && persona.wake_words[0]) || '',
        );
        // Persona swap → fresh transcript (history_loaded will rehydrate).
        transcriptModel.clear();
    }
    // Visual: kick off the wipe; in parallel the server will emit
    // unload_model + load_model. The wipe is purely cosmetic — the
    // unload/load handlers fire whenever they arrive on the WS.
    wipeOverlay.play();
});

connection.addEventListener('unload_model', () => {
    incarnation.handleCommand('unload_model', {});
    safeTransition(State.EMPTY);
});

// On WS connect, request the personas list so the registry can drive
// cross-persona wake matching.
connection.addEventListener('connected', () => {
    connection.send('get_personas', {});
});

connection.addEventListener('personas_list', (e) => {
    personasRegistry.replaceAll(e.detail?.personas || []);
    console.log('[viewer] personas_list:', personasRegistry.all().map((p) => p.id));

    // Boot resolution: honor ?persona= URL param if it matches a known id;
    // else fall back to the registry's default; else do nothing (server
    // stays on whatever --persona it was launched with).
    const wanted = config.persona && personasRegistry.get(config.persona)
        ? personasRegistry.get(config.persona)
        : personasRegistry.findDefault();
    if (wanted && wanted.id) {
        console.log('[viewer] boot persona:', wanted.id);
        connection.send('set_active_persona', { id: wanted.id });
    }
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
    console.log('[viewer] voicestart in state:', stateMachine.current);
    if (stateMachine.current === State.AMBIENT) {
        safeTransition(State.LISTENING);
    }
});

/**
 * Refresh the THINKING-state subtitle text without changing state.
 * The state machine forbids same-state transitions by design, so we
 * fan out a synthetic `change` event that the overlay layer renders.
 * This is what lets the user SEE what Whisper heard before any
 * dismiss/wake routing decision drops the utterance.
 */
function refreshThinkingMeta(text) {
    if (stateMachine.current !== State.THINKING) return;
    stateMachine.updateMeta({ lastUtterance: text });
}

audioCapture.addEventListener('voiceend', async (e) => {
    const wasListening = stateMachine.current === State.LISTENING;
    const blob = e.detail?.blob;
    const peakEnergy = e.detail?.peakEnergy ?? 0;
    console.log(
        '[viewer] voiceend: blob',
        blob ? `${blob.size} bytes (${blob.type})` : 'MISSING',
        '| peak energy:', peakEnergy.toFixed(3),
        '| state:', stateMachine.current,
    );
    if (wasListening) {
        safeTransition(State.THINKING, { lastUtterance: '…' });
    }
    try {
        const sttStart = performance.now();
        const stt_response = await stt.transcribe(blob);
        const sttElapsed = Math.round(performance.now() - sttStart);
        const transcript = (stt_response.text || '').trim();
        // Show every STT result regardless of whether it'll match a wake/dismiss
        // word — diagnoses both "Whisper heard nothing" and "Whisper heard it
        // but my wake_words don't match" cases.
        console.log(
            '[viewer] STT (%dms): language=%s text=%o',
            sttElapsed,
            stt_response.language || '?',
            transcript || '(empty)',
        );

        if (!transcript) {
            if (wasListening) safeTransition(State.AMBIENT);
            return;
        }

        // Render the heard transcript in the subtitle band immediately, BEFORE
        // any routing decision. Dropped utterances will fade out a few seconds
        // later via the AMBIENT-state fade timer; matched utterances will get
        // their meta refreshed again with the residual just before send.
        refreshThinkingMeta(transcript);

        // 1. Dismiss check — always runs, regardless of activation mode.
        if (activePersona.dismiss_words.length) {
            const dismiss = matchPhrase(transcript, activePersona.dismiss_words);
            if (dismiss.matched) {
                console.log('[viewer] dismiss matched:', dismiss.phrase);
                // If we're already in EMPTY, safeTransition catches the
                // illegal EMPTY→EMPTY and warns; the dismiss is then a no-op.
                safeTransition(State.EMPTY);
                return;
            }
        }

        // 2. Wake-word gate — applied in `wake` mode OR when in EMPTY.
        let userInput = transcript;
        const inEmpty = stateMachine.current === State.EMPTY;
        const needsWake = config.activation === 'wake' || inEmpty;

        if (needsWake) {
            // Cross-persona wake: match against ALL known personas, not just
            // the active one. A hit on a different persona triggers a swap.
            const activeId = getActivePersonaId();
            const hit = personasRegistry.findByWakeWord(transcript, activeId);
            if (!hit) {
                console.log('[viewer] wake-mode drop, no wake-word in:', transcript);
                if (wasListening || stateMachine.current === State.THINKING) {
                    safeTransition(State.AMBIENT);
                }
                return;
            }
            userInput = hit.residual;
            console.log(
                '[viewer] wake matched:', hit.phrase,
                '→ persona:', hit.persona.id,
                '→ residual:', userInput || '(empty)',
            );

            // If the matched persona is NOT the currently-active one, fire a
            // server-side swap. The server's persona_changed handler kicks
            // off unload→load via the existing handlers (Task 10).
            const matchedId = hit.persona.id;
            if (matchedId !== activeId) {
                connection.send('set_active_persona', { id: matchedId });
                // The user_input below will route to the new persona; tag it
                // explicitly with the matched id so the server doesn't
                // accidentally route it to the previous active.
                if (userInput) {
                    transcriptModel.append({ role: 'user', content: userInput });
                    connection.send('user_input', {
                        text: userInput, persona_id: matchedId,
                    });
                }
                lastUserUtterance = userInput;
                return;   // server handles the rest
            }
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

        // 5. Refresh THINKING meta with the residual (now that the wake word
        // has been stripped) and forward to the LLM.
        refreshThinkingMeta(userInput);
        lastUserUtterance = userInput;
        transcriptModel.append({ role: 'user', content: userInput });
        connection.send('user_input', { text: userInput });
        console.log('[viewer] user_input sent:', userInput);
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
    // Types with dedicated listeners above are excluded here so they aren't
    // double-dispatched into incarnation.handleCommand. Don't add a type here
    // without a corresponding dedicated listener.
    if (msg.type
        && !msg.type.startsWith('load_')
        && msg.type !== 'play_animation'
        && msg.type !== 'start_lip_sync'
        && msg.type !== 'stop_lip_sync'
        && msg.type !== 'assistant_message'
        && msg.type !== 'show_pip'
        && msg.type !== 'dismiss_pip') {
        incarnation.handleCommand(msg.type, withResolvedUrl(msg.payload || {}));
    }
});

// ── Kiosk display: best-effort keep-awake + fullscreen ───────────────────────
// Both need a user gesture, so they ride on the first-gesture unlockAudio()
// below. A kiosk-browser app (e.g. Fully Kiosk) is the robust path for an
// always-on TV; this is the no-extra-software fallback and degrades silently
// where the APIs are missing (Fire TV Silk may not implement them).
let _wakeLock = null;
async function requestWakeLock() {
    try {
        if ('wakeLock' in navigator) {
            _wakeLock = await navigator.wakeLock.request('screen');
            _wakeLock.addEventListener('release', () => { _wakeLock = null; });
        }
    } catch (err) {
        console.warn('[viewer] screen wake lock unavailable:', err?.message || err);
    }
}
function enterFullscreen() {
    const el = document.documentElement;
    const req = el.requestFullscreen || el.webkitRequestFullscreen;
    if (!req) return;
    try {
        const p = req.call(el);
        if (p && typeof p.catch === 'function') p.catch(() => { /* agent declined */ });
    } catch (_) { /* agent declined */ }
}
if (config.kiosk) {
    // The OS drops a screen wake lock when the tab is hidden; re-acquire it
    // when the page becomes visible again.
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') requestWakeLock();
    });
}

// ── Audio Unlock ────────────────────────────────────────────────────────────
// First user gesture resumes AudioContext — same pattern as the previous
// main.js. Phase 2 will replace the listener-list with a richer mic flow.
const GESTURES = ['click', 'keydown', 'touchstart', 'pointerdown'];
async function unlockAudio() {
    GESTURES.forEach((t) => window.removeEventListener(t, unlockAudio, true));
    if (incarnation.lipSyncManager) {
        await incarnation.lipSyncManager.resume();
    }
    if (config.kiosk) {
        // The first gesture is our only chance to claim these (browser policy).
        enterFullscreen();
        requestWakeLock();
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
    if (cameraDirector.active) {
        // Director owns the camera in kiosk mode: pick a shot from scene state
        // (idle → bust, one-shot animation → full body) and ease toward it.
        cameraDirector.setSceneState({
            model: incarnation.model,
            animating: incarnation.isPlayingOneShot,
            characterCount: incarnation.isLoaded ? 1 : 0,
        });
        cameraDirector.update();
    } else {
        controls.update();
    }
    incarnation.update(dt);
    renderer.render(scene, camera);
}

// ── Connect + start ─────────────────────────────────────────────────────────
connection.connect(config.wsUrl);
tick();
console.log('[viewer] started — ws:', config.wsUrl);
