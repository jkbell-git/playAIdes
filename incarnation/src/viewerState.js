/**
 * viewerState.js — the viewer's UI state machine.
 *
 * States (per spec §2):
 *   EMPTY      — no persona on screen, mic still listening (phase 4)
 *   INTRO      — persona just loaded, intro animation playing
 *   AMBIENT    — persona idling, waiting for input
 *   LISTENING  — capturing user audio (phase 2)
 *   THINKING   — STT + LLM round-trip in flight (phase 2)
 *   SPEAKING   — TTS audio playing + lip sync
 *
 * Phase 1 only reachable states are INTRO, AMBIENT, SPEAKING. The other
 * three are scaffolded so phases 2–4 can wire them without changing
 * the contract.
 *
 * This module deliberately holds no DOM references. Subscribers
 * (overlays, orchestrator) listen on the EventTarget for `change`.
 */

export const State = Object.freeze({
    EMPTY:     'EMPTY',
    INTRO:     'INTRO',
    AMBIENT:   'AMBIENT',
    LISTENING: 'LISTENING',
    THINKING:  'THINKING',
    SPEAKING:  'SPEAKING',
});

/** Allowed transitions per the state diagram in spec §2. */
const TRANSITIONS = {
    EMPTY:     ['INTRO'],                        // wake-word summon (phase 4)
    INTRO:     ['AMBIENT', 'EMPTY'],             // intro anim ends → AMBIENT
    AMBIENT:   ['LISTENING', 'SPEAKING', 'EMPTY', 'INTRO'],
    LISTENING: ['THINKING', 'AMBIENT', 'EMPTY'],
    THINKING:  ['SPEAKING', 'AMBIENT', 'EMPTY'], // AMBIENT on STT failure
    SPEAKING:  ['AMBIENT', 'EMPTY'],             // audio ends → AMBIENT
};

export class ViewerState extends EventTarget {
    /** @param {string} initial — one of the State constants */
    constructor(initial = State.EMPTY) {
        super();
        if (!Object.values(State).includes(initial)) {
            throw new Error(`ViewerState: invalid initial state "${initial}"`);
        }
        this._state = initial;
        /** @type {object|null} arbitrary metadata attached to the current state */
        this._meta = null;
    }

    /** Current state name. */
    get current() { return this._state; }

    /** Metadata attached to the current state (e.g. last assistant message text). */
    get meta() { return this._meta; }

    /**
     * Attempt to transition to a new state. Throws on illegal transitions.
     * @param {string} next — target state (use the State constants)
     * @param {object} [meta] — optional metadata, available on the next state
     */
    transition(next, meta = null) {
        if (!Object.values(State).includes(next)) {
            throw new Error(`ViewerState: invalid target state "${next}"`);
        }
        const allowed = TRANSITIONS[this._state] || [];
        if (!allowed.includes(next)) {
            // Illegal transitions are a programming error — fail loud rather
            // than silently corrupting state.
            throw new Error(
                `ViewerState: illegal transition ${this._state} → ${next}`
            );
        }
        const prev = this._state;
        const prevMeta = this._meta;
        this._state = next;
        this._meta = meta;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { prev, next, prevMeta, meta },
        }));
    }
}
