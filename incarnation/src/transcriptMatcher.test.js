import { describe, it, expect } from 'vitest';
import { matchPhrase } from './transcriptMatcher.js';

describe('matchPhrase', () => {
    it('returns no match for empty transcript', () => {
        const r = matchPhrase('', ['hey silver']);
        expect(r.matched).toBe(false);
        expect(r.phrase).toBe(null);
        expect(r.residual).toBe('');
    });

    it('returns no match for null/empty phrases', () => {
        expect(matchPhrase('hello', null).matched).toBe(false);
        expect(matchPhrase('hello', []).matched).toBe(false);
        expect(matchPhrase('hello', null).residual).toBe('hello');
    });

    it('matches case-insensitively and reports the matched phrase lowercased', () => {
        const r = matchPhrase('Hey Silver, what time is it?', ['hey silver']);
        expect(r.matched).toBe(true);
        expect(r.phrase).toBe('hey silver');
    });

    it('strips the matched phrase from residual and trims whitespace', () => {
        const r = matchPhrase('Hey Silver, what time is it?', ['hey silver']);
        expect(r.residual).toBe(', what time is it?');
    });

    it('returns empty residual when transcript IS the wake word', () => {
        const r = matchPhrase('Silver', ['silver']);
        expect(r.matched).toBe(true);
        expect(r.residual).toBe('');
    });

    it('matches the LONGEST phrase first to avoid shorter alias winning', () => {
        // If "silver" matched first, residual would be "hey , how are you"; we want
        // "hey silver" to win and residual to be "how are you" (with trailing comma stripped).
        const r = matchPhrase('Hey Silver, how are you', ['silver', 'hey silver']);
        expect(r.matched).toBe(true);
        expect(r.phrase).toBe('hey silver');
        expect(r.residual).toBe(', how are you');
    });

    it('matches Japanese substrings without tokenization', () => {
        const r = matchPhrase('こんにちはシルバー、今何時ですか', ['シルバー']);
        expect(r.matched).toBe(true);
        expect(r.phrase).toBe('シルバー');
        expect(r.residual).toBe('こんにちは、今何時ですか');
    });

    it('returns no match when no phrase appears in transcript', () => {
        const r = matchPhrase('hello there', ['hey silver', 'goodnight']);
        expect(r.matched).toBe(false);
        expect(r.phrase).toBe(null);
        expect(r.residual).toBe('hello there');
    });

    it('collapses internal whitespace runs in residual', () => {
        const r = matchPhrase('Hey   Silver   what  time', ['silver']);
        expect(r.matched).toBe(true);
        expect(r.residual).toBe('Hey what time');
    });

    it('treats undefined phrases array safely', () => {
        const r = matchPhrase('hello', undefined);
        expect(r.matched).toBe(false);
        expect(r.residual).toBe('hello');
    });
});
