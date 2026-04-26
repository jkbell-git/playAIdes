/**
 * chatPanel.js — DOM rendering for the right-edge collapsible chat panel.
 *
 * Subscribes to a TranscriptModel for message updates, renders user /
 * assistant transcript items, manages the open/closed state, and exposes
 * a typed-input event the orchestrator listens to so it can forward the
 * text as a `user_input` WS frame (skipping STT).
 *
 * State pip rendering during LISTENING / THINKING / SPEAKING is the
 * orchestrator's job — it calls setLiveState(state) which classifies the
 * tail item.
 */
export class ChatPanel extends EventTarget {
    /**
     * @param {object} root         DOM root containing the panel elements
     * @param {TranscriptModel} model
     * @param {object} options      { initialOpen?: boolean }
     */
    constructor(root, model, options = {}) {
        super();
        this.root = root;
        this.model = model;

        this.elPanel       = root.querySelector('#chat-panel');
        this.elHandle      = root.querySelector('#chat-panel-handle');
        this.elName        = root.querySelector('#chat-panel-name');
        this.elWake        = root.querySelector('#chat-panel-wake');
        this.elTranscript  = root.querySelector('#chat-panel-transcript');
        this.elForm        = root.querySelector('#chat-panel-input-row');
        this.elInput       = root.querySelector('#chat-panel-input');
        this.elSend        = root.querySelector('#chat-panel-send');

        this._open = false;
        if (options.initialOpen) this.open();

        this.elHandle?.addEventListener('click', () => this.toggle());
        this.elForm?.addEventListener('submit', (e) => this._onSubmit(e));
        this.elTranscript?.addEventListener('scroll', () => this._onScroll());

        this.model.addEventListener('change', () => this._render());
        this._render();
    }

    open() {
        this._open = true;
        this.elPanel?.classList.add('open');
        this.elPanel?.setAttribute('aria-hidden', 'false');
        if (document?.body) document.body.dataset.chatOpen = 'true';
        // Snap to bottom on first open so the latest line is visible.
        requestAnimationFrame(() => {
            if (this.elTranscript) {
                this.elTranscript.scrollTop = this.elTranscript.scrollHeight;
            }
        });
    }

    close() {
        this._open = false;
        this.elPanel?.classList.remove('open');
        this.elPanel?.setAttribute('aria-hidden', 'true');
        if (document?.body) document.body.dataset.chatOpen = 'false';
    }

    toggle() {
        if (this._open) this.close(); else this.open();
    }

    isOpen() { return this._open; }

    /** Update header (called when persona_active / persona_changed arrives). */
    setPersona(name, primaryWakeWord = '') {
        if (this.elName) this.elName.textContent = name || '—';
        if (this.elWake) this.elWake.textContent = primaryWakeWord ? `· "${primaryWakeWord}"` : '';
    }

    /** Disable the input — e.g. during SPEAKING. */
    setInputEnabled(enabled) {
        if (this.elInput) this.elInput.disabled = !enabled;
        if (this.elSend) this.elSend.disabled = !enabled;
    }

    _onSubmit(e) {
        e.preventDefault();
        const text = (this.elInput?.value || '').trim();
        if (!text) return;
        this.elInput.value = '';
        this.dispatchEvent(new CustomEvent('submit', { detail: { text } }));
    }

    _onScroll() {
        if (!this.elTranscript) return;
        const distanceFromBottom = this.elTranscript.scrollHeight
            - this.elTranscript.scrollTop
            - this.elTranscript.clientHeight;
        // Tolerate a few px of jitter from sub-pixel layout.
        this.model.setUserScrolledUp(distanceFromBottom > 24);
    }

    _render() {
        if (!this.elTranscript) return;
        // Re-render full transcript on every change. Cheap for v1's expected
        // sizes (capped by CHAT_HISTORY_CAP=80 turns); revisit if profiling
        // shows scroll thrash.
        this.elTranscript.innerHTML = '';
        for (const msg of this.model.messages) {
            const item = document.createElement('div');
            item.className = `transcript-item ${msg.role}`;
            const label = document.createElement('div');
            label.className = 'label';
            label.textContent = msg.role === 'user' ? 'You' : (msg.persona_name || 'Persona');
            const body = document.createElement('div');
            body.className = 'body';
            body.textContent = msg.content;
            item.append(label, body);
            this.elTranscript.appendChild(item);
        }
        if (this.model.shouldAutoScrollToBottom()) {
            requestAnimationFrame(() => {
                this.elTranscript.scrollTop = this.elTranscript.scrollHeight;
            });
        }
    }
}
