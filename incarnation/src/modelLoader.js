import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

/**
 * ModelLoader — loads glTF/GLB, VRM, and FBX 3D models.
 * Centres and scales them, then returns { model, clips, skinnedMeshes, vrm }.
 *
 * Supported formats:
 *   .gltf / .glb — standard glTF via GLTFLoader
 *   .vrm         — VRoid / VRM via GLTFLoader + VRMLoaderPlugin
 *   .fbx         — Autodesk FBX via FBXLoader
 */

// ── Loaders ─────────────────────────────────────────────────────────────────
const gltfLoader = new GLTFLoader();
gltfLoader.register((parser) => new VRMLoaderPlugin(parser));

const fbxLoader = new FBXLoader();

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Detect model format from URL extension.
 * @param {string} url
 * @returns {'vrm'|'fbx'|'gltf'}
 */
function detectFormat(url) {
    const clean = url.split('?')[0].toLowerCase();
    if (clean.endsWith('.vrm')) return 'vrm';
    if (clean.endsWith('.fbx')) return 'fbx';
    return 'gltf'; // .gltf, .glb, or anything else
}

/**
 * Normalise a model URL so Vite can serve it from public/.
 * Ensures a leading '/' for relative paths.
 * @param {string} url
 * @returns {string}
 */
function normaliseUrl(url) {
    if (url.startsWith('/') || url.startsWith('http://') || url.startsWith('https://')) {
        return url;
    }
    return '/' + url;
}

// ── Loader dispatch ─────────────────────────────────────────────────────────

/**
 * Load a glTF / GLB / VRM model via GLTFLoader.
 * @returns {Promise<{model: THREE.Group, clips: THREE.AnimationClip[], vrm: import('@pixiv/three-vrm').VRM|null}>}
 */
async function loadGLTF(url, onProgress) {
    const gltf = await new Promise((resolve, reject) => {
        gltfLoader.load(url, resolve, onProgress, reject);
    });

    let model;
    let vrm = null;

    if (gltf.userData.vrm) {
        vrm = gltf.userData.vrm;
        VRMUtils.removeUnnecessaryJoints(vrm.scene);
        model = vrm.scene;
        VRMUtils.rotateVRM0(vrm);
    } else {
        model = gltf.scene;
    }

    return { model, clips: gltf.animations || [], vrm };
}

/**
 * Load an FBX model via FBXLoader.
 * @returns {Promise<{model: THREE.Group, clips: THREE.AnimationClip[], vrm: null}>}
 */
async function loadFBX(url, onProgress) {
    const fbx = await new Promise((resolve, reject) => {
        fbxLoader.load(url, resolve, onProgress, reject);
    });

    return { model: fbx, clips: fbx.animations || [], vrm: null };
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Load a 3D model (glTF / GLB / VRM / FBX).
 * @param {string} rawUrl  Path or URL to the model file.
 * @param {Function} [onProgress]  Optional progress callback.
 * @returns {Promise<{model: THREE.Group, clips: THREE.AnimationClip[], skinnedMeshes: THREE.SkinnedMesh[], vrm: import('@pixiv/three-vrm').VRM|null}>}
 */
export async function loadModel(rawUrl, onProgress) {
    const url = normaliseUrl(rawUrl);
    const format = detectFormat(url);

    let model, clips, vrm;

    switch (format) {
        case 'fbx':
            ({ model, clips, vrm } = await loadFBX(url, onProgress));
            break;
        case 'vrm':
        case 'gltf':
        default:
            ({ model, clips, vrm } = await loadGLTF(url, onProgress));
            break;
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

    return { model, clips, skinnedMeshes, vrm };
}

/**
 * Load a standalone animation file (glTF / GLB / FBX) and return its clips.
 * Unlike loadModel, this does NOT add anything to the scene — it only
 * extracts AnimationClip[] for use with an already-loaded model.
 *
 * @param {string} rawUrl  Path or URL to the animation file.
 * @param {Function} [onProgress]  Optional progress callback.
 * @returns {Promise<THREE.AnimationClip[]>}
 */
export async function loadAnimationFile(rawUrl, onProgress) {
    const url = normaliseUrl(rawUrl);
    const format = detectFormat(url);

    let clips;

    switch (format) {
        case 'fbx': {
            const fbx = await new Promise((resolve, reject) => {
                fbxLoader.load(url, resolve, onProgress, reject);
            });
            clips = fbx.animations || [];
            break;
        }
        case 'vrm':
        case 'gltf':
        default: {
            const gltf = await new Promise((resolve, reject) => {
                gltfLoader.load(url, resolve, onProgress, reject);
            });
            clips = gltf.animations || [];
            break;
        }
    }

    console.log(`[ModelLoader] Loaded ${clips.length} animation clip(s) from ${rawUrl}`);
    return clips;
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
