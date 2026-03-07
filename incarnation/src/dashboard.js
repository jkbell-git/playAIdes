import * as THREE from 'three';
import { scene, camera, renderer, controls, clock } from './scene.js';
import { loadModel } from './modelLoader.js';
import { AnimationManager } from './animationManager.js';
import { ExpressionManager } from './expressionManager.js';
import { uploadFile } from './ui/uploader.js';

// DOM Elements
const container = document.getElementById('avatar-container');
const avatarInput = document.getElementById('avatar-file');
const avatarBtn = document.getElementById('upload-avatar-btn');
const avatarStatus = document.getElementById('avatar-status');

const animInput = document.getElementById('animation-file');
const animBtn = document.getElementById('upload-animation-btn');
const animStatus = document.getElementById('animation-status');

const expressionsSection = document.getElementById('expressions-section');
const expressionsGrid = document.getElementById('expression-buttons');

const animationsSection = document.getElementById('animations-section');
const animationsGrid = document.getElementById('animation-buttons');

// Global state
let currentModel = null;
let currentVrm = null;
let animManager = null;
let exprManager = new ExpressionManager();

// Animation Loop
function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();

    controls.update();

    if (animManager) {
        animManager.update(delta);
    }

    if (currentVrm) {
        currentVrm.update(delta);
    }

    renderer.render(scene, camera);
}
animate();

// Fix Resizing for flexbox dashboard
function onDashboardResize() {
    if (!container.clientWidth) return; // not yet laid out
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
}
// scene.js already registers 'resize' on window, but sizes to the full window.
// We register our own listener to correct it.
window.addEventListener('resize', onDashboardResize);
// Defer initial resize to after the browser has done its first flexbox layout.
requestAnimationFrame(onDashboardResize);

// Helper: load model into scene
async function loadAvatar(url) {
    try {
        console.log(`[Dashboard] Loading avatar from ${url}`);
        const { model, skinnedMeshes, vrm } = await loadModel(url, (progress) => {
            const pct = Math.round((progress.loaded / progress.total) * 100);
            avatarStatus.textContent = `Loading... ${pct}%`;
        });

        // Remove old model
        if (currentModel) {
            scene.remove(currentModel);
        }

        currentModel = model;
        currentVrm = vrm;
        scene.add(model);

        // Reset animation manager
        animManager = new AnimationManager(model, null);

        // Reset expression manager
        exprManager.setMeshes(skinnedMeshes);

        avatarStatus.textContent = "Avatar loaded successfully!";
        avatarStatus.className = "status success";

        // Build Expression UI for both VRM and GLTF
        buildExpressionMap(vrm, exprManager);

    } catch (e) {
        console.error(e);
        avatarStatus.textContent = `Error loading: ${e.message}`;
        avatarStatus.className = "status error";
    }
}

// Build Expression UI
function buildExpressionMap(vrm, exprManager) {
    expressionsSection.style.display = 'block';
    expressionsGrid.innerHTML = '';

    let names = [];
    if (vrm && vrm.expressionManager) {
        const mgr = vrm.expressionManager;
        if (mgr.expressions) {
            for (const expr of mgr.expressions) {
                if (expr.expressionName) names.push(expr.expressionName);
            }
        }
    } else {
        names = exprManager.listExpressions();
    }

    names.sort();

    names.forEach(name => {
        const btn = document.createElement('button');
        btn.textContent = name;
        btn.onclick = () => {
            if (vrm && vrm.expressionManager) {
                // Reset VRM
                names.forEach(n => vrm.expressionManager.setValue(n, 0));
                vrm.expressionManager.setValue(name, 1.0);
            } else {
                // Reset GLTF
                exprManager.clearExpressions();
                exprManager.setExpression(name, 1.0);
            }
        };
        expressionsGrid.appendChild(btn);
    });
}

// Add a playback button for a successfully loaded clip
function addAnimationButton(clipName) {
    animationsSection.style.display = 'block';

    // Don't add duplicates
    if (animationsGrid.querySelector(`[data-clip="${CSS.escape(clipName)}"]`)) return;

    const btn = document.createElement('button');
    btn.textContent = clipName;
    btn.dataset.clip = clipName;
    btn.style.background = '#2196F3';
    btn.addEventListener('click', () => {
        if (!animManager) return;
        const shouldLoop = loopCheckbox.checked;
        animManager.play(clipName, { loop: shouldLoop, crossFadeDuration: 0.4 });
        // Highlight the active button
        animationsGrid.querySelectorAll('button').forEach(b => b.style.outline = '');
        btn.style.outline = '2px solid #fff';
    });
    animationsGrid.appendChild(btn);
}

// Upload Bindings
avatarBtn.addEventListener('click', async () => {
    const file = avatarInput.files[0];
    if (!file) {
        avatarStatus.textContent = "Please select a file first.";
        avatarStatus.className = "status error";
        return;
    }

    avatarStatus.textContent = "Uploading...";
    avatarStatus.className = "status";
    avatarBtn.disabled = true;

    try {
        const res = await uploadFile(file, 'http://localhost:8765/api/upload/avatar');
        avatarStatus.textContent = "Upload complete. Loading...";
        await loadAvatar(res.url);
    } catch (e) {
        avatarStatus.textContent = `Upload failed: ${e.message}`;
        avatarStatus.className = "status error";
    } finally {
        avatarBtn.disabled = false;
    }
});

const loopCheckbox = document.getElementById('animation-loop');

animBtn.addEventListener('click', async () => {
    const files = Array.from(animInput.files);
    if (!files.length) {
        animStatus.textContent = "Please select one or more files first.";
        animStatus.className = "status error";
        return;
    }
    if (!animManager) {
        animStatus.textContent = "Please load a VRM avatar first.";
        animStatus.className = "status error";
        return;
    }

    const { loadVRMAAnimation } = await import('./vrmaLoader.js');

    animBtn.disabled = true;
    let uploadedCount = 0;
    const errors = [];

    for (const file of files) {
        try {
            animStatus.textContent = `Uploading ${uploadedCount + 1}/${files.length}: ${file.name}…`;
            animStatus.className = "status";

            const res = await uploadFile(file, 'http://localhost:8765/api/upload/animation');

            animStatus.textContent = `Loading clip: ${file.name}…`;
            const clip = await loadVRMAAnimation(res.url, currentVrm);

            if (!clip) throw new Error(`No clip found in ${file.name}`);

            // createVRMAnimationClip always names the clip "clip" — override with filename
            const clipName = file.name.replace(/\.[^.]+$/, ''); // strip extension
            clip.name = clipName;

            animManager.loadClips([clip]);
            addAnimationButton(clip.name);
            if (!firstClipName) firstClipName = clip.name;
            uploadedCount++;
        } catch (e) {
            console.error(`[Dashboard] Failed for ${file.name}:`, e);
            errors.push(file.name);
        }
    }

    animBtn.disabled = false;

    if (uploadedCount > 0) {
        const errMsg = errors.length ? ` (${errors.length} failed)` : '';
        animStatus.textContent = `${uploadedCount} clip(s) loaded${errMsg}. Press a button above to play.`;
        animStatus.className = errors.length ? "status" : "status success";
    } else {
        animStatus.textContent = "All uploads failed.";
        animStatus.className = "status error";
    }
});

