/**
 * pipOverlay.js — picture-in-picture panel (spec §3.10).
 *
 * `pipViewFromMessage` is the pure decision function (unit-tested); the
 * `PipOverlay` class is the thin DOM glue (untested, per repo convention —
 * there is no jsdom harness). Driven by `show_pip` / `dismiss_pip` WS messages.
 */

/** Pure: compute the desired overlay view from an inbound WS message. */
export function pipViewFromMessage(type, payload = {}) {
    if (type === 'show_pip' && payload.url) {
        return {
            visible: true,
            url: payload.url,
            kind: payload.kind === 'live' ? 'live' : 'snapshot',
        };
    }
    // dismiss_pip, or show_pip with no url, or anything else → hidden.
    return { visible: false, url: '', kind: null };
}

export class PipOverlay {
    /** @param {Document|HTMLElement} root */
    constructor(root) {
        this.el = root.querySelector('#pip-overlay');
        this.img = root.querySelector('#pip-image');
    }

    /** @param {{visible:boolean,url:string,kind:string|null}} view */
    apply(view) {
        if (!this.el) return;
        if (view.visible && view.url) {
            if (this.img) this.img.src = view.url;
            this.el.classList.add('visible');
        } else {
            this.el.classList.remove('visible');
            // Drop the src so an MJPEG stream stops fetching when hidden.
            if (this.img) this.img.removeAttribute('src');
        }
    }
}
