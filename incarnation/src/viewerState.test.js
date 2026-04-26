import { describe, it, expect } from 'vitest';
import { State, ViewerState } from './viewerState.js';

describe('State enum', () => {
    it('exposes all six state names with matching string values', () => {
        expect(State.EMPTY).toBe('EMPTY');
        expect(State.INTRO).toBe('INTRO');
        expect(State.AMBIENT).toBe('AMBIENT');
        expect(State.LISTENING).toBe('LISTENING');
        expect(State.THINKING).toBe('THINKING');
        expect(State.SPEAKING).toBe('SPEAKING');
        expect(Object.keys(State)).toHaveLength(6);
    });

    it('is frozen so callers cannot mutate the enum', () => {
        expect(Object.isFrozen(State)).toBe(true);
    });
});

describe('ViewerState — construction', () => {
    it('defaults to EMPTY when no initial is given', () => {
        const sm = new ViewerState();
        expect(sm.current).toBe(State.EMPTY);
    });

    it('accepts a valid initial state', () => {
        const sm = new ViewerState(State.AMBIENT);
        expect(sm.current).toBe(State.AMBIENT);
    });

    it('throws on an invalid initial state', () => {
        expect(() => new ViewerState('FOO')).toThrow(/invalid initial state/);
    });

    it('starts with null meta', () => {
        const sm = new ViewerState(State.AMBIENT);
        expect(sm.meta).toBeNull();
    });
});

describe('ViewerState — legal transitions', () => {
    it('EMPTY → INTRO', () => {
        const sm = new ViewerState(State.EMPTY);
        sm.transition(State.INTRO);
        expect(sm.current).toBe(State.INTRO);
    });

    it('INTRO → AMBIENT', () => {
        const sm = new ViewerState(State.INTRO);
        sm.transition(State.AMBIENT);
        expect(sm.current).toBe(State.AMBIENT);
    });

    it('AMBIENT → LISTENING', () => {
        const sm = new ViewerState(State.AMBIENT);
        sm.transition(State.LISTENING);
        expect(sm.current).toBe(State.LISTENING);
    });

    it('AMBIENT → SPEAKING', () => {
        const sm = new ViewerState(State.AMBIENT);
        sm.transition(State.SPEAKING);
        expect(sm.current).toBe(State.SPEAKING);
    });

    it('LISTENING → THINKING', () => {
        const sm = new ViewerState(State.LISTENING);
        sm.transition(State.THINKING);
        expect(sm.current).toBe(State.THINKING);
    });

    it('THINKING → SPEAKING', () => {
        const sm = new ViewerState(State.THINKING);
        sm.transition(State.SPEAKING);
        expect(sm.current).toBe(State.SPEAKING);
    });

    it('SPEAKING → AMBIENT', () => {
        const sm = new ViewerState(State.SPEAKING);
        sm.transition(State.AMBIENT);
        expect(sm.current).toBe(State.AMBIENT);
    });

    it('every non-EMPTY state can dismiss to EMPTY', () => {
        for (const from of [State.INTRO, State.AMBIENT, State.LISTENING, State.THINKING, State.SPEAKING]) {
            const sm = new ViewerState(from);
            sm.transition(State.EMPTY);
            expect(sm.current).toBe(State.EMPTY);
        }
    });
});

describe('ViewerState — illegal transitions throw', () => {
    it('SPEAKING → INTRO throws with the illegal-transition message', () => {
        const sm = new ViewerState(State.SPEAKING);
        expect(() => sm.transition(State.INTRO)).toThrow(
            'ViewerState: illegal transition SPEAKING → INTRO'
        );
    });

    it('LISTENING → SPEAKING is illegal (must go through THINKING)', () => {
        const sm = new ViewerState(State.LISTENING);
        expect(() => sm.transition(State.SPEAKING)).toThrow(
            'ViewerState: illegal transition LISTENING → SPEAKING'
        );
    });

    it('EMPTY → AMBIENT is illegal (must go through INTRO)', () => {
        const sm = new ViewerState(State.EMPTY);
        expect(() => sm.transition(State.AMBIENT)).toThrow(
            'ViewerState: illegal transition EMPTY → AMBIENT'
        );
    });

    it('throws on an invalid target state name', () => {
        const sm = new ViewerState(State.AMBIENT);
        expect(() => sm.transition('FOO')).toThrow(/invalid target state/);
    });
});

describe('ViewerState — change event and metadata', () => {
    it('dispatches a change event with prev, next, prevMeta, meta', () => {
        const sm = new ViewerState(State.AMBIENT);
        const events = [];
        sm.addEventListener('change', (e) => events.push(e.detail));
        sm.transition(State.SPEAKING, { text: 'hi' });
        expect(events).toHaveLength(1);
        expect(events[0]).toEqual({
            prev: 'AMBIENT',
            next: 'SPEAKING',
            prevMeta: null,
            meta: { text: 'hi' },
        });
    });

    it('attaches metadata to the new state, visible via sm.meta', () => {
        const sm = new ViewerState(State.AMBIENT);
        sm.transition(State.SPEAKING, { text: 'hi' });
        expect(sm.meta).toEqual({ text: 'hi' });
    });

    it('carries the previous meta through the event detail on later transitions', () => {
        const sm = new ViewerState(State.AMBIENT);
        sm.transition(State.SPEAKING, { text: 'first' });
        let captured = null;
        sm.addEventListener('change', (e) => { captured = e.detail; });
        sm.transition(State.AMBIENT, { text: 'second' });
        expect(captured).toEqual({
            prev: 'SPEAKING',
            next: 'AMBIENT',
            prevMeta: { text: 'first' },
            meta: { text: 'second' },
        });
    });

    it('meta resets to null when no meta argument is given', () => {
        const sm = new ViewerState(State.AMBIENT);
        sm.transition(State.SPEAKING, { text: 'hi' });
        expect(sm.meta).toEqual({ text: 'hi' });
        sm.transition(State.AMBIENT);
        expect(sm.meta).toBeNull();
    });

    it('updateMeta refreshes meta + emits change without changing state', () => {
        const sm = new ViewerState(State.THINKING);
        const events = [];
        sm.addEventListener('change', (e) => events.push(e.detail));

        sm.updateMeta({ lastUtterance: 'hello world' });

        expect(sm.current).toBe(State.THINKING);
        expect(sm.meta).toEqual({ lastUtterance: 'hello world' });
        expect(events).toHaveLength(1);
        expect(events[0].prev).toBe(State.THINKING);
        expect(events[0].next).toBe(State.THINKING);
        expect(events[0].meta).toEqual({ lastUtterance: 'hello world' });
    });

    it('updateMeta accepts null and clears meta', () => {
        const sm = new ViewerState(State.THINKING);
        sm.updateMeta({ a: 1 });
        sm.updateMeta(null);
        expect(sm.meta).toBe(null);
    });
});
