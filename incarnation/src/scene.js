import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { EXRLoader } from 'three/addons/loaders/EXRLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { detectBackgroundType, isExrUrl } from './sceneBackgrounds.js';
import { loadConfig } from './viewerConfig.js';

/**
 * Scene — sets up the Three.js renderer, camera, lights, and controls.
 * Exports singleton references so other modules can add objects to the scene.
 */

// Low-quality mode (?quality=low) for weak GPUs (e.g. a Fire TV stick): caps the
// device pixel ratio and drops shadows — the heaviest fill-rate costs. MSAA is
// kept on (cheap on the tile-based GPUs these devices use, and it prevents the
// jagged model edges you'd otherwise get). Capable devices (?quality=high) also
// render shadows and allow a higher pixel ratio.
const cfg = loadConfig();
const lowQuality = cfg.quality === 'low';

// ── Renderer ────────────────────────────────────────────────────────────────
const canvas = document.getElementById('viewer');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
// Resolution dial: ?dpr=<n> overrides the cap (clamped 0.5–3) so sharpness vs.
// smoothness can be tuned per device; otherwise auto-cap (low: 1, high: up to 2).
const renderScale = cfg.pixelRatio != null
    ? Math.max(0.5, Math.min(3, cfg.pixelRatio))
    : Math.min(window.devicePixelRatio, lowQuality ? 1 : 2);
renderer.setPixelRatio(renderScale);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = !lowQuality;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

// ── Scene ───────────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

// Subtle fog for depth
scene.fog = new THREE.Fog(0x1a1a2e, 8, 20);

// ── Camera ──────────────────────────────────────────────────────────────────
const camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    100
);
camera.position.set(0, 1.2, 3);

// ── Controls ────────────────────────────────────────────────────────────────
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 1;
controls.maxDistance = 10;
controls.maxPolarAngle = Math.PI / 1.8;
controls.update();

// ── Lights ──────────────────────────────────────────────────────────────────
const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
scene.add(ambientLight);

const directionalLight = new THREE.DirectionalLight(0xfff0dd, 1.2);
directionalLight.position.set(3, 5, 4);
directionalLight.castShadow = !lowQuality;
directionalLight.shadow.mapSize.width = 1024;
directionalLight.shadow.mapSize.height = 1024;
scene.add(directionalLight);

// Soft fill light from the opposite side
const fillLight = new THREE.DirectionalLight(0xc4d7ff, 0.4);
fillLight.position.set(-3, 2, -2);
scene.add(fillLight);

// ── Ground plane (subtle shadow catcher only) ───────────────────────────────
// Provide a transparent plane that only receives shadows, so the background shows through
const shadowMaterial = new THREE.ShadowMaterial({ opacity: 0.5 });
const groundGeo = new THREE.PlaneGeometry(100, 100);
const ground = new THREE.Mesh(groundGeo, shadowMaterial);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

// ── Resize handler ──────────────────────────────────────────────────────────
function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}
window.addEventListener('resize', onResize);

// ── Clock ───────────────────────────────────────────────────────────────────
const clock = new THREE.Clock();

// ── Background & Camera APIs ────────────────────────────────────────────────

// Track the currently-loaded 3D background so we can remove it on swap.
let _bg3DScene = null;

// Spec §4b failure-fallback color for missing/failed backgrounds. Mid-grey
// reads as "scene unavailable" without competing with the persona's chrome
// (the gold/red P5 strip is always present).
const FALLBACK_GREY = 0x808080;

/**
 * Dispose any currently-assigned background or environment texture so we
 * don't leak GPU memory across swaps. (three.js Texture objects live in
 * VRAM until explicitly disposed.)
 */
function _disposeCurrentBackground() {
    if (scene.background && scene.background.isTexture) {
        scene.background.dispose();
    }
    if (scene.environment && scene.environment.isTexture) {
        scene.environment.dispose();
    }
}

function setBackground(url) {
    if (!url) {
        console.log('[scene] No background URL provided');
        _disposeCurrentBackground();
        scene.background = new THREE.Color(FALLBACK_GREY);
        scene.environment = null;
        if (_bg3DScene) { scene.remove(_bg3DScene); _bg3DScene = null; }
        return;
    }

    // Dispatch by extension. Spec §4b "auto-detected by file extension."
    const kind = detectBackgroundType(url);
    // Always tear down any previous 3D background; texture/envMap disposal
    // happens inside the per-tier loaders right before reassignment.
    if (_bg3DScene) { scene.remove(_bg3DScene); _bg3DScene = null; }

    if (kind === 'flat') {
        const loader = new THREE.TextureLoader();
        loader.load(url, (texture) => {
            texture.colorSpace = THREE.SRGBColorSpace;
            _disposeCurrentBackground();
            scene.background = texture;
            scene.environment = null;   // flat images aren't IBL sources
        }, undefined, (err) => {
            console.error('[scene] Failed to load flat background:', err);
        });
        return;
    }
    if (kind === 'hdri') {
        loadHDRIBackground(url);
        return;
    }
    if (kind === 'glb') {
        load3DBackground(url);
        return;
    }
    console.warn('[scene] unknown background extension:', url);
}

/**
 * Load an HDRI panorama (.hdr or .exr) and assign it as both the scene
 * background AND the environment map (image-based lighting). Spec §4b.
 */
function loadHDRIBackground(url) {
    const isExr = isExrUrl(url);
    const Loader = isExr ? EXRLoader : RGBELoader;
    const loader = new Loader();
    loader.load(url, (hdrTexture) => {
        const pmrem = new THREE.PMREMGenerator(renderer);
        pmrem.compileEquirectangularShader();
        const envMap = pmrem.fromEquirectangular(hdrTexture).texture;
        _disposeCurrentBackground();
        scene.background = envMap;
        scene.environment = envMap;
        hdrTexture.dispose();
        pmrem.dispose();
    }, undefined, (err) => {
        console.error('[scene] HDRI load failed; falling back to grey:', err);
        _disposeCurrentBackground();
        scene.background = new THREE.Color(FALLBACK_GREY);
        scene.environment = null;
    });
}

/**
 * Load a 3D background scene (.glb / .gltf). The loaded scene is added
 * to the main THREE.Scene next to the VRM. Existing rim/key lights still
 * apply; any lights packed into the .glb are added on top. Spec §4b.
 *
 * On success: leaves a solid black behind the 3D scene so geometry without
 * its own skybox doesn't render against a transparent canvas. The .glb
 * itself is responsible for any skybox / dome it wants visible.
 *
 * On failure: falls back to a flat grey color and warns.
 */
function load3DBackground(url) {
    if (_bg3DScene) {
        scene.remove(_bg3DScene);
        _bg3DScene = null;
    }
    const loader = new GLTFLoader();
    loader.load(url, (gltf) => {
        _bg3DScene = gltf.scene;
        scene.add(_bg3DScene);
        // Clear any HDRI env map / texture left over from a prior swap.
        // 3D scenes can still benefit from a non-null environment if the
        // scene wants IBL, but that's the .glb's responsibility — we
        // start it clean.
        _disposeCurrentBackground();
        scene.background = new THREE.Color(0x000000);
        scene.environment = null;
    }, undefined, (err) => {
        console.warn('[scene] 3D background load failed; falling back to grey:', err);
        _disposeCurrentBackground();
        scene.background = new THREE.Color(FALLBACK_GREY);
        scene.environment = null;
    });
}

function focusOnHead(model) {
    if (!model) return;
    console.log("[scene] Focusing on head");
    // Use a bounding box to find the rough center/top of the model
    const box = new THREE.Box3().setFromObject(model);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());

    // Better approximate head position: typically around 85-90% of total height
    // We also want to look slightly "down" at the face rather than from below.
    const headY = box.min.y + (size.y * 0.88);

    // Target the actual face center
    const targetPos = new THREE.Vector3(center.x, headY, center.z);

    // Place camera right in front of the face
    // Z offset controls how "close" the camera gets
    // Y offset controls angle (slightly higher than the focus target)
    const camTargetPos = new THREE.Vector3(
        center.x,
        headY + 0.05,
        center.z + 0.6
    );

    // Naive simple lerp loop via requestAnimationFrame
    let alpha = 0;
    function animateFocus() {
        alpha += 0.02; // Speed of pan
        if (alpha > 1) {
            controls.target.copy(targetPos);
            camera.position.copy(camTargetPos);
            controls.update();
            return;
        }

        controls.target.lerp(targetPos, 0.05);
        camera.position.lerp(camTargetPos, 0.05);
        controls.update();

        requestAnimationFrame(animateFocus);
    }

    animateFocus();
}

export { scene, camera, renderer, controls, clock, setBackground, loadHDRIBackground, load3DBackground, focusOnHead };
