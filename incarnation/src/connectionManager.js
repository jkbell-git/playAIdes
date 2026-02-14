/**
 * ConnectionManager — WebSocket client for communicating with PlayAIdes.
 *
 * Protocol (JSON messages):
 *   Inbound (from PlayAIdes):
 *     { type: "load_model",          payload: { url: string } }
 *     { type: "load_animation",      payload: { url: string, name?: string } }
 *     { type: "play_animation",      payload: { name: string, loop?: boolean, crossFade?: number } }
 *     { type: "set_expression",      payload: { expressions: Record<string, number> } }
 *     { type: "play_viseme_sequence", payload: { sequence: {viseme,weight,time}[] } }
 *     { type: "stop_animation" }
 *     { type: "clear_expressions" }
 *
 *   Outbound (to PlayAIdes):
 *     { type: "status", payload: { state: "ready"|"model_loaded"|"error", ... } }
 *
 * Future: multi-persona routing via a `personaId` field.
 */
export class ConnectionManager extends EventTarget {
    /**
     * @param {string} [url]  WebSocket URL, e.g. "ws://localhost:8765"
     */
    constructor(url) {
        super();
        /** @type {WebSocket|null} */
        this.ws = null;
        this.url = url || null;
        this._reconnectTimer = null;
        this._reconnectDelay = 2000; // ms
    }

    // ── Connection lifecycle ────────────────────────────────────────────────

    /**
     * Open a WebSocket connection.
     * @param {string} [url]  Override the URL set in the constructor.
     */
    connect(url) {
        if (url) this.url = url;
        if (!this.url) {
            console.warn('[ConnectionManager] No URL provided');
            return;
        }

        this._clearReconnect();

        try {
            this.ws = new WebSocket(this.url);
        } catch (err) {
            console.error('[ConnectionManager] Failed to create WebSocket:', err);
            this._scheduleReconnect();
            return;
        }

        this.ws.addEventListener('open', () => {
            console.log('[ConnectionManager] Connected to', this.url);
            this._emit('connected');
            this.send('status', { state: 'ready' });
        });

        this.ws.addEventListener('message', (event) => {
            try {
                const msg = JSON.parse(event.data);
                this._emit('message', msg);

                // Also emit typed events: e.g. "load_model", "set_expression"
                if (msg.type) {
                    this._emit(msg.type, msg.payload || {});
                }
            } catch (err) {
                console.warn('[ConnectionManager] Bad message:', event.data, err);
            }
        });

        this.ws.addEventListener('close', () => {
            console.log('[ConnectionManager] Disconnected');
            this._emit('disconnected');
            this._scheduleReconnect();
        });

        this.ws.addEventListener('error', (err) => {
            console.error('[ConnectionManager] Error:', err);
            this._emit('error', err);
        });
    }

    /** Gracefully close the connection. */
    disconnect() {
        this._clearReconnect();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    // ── Sending ─────────────────────────────────────────────────────────────

    /**
     * Send a JSON message to PlayAIdes.
     * @param {string} type
     * @param {object} [payload]
     */
    send(type, payload = {}) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('[ConnectionManager] Not connected, cannot send:', type);
            return;
        }
        this.ws.send(JSON.stringify({ type, payload }));
    }

    // ── Internal helpers ────────────────────────────────────────────────────

    /** @private */
    _emit(name, detail) {
        this.dispatchEvent(new CustomEvent(name, { detail }));
    }

    /** @private */
    _scheduleReconnect() {
        this._clearReconnect();
        this._reconnectTimer = setTimeout(() => {
            console.log('[ConnectionManager] Attempting reconnect…');
            this.connect();
        }, this._reconnectDelay);
    }

    /** @private */
    _clearReconnect() {
        if (this._reconnectTimer !== null) {
            clearTimeout(this._reconnectTimer);
            this._reconnectTimer = null;
        }
    }
}
