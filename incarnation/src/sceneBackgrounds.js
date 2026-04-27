/**
 * sceneBackgrounds.js — pure helpers for the tiered background loader.
 *
 * The actual scene mutation (texture / env-map / glTF instance) lives in
 * scene.js where three.js objects are constructed. This module is pure so
 * the extension classification can be unit-tested in node without DOM.
 */

const FLAT_EXTS = ['.jpg', '.jpeg', '.png', '.webp'];
const HDRI_EXTS = ['.hdr', '.exr'];
const GLB_EXTS  = ['.glb', '.gltf'];

/**
 * Classify a background URL by extension.
 *
 * @param {string|null|undefined} url
 * @returns {'flat' | 'hdri' | 'glb' | 'unknown'}
 */
export function detectBackgroundType(url) {
    if (!url || typeof url !== 'string') return 'unknown';
    // Strip query strings (`?v=2`) and fragments (`#x`) so the extension
    // match isn't fooled by cache-busters.
    const stripped = url.split('?')[0].split('#')[0].toLowerCase();
    if (FLAT_EXTS.some((e) => stripped.endsWith(e))) return 'flat';
    if (HDRI_EXTS.some((e) => stripped.endsWith(e))) return 'hdri';
    if (GLB_EXTS.some((e) => stripped.endsWith(e))) return 'glb';
    return 'unknown';
}

/**
 * True iff the URL points to an OpenEXR file. Used by loadHDRIBackground
 * to pick between RGBELoader and EXRLoader.
 */
export function isExrUrl(url) {
    if (!url || typeof url !== 'string') return false;
    return url.split('?')[0].split('#')[0].toLowerCase().endsWith('.exr');
}
