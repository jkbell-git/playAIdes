import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMAnimationLoaderPlugin, createVRMAnimationClip } from '@pixiv/three-vrm-animation';

/**
 * vrmaLoader — loads VRMA (VRM Animation) files and converts them
 * to THREE.AnimationClip retargeted for a specific VRM model.
 *
 * VRMA is the standard animation format for VRM models, part of the
 * VRM specification. Unlike Mixamo FBX retargeting, VRMA files are
 * purpose-built for VRM and map cleanly to humanoid bones + expressions.
 */

// Dedicated GLTFLoader with VRMAnimationLoaderPlugin registered
const vrmaGltfLoader = new GLTFLoader();
vrmaGltfLoader.register((parser) => new VRMAnimationLoaderPlugin(parser));

/**
 * Load a VRMA animation file and create a retargeted AnimationClip
 * for the given VRM model.
 *
 * @param {string} url  Path or URL to the .vrma file.
 * @param {import('@pixiv/three-vrm').VRM} vrm  The loaded VRM model instance.
 * @returns {Promise<import('three').AnimationClip|null>}
 */
export async function loadVRMAAnimation(url, vrm) {
    const gltf = await new Promise((resolve, reject) => {
        vrmaGltfLoader.load(url, resolve, undefined, reject);
    });

    // VRMAnimationLoaderPlugin stores parsed animations in userData.vrmAnimations
    const vrmAnimations = gltf.userData.vrmAnimations;

    if (!vrmAnimations || vrmAnimations.length === 0) {
        console.warn('[vrmaLoader] No VRM animations found in:', url);
        return null;
    }

    // Create a retargeted AnimationClip from the first VRMAnimation
    const vrmAnimation = vrmAnimations[0];
    const clip = createVRMAnimationClip(vrmAnimation, vrm);

    console.log(`[vrmaLoader] Loaded VRMA clip "${clip.name}" (${clip.duration.toFixed(2)}s) from ${url}`);
    return clip;
}
