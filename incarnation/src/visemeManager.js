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
        /** @type {any|null} */
        this.expressionManager = null;
        this._sequenceTimer = null;

        // Mapping from standard (Oculus / ARKit) viseme names to VRM
        // expression preset names.
        //
        // Note: VRM 1.0 / VRoid models use `aa, ih, ou, ee, oh`
        // (NOT `a, i, u, e, o`). Earlier versions of this map used the
        // short vowel names which silently did nothing, because
        // expressionManager.setValue('i', …) on a VRM with only 'ih' is
        // a no-op — and the call site swallowed the miss in a try/catch.
        // The result was visible as "no lip sync at all" on VRoid models.
        this._vrmMap = {
            'viseme_aa': 'aa',
            'viseme_I':  'ih',
            'viseme_U':  'ou',
            'viseme_E':  'ee',
            'viseme_O':  'oh',
            'viseme_sil': 'neutral',
        };

        // Populated from setExpressionManager() — used to warn once if a
        // lookup misses entirely, so broken mappings can't silently hide.
        this._knownVRMExpressions = null;
        this._missWarned = new Set();
    }

    /** Set the VRM expression manager for preset-based visemes. */
    setExpressionManager(mgr) {
        this.expressionManager = mgr;

        // Cache which expressions this model actually supports so
        // setViseme() can skip misses without try/catch, and we can
        // warn clearly when the map is out of sync with the model.
        this._knownVRMExpressions = new Set();
        try {
            const map = mgr?._expressionMap ?? mgr?.expressionMap;
            if (map) {
                const names = map instanceof Map
                    ? [...map.keys()]
                    : Object.keys(map);
                names.forEach((n) => this._knownVRMExpressions.add(n));
            }
        } catch (_) { /* fine — fall back to blind setValue */ }

        if (this._knownVRMExpressions && this._knownVRMExpressions.size) {
            console.log('[VisemeManager] VRM expressions available:',
                [...this._knownVRMExpressions].sort().join(', '));
            // Warn if required viseme mappings are missing entirely
            const required = Object.values(this._vrmMap);
            const missing = required.filter((n) => !this._knownVRMExpressions.has(n));
            if (missing.length) {
                console.warn('[VisemeManager] ⚠ VRM is missing these mapped ' +
                    'viseme presets (lip sync will be degraded): ' +
                    missing.join(', '));
            }
        }
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

        // Use VRM expression manager if available
        if (this.expressionManager) {
            const vrmName = this._vrmMap[visemeName] || visemeName;
            // Only call setValue for expressions we know the model has;
            // otherwise three-vrm logs a warning per-frame which floods
            // the console and mangles perf.
            if (!this._knownVRMExpressions
                || this._knownVRMExpressions.has(vrmName)) {
                try {
                    this.expressionManager.setValue(vrmName, clamped);
                } catch (e) { /* shouldn't happen with the gate above */ }
            } else if (!this._missWarned.has(vrmName)) {
                this._missWarned.add(vrmName);
                console.debug(`[VisemeManager] no VRM expression "${vrmName}" — skipping`);
            }
        }

        // Fallback or parallel: drive raw morph targets
        for (const mesh of this.meshes) {
            const dict = mesh.morphTargetDictionary;
            if (dict && visemeName in dict) {
                mesh.morphTargetInfluences[dict[visemeName]] = clamped;
            }
        }
    }

    /** Reset all viseme morph targets to 0. */
    clearVisemes() {
        if (this.expressionManager) {
            for (const vrmName of Object.values(this._vrmMap)) {
                if (this._knownVRMExpressions
                    && !this._knownVRMExpressions.has(vrmName)) continue;
                try { this.expressionManager.setValue(vrmName, 0); } catch (e) {}
            }
        }

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
