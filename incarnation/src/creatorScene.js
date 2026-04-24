/**
 * creatorScene.js — A self-contained 3D viewport for the Persona Forge page.
 *
 * Unlike scene.js (which sizes to window.innerWidth), this scene sizes itself
 * to its parent container so the canvas can live inside a framed "character
 * card" in the layout.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { loadVRMAAnimation } from './vrmaLoader.js';

export function createCreatorScene(canvas) {
    // ── Renderer ────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // ── Scene ───────────────────────────────────────────────────────
    const scene = new THREE.Scene();
    // No solid background — let the HTML gradient / radial show through
    scene.background = null;

    // ── Camera ──────────────────────────────────────────────────────
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 1.35, 2.4);

    // ── Controls ────────────────────────────────────────────────────
    const controls = new OrbitControls(camera, canvas);
    controls.target.set(0, 1.1, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controls.minDistance = 1;
    controls.maxDistance = 6;
    controls.maxPolarAngle = Math.PI / 1.9;
    controls.enablePan = false;
    controls.update();

    // ── Lights (JRPG-style rim lighting) ────────────────────────────
    // Warm key light (like a stage spotlight)
    const key = new THREE.DirectionalLight(0xffe6cc, 1.4);
    key.position.set(2, 4, 3);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    scene.add(key);

    // Cool fill from opposite side
    const fill = new THREE.DirectionalLight(0x8aa4ff, 0.45);
    fill.position.set(-3, 2, -1);
    scene.add(fill);

    // Red rim light from behind (P5 accent)
    const rim = new THREE.DirectionalLight(0xff3a5a, 0.5);
    rim.position.set(0, 2, -3);
    scene.add(rim);

    // Gold ambient wash (Genshin character-screen feel)
    const ambient = new THREE.AmbientLight(0xd4a74b, 0.35);
    scene.add(ambient);

    // ── Shadow-catcher plane ────────────────────────────────────────
    const shadowMat = new THREE.ShadowMaterial({ opacity: 0.4 });
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), shadowMat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // ── Placeholder ghost (shown when no VRM is loaded) ─────────────
    const placeholder = new THREE.Group();
    const ghost = new THREE.Mesh(
        new THREE.CapsuleGeometry(0.3, 0.9, 6, 12),
        new THREE.MeshStandardMaterial({
            color: 0x3a2f4a,
            emissive: 0x1a1228,
            transparent: true,
            opacity: 0.35,
            roughness: 0.8,
        })
    );
    ghost.position.y = 0.9;
    ghost.castShadow = true;
    placeholder.add(ghost);
    scene.add(placeholder);

    // ── VRM + animation state ───────────────────────────────────────
    let currentVrm = null;
    let mixer = null;
    /** Map of animationName → AnimationClip for the currently loaded VRM. */
    const clipCache = new Map();
    /** The AnimationAction currently playing (or paused). */
    let currentAction = null;
    /** Name of the currently-playing clip, for UI state. */
    let currentClipName = null;
    /** Callback fired with (name, state) where state is 'play'|'pause'|'stop'. */
    let onAnimStateChange = () => {};

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));

    async function loadVrm(url) {
        // Remove previous VRM
        if (currentVrm) {
            scene.remove(currentVrm.scene);
            currentVrm.dispose?.();
            currentVrm = null;
        }
        // Clear animation state tied to the old VRM
        clipCache.clear();
        currentAction = null;
        currentClipName = null;
        onAnimStateChange(null, 'stop');
        // Hide placeholder
        placeholder.visible = false;

        try {
            const gltf = await loader.loadAsync(url);
            const vrm = gltf.userData.vrm;
            if (!vrm) throw new Error('Loaded GLTF has no VRM payload');
            vrm.scene.traverse((obj) => {
                if (obj.isMesh) { obj.castShadow = true; obj.receiveShadow = true; }
            });
            scene.add(vrm.scene);
            currentVrm = vrm;
            mixer = new THREE.AnimationMixer(vrm.scene);
            mixer.addEventListener('finished', (e) => {
                // When a non-looping clip finishes, mark stopped.
                if (e.action === currentAction) {
                    currentAction = null;
                    const name = currentClipName;
                    currentClipName = null;
                    onAnimStateChange(name, 'stop');
                }
            });
            focusOnModel();
            return vrm;
        } catch (err) {
            placeholder.visible = true;
            throw err;
        }
    }

    function clearVrm() {
        if (currentVrm) {
            scene.remove(currentVrm.scene);
            currentVrm.dispose?.();
            currentVrm = null;
            mixer = null;
        }
        clipCache.clear();
        currentAction = null;
        currentClipName = null;
        onAnimStateChange(null, 'stop');
        placeholder.visible = true;
    }

    // ── Animation playback ──────────────────────────────────────────

    /**
     * Load (if needed) and play a VRMA animation by URL.
     * Subsequent calls with the same URL are cheap — clips are cached.
     * Replaces any currently-playing animation with a short crossfade.
     *
     * @param {string} url   VRMA file URL
     * @param {string} name  Display name; used for state/caching
     * @param {{loop?: boolean, fadeIn?: number, fadeOut?: number}} [opts]
     */
    async function playAnimation(url, name, opts = {}) {
        if (!currentVrm || !mixer) {
            throw new Error('No VRM loaded — cannot play animation');
        }
        const { loop = true, fadeIn = 0.25, fadeOut = 0.25 } = opts;

        // Load + cache clip
        let clip = clipCache.get(name);
        if (!clip) {
            clip = await loadVRMAAnimation(url, currentVrm);
            if (!clip) throw new Error(`VRMA "${name}" produced no clip`);
            clipCache.set(name, clip);
        }

        // Crossfade from any existing action
        const prev = currentAction;
        const next = mixer.clipAction(clip);
        next.reset();
        next.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity);
        next.clampWhenFinished = !loop;
        next.enabled = true;
        next.setEffectiveTimeScale(1);
        next.setEffectiveWeight(1);
        next.play();

        if (prev && prev !== next) {
            prev.crossFadeTo(next, fadeIn, false);
            // Stop the old one shortly after crossfade completes
            setTimeout(() => prev.stop(), Math.max(fadeIn, fadeOut) * 1000 + 50);
        } else {
            next.fadeIn(fadeIn);
        }

        mixer.timeScale = 1; // in case we were paused
        currentAction = next;
        currentClipName = name;
        onAnimStateChange(name, 'play');
    }

    function pauseAnimation() {
        if (!mixer || !currentAction) return;
        mixer.timeScale = 0;
        onAnimStateChange(currentClipName, 'pause');
    }

    function resumeAnimation() {
        if (!mixer || !currentAction) return;
        mixer.timeScale = 1;
        onAnimStateChange(currentClipName, 'play');
    }

    function togglePlayPause() {
        if (!mixer || !currentAction) return;
        if (mixer.timeScale === 0) resumeAnimation();
        else pauseAnimation();
    }

    function stopAnimation(fadeOut = 0.2) {
        if (!mixer || !currentAction) return;
        const action = currentAction;
        action.fadeOut(fadeOut);
        setTimeout(() => action.stop(), fadeOut * 1000 + 20);
        const name = currentClipName;
        currentAction = null;
        currentClipName = null;
        onAnimStateChange(name, 'stop');
    }

    function isPlaying() {
        return !!(mixer && currentAction && mixer.timeScale !== 0);
    }

    function getCurrentAnimationName() {
        return currentClipName;
    }

    function focusOnModel() {
        const target = currentVrm?.scene ?? placeholder;
        const box = new THREE.Box3().setFromObject(target);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        controls.target.set(center.x, center.y + size.y * 0.1, center.z);
        camera.position.set(center.x, center.y + size.y * 0.15, center.z + Math.max(size.y * 1.8, 1.6));
        controls.update();
    }

    function focusOnFace() {
        if (!currentVrm) return focusOnModel();
        const box = new THREE.Box3().setFromObject(currentVrm.scene);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const headY = box.min.y + size.y * 0.88;
        controls.target.set(center.x, headY, center.z);
        camera.position.set(center.x, headY + 0.04, center.z + 0.55);
        controls.update();
    }

    function resetCamera() {
        controls.reset();
        camera.position.set(0, 1.35, 2.4);
        controls.target.set(0, 1.1, 0);
        controls.update();
    }

    // ── Resize handling (fits parent container) ─────────────────────
    function resize() {
        const parent = canvas.parentElement;
        if (!parent) return;
        const w = parent.clientWidth || 1;
        const h = parent.clientHeight || 1;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
    }

    const ro = new ResizeObserver(resize);
    if (canvas.parentElement) ro.observe(canvas.parentElement);
    window.addEventListener('resize', resize);
    // Initial sizing after layout
    requestAnimationFrame(resize);

    // ── Render loop ─────────────────────────────────────────────────
    const clock = new THREE.Clock();
    let rafId = null;

    function tick() {
        const dt = clock.getDelta();
        controls.update();
        if (mixer) mixer.update(dt);
        if (currentVrm) currentVrm.update(dt);
        // Gentle idle rotation on the placeholder for a "waiting" feel
        if (placeholder.visible) placeholder.rotation.y += dt * 0.4;
        renderer.render(scene, camera);
        rafId = requestAnimationFrame(tick);
    }
    tick();

    function dispose() {
        if (rafId) cancelAnimationFrame(rafId);
        ro.disconnect();
        window.removeEventListener('resize', resize);
        renderer.dispose();
    }

    return {
        loadVrm,
        clearVrm,
        focusOnFace,
        focusOnModel,
        resetCamera,
        dispose,
        // Animation API
        playAnimation,
        pauseAnimation,
        resumeAnimation,
        togglePlayPause,
        stopAnimation,
        isPlaying,
        getCurrentAnimationName,
        /** @param {(name: string|null, state: 'play'|'pause'|'stop') => void} fn */
        onAnimStateChange(fn) { onAnimStateChange = fn || (() => {}); },
        get vrm() { return currentVrm; },
    };
}
