/**
 * transcriptModel.js — pure transcript state + Discord/Slack-style
 * auto-scroll heuristic.
 *
 * Owns the list of messages displayed in the chat panel and a single
 * "user has scrolled up" flag. The DOM layer (ChatPanel) calls
 * setUserScrolledUp(true) when the user scrolls away from the bottom
 * and false when they return; it consults shouldAutoScrollToBottom()
 * before each render to decide whether to snap to bottom.
 *
 * No DOM references — fully Vitest-testable.
 */
export class TranscriptModel extends EventTarget {
    constructor() {
        super();
        this._messages = [];
        this._userScrolledUp = false;
    }

    /** Defensive copy of the message list. */
    get messages() {
        return this._messages.slice();
    }

    /** Append a single message and emit `change`. */
    append(message) {
        this._messages.push(message);
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'append', message },
        }));
    }

    /** Replace the entire list (e.g. after history_loaded) and reset
     *  the user-scrolled-up flag (a fresh persona's transcript should
     *  always start at the bottom). Emits `change`. */
    replaceAll(messages) {
        this._messages = (messages || []).slice();
        this._userScrolledUp = false;
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'replaceAll', messages: this.messages },
        }));
    }

    /** Empty the list (e.g. on persona dismiss). Emits `change`. */
    clear() {
        this._messages = [];
        this.dispatchEvent(new CustomEvent('change', {
            detail: { kind: 'clear' },
        }));
    }

    /** DOM layer reports whether the user has scrolled up away from
     *  the bottom. Append while flagged stays put (Slack/Discord). */
    setUserScrolledUp(flag) {
        this._userScrolledUp = !!flag;
    }

    /** Whether the next render should snap to bottom. */
    shouldAutoScrollToBottom() {
        return !this._userScrolledUp;
    }
}
