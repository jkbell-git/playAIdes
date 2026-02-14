import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/**
 * Scene — sets up the Three.js renderer, camera, lights, and controls.
 * Exports singleton references so other modules can add objects to the scene.
 */

// ── Renderer ────────────────────────────────────────────────────────────────
const canvas = document.getElementById('viewer');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
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
directionalLight.castShadow = true;
directionalLight.shadow.mapSize.width = 1024;
directionalLight.shadow.mapSize.height = 1024;
scene.add(directionalLight);

// Soft fill light from the opposite side
const fillLight = new THREE.DirectionalLight(0xc4d7ff, 0.4);
fillLight.position.set(-3, 2, -2);
scene.add(fillLight);

// ── Ground plane (subtle) ───────────────────────────────────────────────────
const groundGeo = new THREE.CircleGeometry(5, 64);
const groundMat = new THREE.MeshStandardMaterial({
    color: 0x16213e,
    roughness: 0.9,
    metalness: 0.0,
});
const ground = new THREE.Mesh(groundGeo, groundMat);
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

export { scene, camera, renderer, controls, clock };
