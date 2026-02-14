import * as THREE from 'three';

/**
 * AnimationManager — wraps THREE.AnimationMixer.
 * Manages loading, playing, cross-fading, and stopping animation clips.
 */
export class AnimationManager {
    /** @param {THREE.Object3D} root  The root object (loaded model). */
    constructor(root) {
        this.mixer = new THREE.AnimationMixer(root);
        /** @type {Map<string, THREE.AnimationClip>} */
        this.clips = new Map();
        /** @type {THREE.AnimationAction|null} */
        this.currentAction = null;
    }

    // ── Clip management ─────────────────────────────────────────────────────
    /**
     * Register animation clips by name.
     * @param {THREE.AnimationClip[]} clips
     */
    loadClips(clips) {
        for (const clip of clips) {
            this.clips.set(clip.name, clip);
        }
    }

    /** @returns {string[]} List of registered clip names. */
    listClips() {
        return [...this.clips.keys()];
    }

    // ── Playback ────────────────────────────────────────────────────────────
    /**
     * Play a named clip, optionally cross-fading from the current one.
     * @param {string} name
     * @param {object} [opts]
     * @param {boolean} [opts.loop=true]
     * @param {number}  [opts.crossFadeDuration=0.4]  seconds
     * @param {number}  [opts.timeScale=1]
     */
    play(name, { loop = true, crossFadeDuration = 0.4, timeScale = 1 } = {}) {
        const clip = this.clips.get(name);
        if (!clip) {
            console.warn(`[AnimationManager] clip "${name}" not found`);
            return;
        }

        const nextAction = this.mixer.clipAction(clip);
        nextAction.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
        nextAction.clampWhenFinished = !loop;
        nextAction.timeScale = timeScale;

        if (this.currentAction && this.currentAction !== nextAction) {
            nextAction.reset().setEffectiveWeight(1);
            this.currentAction.crossFadeTo(nextAction, crossFadeDuration, true);
        }

        nextAction.play();
        this.currentAction = nextAction;
    }

    /** Stop all actions. */
    stop() {
        this.mixer.stopAllAction();
        this.currentAction = null;
    }

    /** Pause the current action. */
    pause() {
        if (this.currentAction) this.currentAction.paused = true;
    }

    /** Resume the current action. */
    resume() {
        if (this.currentAction) this.currentAction.paused = false;
    }

    // ── Per-frame update ────────────────────────────────────────────────────
    /** @param {number} delta  Seconds since last frame. */
    update(delta) {
        this.mixer.update(delta);
    }
}
