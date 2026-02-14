/**
 * VisemeManager — drives morph-target based mouth shapes (visemes).
 *
 * Supports:
 *  - Setting a single viseme weight instantly.
 *  - Playing a timed sequence of visemes for basic speech animation.
 *
 * Standard viseme names (Oculus / ARKit convention):
 *   viseme_sil, viseme_PP, viseme_FF, viseme_TH, viseme_DD,
 *   viseme_kk, viseme_CH, viseme_SS, viseme_nn, viseme_RR,
 *   viseme_aa, viseme_E, viseme_I, viseme_O, viseme_U
 */
export class VisemeManager {
    /**
     * @param {import('three').Mesh[]} meshes  Meshes with morph targets.
     */
    constructor(meshes = []) {
        /** @type {import('three').Mesh[]} */
        this.meshes = meshes;
        this._sequenceTimer = null;
    }

    /** Replace the mesh list (e.g. after loading a new model). */
    setMeshes(meshes) {
        this.meshes = meshes;
    }

    /**
     * Set a single viseme morph-target weight.
     * @param {string} visemeName  e.g. "viseme_aa"
     * @param {number} weight      0–1
     */
    setViseme(visemeName, weight) {
        const clamped = Math.max(0, Math.min(1, weight));
        for (const mesh of this.meshes) {
            const dict = mesh.morphTargetDictionary;
            if (dict && visemeName in dict) {
                mesh.morphTargetInfluences[dict[visemeName]] = clamped;
            }
        }
    }

    /** Reset all viseme morph targets to 0. */
    clearVisemes() {
        for (const mesh of this.meshes) {
            if (!mesh.morphTargetDictionary) continue;
            for (const [name, idx] of Object.entries(mesh.morphTargetDictionary)) {
                if (name.startsWith('viseme_')) {
                    mesh.morphTargetInfluences[idx] = 0;
                }
            }
        }
    }

    /**
     * Play a timed sequence of visemes.
     * Each entry: { viseme: string, weight: number, time: number (seconds) }.
     * @param {{ viseme: string, weight: number, time: number }[]} sequence
     * @returns {Promise<void>} Resolves when the sequence finishes.
     */
    playVisemeSequence(sequence) {
        this.stopSequence();

        return new Promise((resolve) => {
            if (!sequence || sequence.length === 0) {
                resolve();
                return;
            }

            let idx = 0;
            const step = () => {
                // Clear previous visemes
                this.clearVisemes();

                if (idx >= sequence.length) {
                    this._sequenceTimer = null;
                    resolve();
                    return;
                }

                const entry = sequence[idx];
                this.setViseme(entry.viseme, entry.weight);
                idx++;

                // Schedule next entry
                const nextDelay = idx < sequence.length
                    ? (sequence[idx].time - entry.time) * 1000
                    : 200; // short hold on last viseme before clearing
                this._sequenceTimer = setTimeout(step, nextDelay);
            };

            // First step immediately or after its time offset
            this._sequenceTimer = setTimeout(step, sequence[0].time * 1000);
        });
    }

    /** Cancel a running viseme sequence. */
    stopSequence() {
        if (this._sequenceTimer !== null) {
            clearTimeout(this._sequenceTimer);
            this._sequenceTimer = null;
        }
        this.clearVisemes();
    }

    /** @returns {string[]} Available viseme morph-target names. */
    listVisemes() {
        const names = new Set();
        for (const mesh of this.meshes) {
            if (mesh.morphTargetDictionary) {
                for (const name of Object.keys(mesh.morphTargetDictionary)) {
                    if (name.startsWith('viseme_')) {
                        names.add(name);
                    }
                }
            }
        }
        return [...names].sort();
    }
}
