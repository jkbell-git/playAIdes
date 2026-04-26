import { describe, it, expect } from 'vitest';
import { PersonasRegistry } from './personasRegistry.js';

const SILVER = {
    id: 'silver',
    name: 'Silver',
    wake_words: ['hey silver', 'silver'],
    dismiss_words: ['goodnight silver'],
    is_default: true,
};
const RIN = {
    id: 'rin',
    name: 'Rin',
    wake_words: ['hey rin', 'rin'],
    dismiss_words: ['goodnight rin'],
    is_default: false,
};

describe('PersonasRegistry', () => {
    it('starts empty', () => {
        const r = new PersonasRegistry();
        expect(r.all()).toEqual([]);
    });

    it('replaceAll loads a list', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        expect(r.all().map((p) => p.id)).toEqual(['silver', 'rin']);
        expect(r.get('silver')).toEqual(SILVER);
    });

    it('findDefault returns the persona with is_default true', () => {
        const r = new PersonasRegistry();
        r.replaceAll([RIN, SILVER]);
        expect(r.findDefault()?.id).toBe('silver');
    });

    it('findDefault returns first alphabetical when none flagged', () => {
        const r = new PersonasRegistry();
        r.replaceAll([
            { ...RIN, is_default: false },
            { ...SILVER, is_default: false, id: 'alice', name: 'Alice' },
        ]);
        expect(r.findDefault()?.id).toBe('alice');
    });

    it('findDefault returns null when registry empty', () => {
        const r = new PersonasRegistry();
        expect(r.findDefault()).toBe(null);
    });

    it('findByWakeWord matches active persona first when tied', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        // "hey silver" matches Silver's wake word.
        const hit = r.findByWakeWord('Hey Silver, what time is it?', 'rin');
        expect(hit.persona.id).toBe('silver');
    });

    it('findByWakeWord prefers active persona on overlap', () => {
        const r = new PersonasRegistry();
        // Both have the literal phrase "hello" as a wake word — active wins.
        r.replaceAll([
            { ...SILVER, wake_words: ['hello'] },
            { ...RIN, wake_words: ['hello'] },
        ]);
        const hit = r.findByWakeWord('hello', 'rin');
        expect(hit.persona.id).toBe('rin');
    });

    it('findByWakeWord returns null when nothing matches', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        const hit = r.findByWakeWord('what time is it', 'silver');
        expect(hit).toBe(null);
    });

    it('findByWakeWord includes residual + matched phrase', () => {
        const r = new PersonasRegistry();
        r.replaceAll([SILVER, RIN]);
        const hit = r.findByWakeWord('Hey Rin, where are you', 'silver');
        expect(hit.persona.id).toBe('rin');
        expect(hit.phrase).toBe('hey rin');
        expect(hit.residual).toBe(', where are you');
    });
});
