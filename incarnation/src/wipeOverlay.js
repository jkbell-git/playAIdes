/**
 * wipeOverlay.js — 200ms red-diagonal wipe shown during persona swap.
 *
 * Usage:
 *   const wipe = new WipeOverlay(document.getElementById('wipe-overlay'));
 *   await wipe.play();
 *   // safe to swap models now
 */
export class WipeOverlay {
    constructor(el) {
        this.el = el;
    }

    /** Trigger the animation; resolves when it finishes (~200 ms). */
    play() {
        if (!this.el) return Promise.resolve();
        return new Promise((resolve) => {
            const onEnd = () => {
                this.el.removeEventListener('animationend', onEnd);
                this.el.classList.remove('active');
                resolve();
            };
            this.el.addEventListener('animationend', onEnd);
            // Force a reflow so re-adding the class restarts the animation.
            void this.el.offsetWidth;
            this.el.classList.add('active');
        });
    }
}
