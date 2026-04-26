import { describe, it, expect } from 'vitest';
import { TranscriptModel } from './transcriptModel.js';

describe('TranscriptModel', () => {
    it('starts empty', () => {
        const t = new TranscriptModel();
        expect(t.messages).toEqual([]);
    });

    it('append adds a message and emits a change event', () => {
        const t = new TranscriptModel();
        const events = [];
        t.addEventListener('change', (e) => events.push(e.detail));
        t.append({ role: 'user', content: 'hi' });
        expect(t.messages).toEqual([{ role: 'user', content: 'hi' }]);
        expect(events).toHaveLength(1);
        expect(events[0].kind).toBe('append');
        expect(events[0].message).toEqual({ role: 'user', content: 'hi' });
    });

    it('replaceAll swaps the list and emits a change event', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'old' });
        const events = [];
        t.addEventListener('change', (e) => events.push(e.detail));
        t.replaceAll([
            { role: 'user', content: 'a' },
            { role: 'assistant', content: 'b' },
        ]);
        expect(t.messages).toEqual([
            { role: 'user', content: 'a' },
            { role: 'assistant', content: 'b' },
        ]);
        expect(events[0].kind).toBe('replaceAll');
    });

    it('clear empties the list and emits change', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'x' });
        const events = [];
        t.addEventListener('change', (e) => events.push(e.detail));
        t.clear();
        expect(t.messages).toEqual([]);
        expect(events[0].kind).toBe('clear');
    });

    it('shouldAutoScrollToBottom is true at construction (user hasn\'t scrolled up)', () => {
        const t = new TranscriptModel();
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });

    it('shouldAutoScrollToBottom flips to false after setUserScrolledUp(true)', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        expect(t.shouldAutoScrollToBottom()).toBe(false);
    });

    it('shouldAutoScrollToBottom flips back to true after setUserScrolledUp(false)', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        t.setUserScrolledUp(false);
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });

    it('append while frozen does NOT change the auto-scroll flag', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        t.append({ role: 'assistant', content: 'new line' });
        expect(t.shouldAutoScrollToBottom()).toBe(false);
    });

    it('replaceAll resets to auto-scroll (e.g. after persona swap rehydrate)', () => {
        const t = new TranscriptModel();
        t.setUserScrolledUp(true);
        t.replaceAll([{ role: 'user', content: 'a' }]);
        expect(t.shouldAutoScrollToBottom()).toBe(true);
    });

    it('messages getter returns a defensive copy', () => {
        const t = new TranscriptModel();
        t.append({ role: 'user', content: 'a' });
        const msgs = t.messages;
        msgs.push({ role: 'assistant', content: 'b' });
        // Internal list is unchanged; getter returned a copy.
        expect(t.messages).toEqual([{ role: 'user', content: 'a' }]);
    });
});
