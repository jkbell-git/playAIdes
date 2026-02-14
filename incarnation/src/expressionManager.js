/**
 * ExpressionManager — controls morph-target based facial expressions.
 * Works with any glTF model that has blend-shape morph targets on its meshes.
 *
 * Usage:
 *   const em = new ExpressionManager(skinnedMeshes);
 *   em.setExpression('happy', 0.8);
 *   em.clearExpressions();
 */
export class ExpressionManager {
    /**
     * @param {import('three').Mesh[]} meshes  Meshes with morph targets.
     */
    constructor(meshes = []) {
        /** @type {import('three').Mesh[]} */
        this.meshes = meshes;
    }

    /** Replace the mesh list (e.g. after loading a new model). */
    setMeshes(meshes) {
        this.meshes = meshes;
    }

    /**
     * Set a single morph-target value across all meshes that contain it.
     * @param {string} name   Morph-target name (e.g. "happy", "angry").
     * @param {number} value  Weight 0–1.
     */
    setExpression(name, value) {
        const clamped = Math.max(0, Math.min(1, value));
        for (const mesh of this.meshes) {
            const dict = mesh.morphTargetDictionary;
            if (dict && name in dict) {
                mesh.morphTargetInfluences[dict[name]] = clamped;
            }
        }
    }

    /**
     * Set multiple expressions at once.
     * @param {Record<string, number>} expressions  e.g. { happy: 0.8, sad: 0.0 }
     */
    setExpressions(expressions) {
        for (const [name, value] of Object.entries(expressions)) {
            this.setExpression(name, value);
        }
    }

    /** Reset all morph-target influences to 0. */
    clearExpressions() {
        for (const mesh of this.meshes) {
            if (mesh.morphTargetInfluences) {
                mesh.morphTargetInfluences.fill(0);
            }
        }
    }

    /** @returns {string[]} All available morph-target names. */
    listExpressions() {
        const names = new Set();
        for (const mesh of this.meshes) {
            if (mesh.morphTargetDictionary) {
                for (const name of Object.keys(mesh.morphTargetDictionary)) {
                    names.add(name);
                }
            }
        }
        return [...names].sort();
    }
}
