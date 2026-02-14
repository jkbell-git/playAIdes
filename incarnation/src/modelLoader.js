import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

/**
 * ModelLoader — loads glTF/GLB and VRM 3D models, centres and scales them.
 * Returns { model, clips, skinnedMeshes, vrm } for use by other managers.
 *
 * VRM files are detected by extension and loaded with @pixiv/three-vrm.
 */

const gltfLoader = new GLTFLoader();

// Register the VRM plugin so .vrm files are parsed automatically
gltfLoader.register((parser) => new VRMLoaderPlugin(parser));

/**
 * Detect whether a URL points to a VRM file.
 * @param {string} url
 * @returns {boolean}
 */
function isVRM(url) {
    return /\.vrm(\?.*)?$/i.test(url);
}

/**
 * Normalise a model URL so Vite can serve it from public/.
 * Ensures a leading '/' for relative paths.
 * @param {string} url
 * @returns {string}
 */
function normaliseUrl(url) {
    // Already absolute or a full URL — leave it
    if (url.startsWith('/') || url.startsWith('http://') || url.startsWith('https://')) {
        return url;
    }
    return '/' + url;
}

/**
 * Load a glTF / GLB / VRM model.
 * @param {string} rawUrl  Path or URL to the model file.
 * @param {Function} [onProgress]  Optional progress callback.
 * @returns {Promise<{model: THREE.Group, clips: THREE.AnimationClip[], skinnedMeshes: THREE.SkinnedMesh[], vrm: import('@pixiv/three-vrm').VRM|null}>}
 */
export async function loadModel(rawUrl, onProgress) {
    const url = normaliseUrl(rawUrl);

    const gltf = await new Promise((resolve, reject) => {
        gltfLoader.load(url, resolve, onProgress, reject);
    });

    let model;
    let vrm = null;

    // ── VRM-specific handling ────────────────────────────────────────────────
    if (gltf.userData.vrm) {
        vrm = gltf.userData.vrm;

        // VRMUtils.removeUnnecessaryJoints removes unused bones that can
        // cause warnings and performance issues.
        VRMUtils.removeUnnecessaryJoints(vrm.scene);

        model = vrm.scene;

        // VRM models face +Z by default; rotate to face camera (-Z)
        VRMUtils.rotateVRM0(vrm);
    } else {
        model = gltf.scene;
    }

    // ── Normalise: centre and scale to ~1.6 m tall ──────────────────────────
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

    return { model, clips, skinnedMeshes, vrm };
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
