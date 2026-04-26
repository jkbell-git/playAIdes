/**
 * personasRegistry.js — browser-side cache of all personas.
 *
 * Populated at boot by fetching the personas list from the server.
 * Used by the orchestrator's voiceend handler to detect cross-persona
 * wake words ("Hey Rin" while Silver is active should fire a swap).
 */

import { matchPhrase } from './transcriptMatcher.js';

export class PersonasRegistry {
    constructor() {
        this._byId = new Map();
    }

    /** Replace the cache with a fresh list (server pushed). */
    replaceAll(personas) {
        this._byId.clear();
        for (const p of personas || []) {
            if (p && p.id) this._byId.set(p.id, p);
        }
    }

    /** Get a persona by id, or undefined. */
    get(id) {
        return this._byId.get(id);
    }

    /** All personas as an array, in insertion order. */
    all() {
        return Array.from(this._byId.values());
    }

    /**
     * Pick the boot persona:
     *   - Persona with is_default: true, if any.
     *   - Else first alphabetically (by id).
     *   - Else null when the registry is empty.
     */
    findDefault() {
        const all = this.all();
        if (!all.length) return null;
        const explicit = all.find((p) => p.is_default === true);
        if (explicit) return explicit;
        return [...all].sort((a, b) => (a.id || '').localeCompare(b.id || ''))[0];
    }

    /**
     * Find which persona's wake word(s) appear in a transcript.
     * Active persona is preferred on overlap (so saying the active
     * persona's name doesn't accidentally match a different persona
     * that shares an alias).
     *
     * @param {string} transcript
     * @param {string|null} activeId — id of the currently-active persona
     * @returns {{persona, phrase, residual}|null}
     */
    findByWakeWord(transcript, activeId) {
        if (!transcript) return null;
        // Try the active persona first.
        if (activeId) {
            const active = this.get(activeId);
            if (active) {
                const m = matchPhrase(transcript, active.wake_words);
                if (m.matched) {
                    return { persona: active, phrase: m.phrase, residual: m.residual };
                }
            }
        }
        // Then try every other persona.
        for (const persona of this.all()) {
            if (persona.id === activeId) continue;
            const m = matchPhrase(transcript, persona.wake_words);
            if (m.matched) {
                return { persona, phrase: m.phrase, residual: m.residual };
            }
        }
        return null;
    }
}
