import * as THREE from 'three';

/**
 * cameraDirector.js — drives the viewer camera automatically (no user
 * controls) in kiosk / unattended mode.
 *
 * It picks a "shot" from scene state and frames the avatar's bounding box:
 *   • bust — idle (no one-shot animation): upper body, head in the upper
 *            third of the frame.
 *   • full — a one-shot animation (intro / gesture) is playing: whole body,
 *            so the motion reads.
 *
 * Shot selection (chooseShot) and framing (computeShotPose) are pure, so
 * both are unit-tested without a WebGL context. The class wires them to a
 * THREE camera + OrbitControls and eases between poses each frame.
 *
 * Future: characterCount > 1 → a "group" shot; multiple named views.
 */

// Shot presets. targetFrac = look-at height as a fraction of the avatar's
// height (0 = feet, 1 = top of head); extentFrac = the vertical slice of the
// avatar to fit in frame, as a fraction of height. Both are eyeball-tunable —
// adjust against a real avatar on the actual TV.
export const SHOTS = Object.freeze({
    // Idle: upper-body "bust". Looking high up the body with a tight extent
    // puts the head in the upper third and frames roughly the upper half.
    bust: { targetFrac: 0.82, extentFrac: 0.62 },
    // Animation playing: full body with head/foot room so motion reads.
    full: { targetFrac: 0.55, extentFrac: 1.18 },
});

/**
 * Pick a shot key from scene state. Pure.
 * @param {{animating:boolean, characterCount?:number}} [s]
 * @returns {'bust'|'full'}
 */
export function chooseShot({ animating = false, characterCount = 1 } = {}) {
    // characterCount is reserved for a future multi-character "group" shot.
    void characterCount;
    return animating ? 'full' : 'bust';
}

/**
 * Compute a camera position + look-at target that frames a vertical extent of
 * an avatar's bounding box. Pure math — no THREE required.
 *
 * The avatar is framed from the front (camera on the +z side, matching
 * scene.js focusOnHead). `fovDeg` is the camera's VERTICAL field of view, so
 * fitting a vertical extent is exact regardless of screen aspect ratio.
 *
 * @param {{minY:number, maxY:number, cx:number, cz:number}} box
 * @param {{targetFrac:number, extentFrac:number}} shot
 * @param {number} fovDeg  camera vertical FOV, degrees
 * @returns {{position:{x:number,y:number,z:number}, target:{x:number,y:number,z:number}}}
 */
export function computeShotPose(box, shot, fovDeg) {
    const height = box.maxY - box.minY;
    const targetY = box.minY + height * shot.targetFrac;
    const extent = height * shot.extentFrac;
    const distance = (extent / 2) / Math.tan((fovDeg * Math.PI / 180) / 2);
    return {
        position: { x: box.cx, y: targetY, z: box.cz + distance },
        target:   { x: box.cx, y: targetY, z: box.cz },
    };
}

export class CameraDirector {
    /**
     * @param {import('three').PerspectiveCamera} camera
     * @param {{target: import('three').Vector3, enabled: boolean}} [controls]  OrbitControls
     * @param {object} [opts]
     * @param {number} [opts.smoothing=0.08]  per-frame lerp factor (0..1)
     */
    constructor(camera, controls = null, { smoothing = 0.08 } = {}) {
        this.camera = camera;
        this.controls = controls;
        this.smoothing = smoothing;
        this.active = false;

        this._desiredPos = new THREE.Vector3();
        this._desiredTarget = new THREE.Vector3();
        this._target = new THREE.Vector3();        // the lerped look-at point
        this._hasDesired = false;

        this._box = new THREE.Box3();
        this._lastModel = null;
        this._lastShot = null;
    }

    /** Take over the camera: disable user controls. */
    enable() {
        this.active = true;
        if (this.controls) {
            this._target.copy(this.controls.target);   // seed for a smooth first ease
            this.controls.enabled = false;
        }
    }

    /** Hand the camera back to the user. */
    disable() {
        this.active = false;
        if (this.controls) this.controls.enabled = true;
    }

    /**
     * Recompute the desired pose from the current model + scene state. Cheap
     * to call every frame: the bounding box is only re-measured when the model
     * or the chosen shot actually changes (a fixed frame also looks steadier
     * than one that chases every limb during an animation).
     * @param {{model: import('three').Object3D|null, animating: boolean, characterCount?: number}} s
     */
    setSceneState({ model, animating, characterCount = 1 }) {
        if (!model) { this._hasDesired = false; this._lastModel = null; return; }

        const shot = chooseShot({ animating, characterCount });
        if (model === this._lastModel && shot === this._lastShot) return;
        this._lastModel = model;
        this._lastShot = shot;

        this._box.setFromObject(model);
        const { min, max } = this._box;
        const pose = computeShotPose(
            { minY: min.y, maxY: max.y, cx: (min.x + max.x) / 2, cz: (min.z + max.z) / 2 },
            SHOTS[shot],
            this.camera.fov,
        );
        this._desiredPos.set(pose.position.x, pose.position.y, pose.position.z);
        this._desiredTarget.set(pose.target.x, pose.target.y, pose.target.z);
        this._hasDesired = true;
    }

    /** Per-frame: ease the camera toward the desired pose. */
    update() {
        if (!this.active || !this._hasDesired) return;
        const a = this.smoothing;
        this.camera.position.lerp(this._desiredPos, a);
        this._target.lerp(this._desiredTarget, a);
        this.camera.lookAt(this._target);
        // Keep controls.target in sync so a later disable() resumes cleanly.
        if (this.controls) this.controls.target.copy(this._target);
    }

    /** @returns {string|null} the currently-selected shot key. */
    get currentShot() { return this._lastShot; }
}
