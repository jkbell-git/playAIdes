/**
 * transcriptMatcher.js — case-insensitive substring matcher for
 * wake-word and dismiss-word detection.
 *
 * No tokenization, no language-aware splitting — Whisper produces
 * mixed EN/JP transcripts that work fine as raw substrings since
 * we lowercase them and the wake/dismiss config is also case-insensitive.
 *
 * Longest-first ordering ensures that e.g. ["silver", "hey silver"]
 * matches "Hey Silver" against "hey silver" (the longer alias) rather
 * than "silver" — preserving more of the residual.
 */

/**
 * Test whether a transcript contains any of the given phrases.
 *
 * @param {string} transcript
 * @param {string[]|null|undefined} phrases
 * @returns {{matched: boolean, phrase: string|null, residual: string}}
 *   matched  — true if any phrase appears in transcript
 *   phrase   — the matched phrase (lowercased), or null
 *   residual — transcript with the matched phrase removed and internal
 *              whitespace collapsed; equals the input transcript when
 *              no phrase matched
 */
export function matchPhrase(transcript, phrases) {
    const safeTranscript = transcript || '';
    if (!phrases || !Array.isArray(phrases) || phrases.length === 0) {
        return { matched: false, phrase: null, residual: safeTranscript };
    }
    if (!safeTranscript) {
        return { matched: false, phrase: null, residual: '' };
    }
    const lower = safeTranscript.toLowerCase();
    // Longest-first: avoids "silver" winning when "hey silver" is also configured.
    const sorted = phrases
        .filter((p) => typeof p === 'string' && p.length > 0)
        .map((p) => p.toLowerCase())
        .sort((a, b) => b.length - a.length);

    for (const phrase of sorted) {
        const idx = lower.indexOf(phrase);
        if (idx !== -1) {
            const residual = (
                safeTranscript.slice(0, idx) +
                safeTranscript.slice(idx + phrase.length)
            )
                .replace(/\s+/g, ' ')
                .trim();
            return { matched: true, phrase, residual };
        }
    }
    return { matched: false, phrase: null, residual: safeTranscript };
}
