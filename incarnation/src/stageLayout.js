/**
 * stageLayout.js — chooses between the normal full-screen avatar and the
 * camera "split" (Silver left, live feed right, ink divider between).
 *
 * `stageLayoutFromMessage` is the pure decision function (unit-tested);
 * `StageLayout` is the thin DOM glue (untested, per repo convention — no
 * jsdom harness). Driven by the existing `show_pip` / `dismiss_pip` WS
 * messages, the same source the floating PiP listens to.
 */

/**
 * Pure: decide the stage layout from an inbound WS message.
 * @param {string} type                  'show_pip' | 'dismiss_pip' | other
 * @param {{url?:string,kind?:string}} payload
 * @param {{splitEnabled?:boolean}} opts  splitEnabled defaults to true
 * @returns {{layout:'full'|'split-camera',feedUrl:string,feedKind:string|null}}
 */
export function stageLayoutFromMessage(type, payload = {}, opts = {}) {
    const splitEnabled = opts.splitEnabled !== false; // default true
    if (type === 'show_pip' && payload.url && splitEnabled) {
        return {
            layout: 'split-camera',
            feedUrl: payload.url,
            feedKind: payload.kind === 'live' ? 'live' : 'snapshot',
        };
    }
    // dismiss_pip, no url, split disabled, or anything else → full screen.
    return { layout: 'full', feedUrl: '', feedKind: null };
}

export class StageLayout {
    /** @param {Document} root */
    constructor(root) {
        this.body = root.body || document.body;
        this.img = root.querySelector('#split-feed-image');
        if (!this.img) {
            console.warn('[StageLayout] #split-feed-image not found — split disabled');
        }
        // If the feed fails to load (dead camera URL / dropped MJPEG), collapse
        // back to the full-screen avatar rather than leaving a broken panel up.
        if (this.img) {
            this.img.addEventListener('error', () => { this.body.dataset.layout = 'full'; });
        }
    }

    /** @param {{layout:string,feedUrl:string,feedKind:string|null}} view */
    apply(view) {
        if (view.layout === 'split-camera' && view.feedUrl) {
            if (this.img) this.img.src = view.feedUrl;
            this.body.dataset.layout = 'split-camera';
        } else {
            this.body.dataset.layout = 'full';
            // Drop the src so an MJPEG stream stops fetching when hidden.
            if (this.img) this.img.removeAttribute('src');
        }
    }
}
