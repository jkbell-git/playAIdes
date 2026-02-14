import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

/**
 * ModelLoader — loads glTF/GLB 3D models, centres and scales them.
 * Returns { model, clips, skinnedMeshes } for use by other managers.
 *
 * Future: VRM branch using @pixiv/three-vrm.
 */

const gltfLoader = new GLTFLoader();

/**
 * Load a glTF / GLB model.
 * @param {string} url  Path or URL to the model file.
 * @param {Function} [onProgress]  Optional progress callback.
 * @returns {Promise<{model: THREE.Group, clips: THREE.AnimationClip[], skinnedMeshes: THREE.SkinnedMesh[]}>}
 */
export async function loadModel(url, onProgress) {
    const gltf = await new Promise((resolve, reject) => {
        gltfLoader.load(url, resolve, onProgress, reject);
    });

    const model = gltf.scene;

    // ── Normalise: centre and scale to ~1.6 m tall ────────────────────────────
    const box = new THREE.Box3().setFromObject(model);
    const size = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());

    const targetHeight = 1.6; // metres
    const scale = targetHeight / size.y;
    model.scale.setScalar(scale);

    // Re-centre so feet sit on y = 0
    model.position.x = -centre.x * scale;
    model.position.y = -box.min.y * scale;
    model.position.z = -centre.z * scale;

    // Enable shadows on every mesh child
    model.traverse((child) => {
        if (child.isMesh) {
            child.castShadow = true;
            child.receiveShadow = true;
        }
    });

    // Collect skinned meshes (morph targets live here)
    const skinnedMeshes = [];
    model.traverse((child) => {
        if (child.isSkinnedMesh || (child.isMesh && child.morphTargetInfluences)) {
            skinnedMeshes.push(child);
        }
    });

    const clips = gltf.animations || [];

    return { model, clips, skinnedMeshes };
}

/**
 * Convenience: list morph target names from a set of skinned meshes.
 * @param {THREE.SkinnedMesh[]} skinnedMeshes
 * @returns {string[]}
 */
export function listMorphTargets(skinnedMeshes) {
    const names = new Set();
    for (const mesh of skinnedMeshes) {
        if (mesh.morphTargetDictionary) {
            for (const name of Object.keys(mesh.morphTargetDictionary)) {
                names.add(name);
            }
        }
    }
    return [...names].sort();
}
