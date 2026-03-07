/**
 * personaCreator.js — Persona Creator page orchestrator.
 *
 * Responsibilities:
 *  - Load /api/personas on startup and populate the selector
 *  - Create new personas
 *  - Upload VRM model and animations tied to the active persona
 *  - Load / play animations and expressions in the 3D viewport
 *  - Design a voice and preview speech generation
 */

import { scene, camera, renderer, controls, clock } from './scene.js';
import { loadModel } from './modelLoader.js';
import { AnimationManager } from './animationManager.js';
import { ExpressionManager } from './expressionManager.js';

const API = 'http://localhost:8765';

// ── DOM refs ─────────────────────────────────────────────────────────────────
const personaSelect = document.getElementById('persona-select');
const newPersonaBtn = document.getElementById('new-persona-btn');
const createForm = document.getElementById('create-form');
const newPersonaName = document.getElementById('new-persona-name');
const newPersonaDesc = document.getElementById('new-persona-desc');
const createPersonaBtn = document.getElementById('create-persona-btn');
const createStatus = document.getElementById('create-status');

const modelSection = document.getElementById('model-section');
const modelFile = document.getElementById('model-file');
const uploadModelBtn = document.getElementById('upload-model-btn');
const modelStatus = document.getElementById('model-status');

const animUploadSection = document.getElementById('anim-upload-section');
const animFile = document.getElementById('anim-file');
const uploadAnimBtn = document.getElementById('upload-anim-btn');
const animUploadStatus = document.getElementById('anim-upload-status');

const animSection = document.getElementById('anim-section');
const animButtons = document.getElementById('anim-buttons');
const animLoopChk = document.getElementById('anim-loop');

const exprSection = document.getElementById('expr-section');
const exprButtons = document.getElementById('expr-buttons');

const voiceDesignSection = document.getElementById('voice-design-section');
const voiceName = document.getElementById('voice-name');
const voiceGender = document.getElementById('voice-gender');
const voiceLanguage = document.getElementById('voice-language');
const voiceInstruct = document.getElementById('voice-instruct');
const voiceSample = document.getElementById('voice-sample');
const designVoiceBtn = document.getElementById('design-voice-btn');
const voiceDesignStatus = document.getElementById('voice-design-status');

const voicePreviewSection = document.getElementById('voice-preview-section');
const voiceText = document.getElementById('voice-text');
const speakBtn = document.getElementById('speak-btn');
const voicePreviewStatus = document.getElementById('voice-preview-status');
const voiceAudio = document.getElementById('voice-preview-audio');

// ── Viewport sizing ──────────────────────────────────────────────────────────
const viewport = document.getElementById('viewport');
function resizeViewport() {
    if (!viewport.clientWidth) return;
    camera.aspect = viewport.clientWidth / viewport.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(viewport.clientWidth, viewport.clientHeight);
}
window.addEventListener('resize', resizeViewport);
requestAnimationFrame(resizeViewport);

// ── Render loop ───────────────────────────────────────────────────────────────
let animManager = null;
let exprManager = new ExpressionManager();
let currentModel = null;
let currentVrm = null;
let activeSpeakerId = null;

function renderLoop() {
    requestAnimationFrame(renderLoop);
    const delta = clock.getDelta();
    controls.update();
    if (animManager) animManager.update(delta);
    if (currentVrm) currentVrm.update(delta);
    renderer.render(scene, camera);
}
renderLoop();

// ── State ─────────────────────────────────────────────────────────────────────
let activePersonaId = null;

// ── Persona list ──────────────────────────────────────────────────────────────
async function loadPersonas() {
    try {
        const res = await fetch(`${API}/api/personas`);
        const list = await res.json();
        personaSelect.innerHTML = '<option value="">— select or create —</option>';
        list.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            personaSelect.appendChild(opt);
        });
    } catch {
        personaSelect.innerHTML = '<option value="">⚠ Server unreachable</option>';
    }
}

personaSelect.addEventListener('change', async () => {
    const id = personaSelect.value;
    if (!id) { setActivePersona(null); return; }
    const res = await fetch(`${API}/api/personas/${id}`);
    if (!res.ok) return;
    const persona = await res.json();
    setActivePersona(persona);
});

function setActivePersona(persona) {
    activePersonaId = persona?.id ?? null;
    const hasPerson = !!persona;

    [modelSection, animUploadSection, voiceDesignSection].forEach(el =>
        el.classList.toggle('hidden', !hasPerson)
    );

    if (!hasPerson) {
        animSection.classList.add('hidden');
        exprSection.classList.add('hidden');
        voicePreviewSection.classList.add('hidden');
        return;
    }

    // Pre-fill voice name placeholder
    voiceName.placeholder = `${persona.name}_voice`;

    // If persona already has a model, load it
    if (persona.model) {
        loadAvatar(persona.model.url);
    }

    // Restore animation buttons
    animButtons.innerHTML = '';
    if (persona.animations?.length) {
        animSection.classList.remove('hidden');
        persona.animations.forEach(a => addAnimChip(a.name, a.url));
    } else {
        animSection.classList.add('hidden');
    }

    // Restore voice speaker
    if (persona.voice) {
        activeSpeakerId = persona.voice.speaker_id;
        voiceName.value = persona.voice.name;
        voiceGender.value = persona.voice.gender;
        voiceLanguage.value = persona.voice.language;
        voiceInstruct.value = persona.voice.instruct;
        voicePreviewSection.classList.remove('hidden');
        voiceDesignStatus.textContent = `Using saved voice: ${persona.voice.name}`;
        voiceDesignStatus.className = 'status ok';
    } else {
        activeSpeakerId = null;
        voicePreviewSection.classList.add('hidden');
    }
}

// ── Create persona ────────────────────────────────────────────────────────────
newPersonaBtn.addEventListener('click', () => {
    createForm.classList.toggle('visible');
});

createPersonaBtn.addEventListener('click', async () => {
    const name = newPersonaName.value.trim();
    if (!name) { createStatus.textContent = 'Name is required.'; createStatus.className = 'status err'; return; }

    createStatus.textContent = 'Creating…';
    createStatus.className = 'status';
    createPersonaBtn.disabled = true;

    try {
        const res = await fetch(`${API}/api/personas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: newPersonaDesc.value.trim() }),
        });
        if (!res.ok) throw new Error(await res.text());
        const p = await res.json();
        createStatus.textContent = `Created "${p.name}"`;
        createStatus.className = 'status ok';
        newPersonaName.value = '';
        newPersonaDesc.value = '';
        createForm.classList.remove('visible');
        await loadPersonas();
        personaSelect.value = p.id;
        setActivePersona(p);
    } catch (e) {
        createStatus.textContent = `Error: ${e.message}`;
        createStatus.className = 'status err';
    } finally {
        createPersonaBtn.disabled = false;
    }
});

// ── Model upload ──────────────────────────────────────────────────────────────
uploadModelBtn.addEventListener('click', async () => {
    const file = modelFile.files[0];
    if (!file || !activePersonaId) return;

    setStatus(modelStatus, 'Uploading…');
    uploadModelBtn.disabled = true;
    try {
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch(`${API}/api/personas/${activePersonaId}/model`, { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await res.text());
        const record = await res.json();
        setStatus(modelStatus, 'Uploaded. Loading model…', true);
        await loadAvatar(record.url);
    } catch (e) {
        setStatus(modelStatus, e.message, false);
    } finally {
        uploadModelBtn.disabled = false;
    }
});

// ── Load avatar ───────────────────────────────────────────────────────────────
async function loadAvatar(url) {
    try {
        setStatus(modelStatus, 'Loading 3D model…');
        const { model, skinnedMeshes, vrm } = await loadModel(url, prog => {
            const pct = prog.total ? Math.round(prog.loaded / prog.total * 100) : '…';
            setStatus(modelStatus, `Loading ${pct}%`);
        });

        if (currentModel) scene.remove(currentModel);
        currentModel = model;
        currentVrm = vrm;
        scene.add(model);

        animManager = new AnimationManager(model, null);
        exprManager.setMeshes(skinnedMeshes);

        setStatus(modelStatus, 'Model loaded', true);
        buildExpressionUI(vrm, exprManager);
    } catch (e) {
        setStatus(modelStatus, `Load failed: ${e.message}`, false);
    }
}

// ── Animation upload ──────────────────────────────────────────────────────────
uploadAnimBtn.addEventListener('click', async () => {
    const files = Array.from(animFile.files);
    if (!files.length || !activePersonaId || !animManager) {
        if (!animManager) setStatus(animUploadStatus, 'Load a model first.', false);
        return;
    }

    const { loadVRMAAnimation } = await import('./vrmaLoader.js');
    uploadAnimBtn.disabled = true;
    let ok = 0, fail = 0;

    for (const file of files) {
        try {
            setStatus(animUploadStatus, `Uploading ${ok + fail + 1}/${files.length}: ${file.name}…`);
            const fd = new FormData();
            fd.append('file', file);
            const res = await fetch(`${API}/api/personas/${activePersonaId}/animations`, { method: 'POST', body: fd });
            if (!res.ok) throw new Error(await res.text());
            const record = await res.json();

            setStatus(animUploadStatus, `Loading clip: ${file.name}…`);
            const clip = await loadVRMAAnimation(record.url, currentVrm);
            if (!clip) throw new Error('No clip found');

            clip.name = record.name;
            animManager.loadClips([clip]);
            addAnimChip(record.name, record.url);
            ok++;
        } catch (e) {
            console.error(`[PersonaCreator] ${file.name}:`, e);
            fail++;
        }
    }

    uploadAnimBtn.disabled = false;
    setStatus(animUploadStatus, `${ok} uploaded${fail ? `, ${fail} failed` : ''}.`, fail === 0);
});

// ── Animation chip ────────────────────────────────────────────────────────────
function addAnimChip(name, _url) {
    animSection.classList.remove('hidden');
    if (animButtons.querySelector(`[data-clip="${CSS.escape(name)}"]`)) return;

    const btn = document.createElement('button');
    btn.className = 'chip chip-anim';
    btn.textContent = name;
    btn.dataset.clip = name;
    btn.addEventListener('click', () => {
        if (!animManager) return;
        animManager.play(name, { loop: animLoopChk.checked, crossFadeDuration: 0.4 });
        animButtons.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
    });
    animButtons.appendChild(btn);
}

// ── Expressions ───────────────────────────────────────────────────────────────
function buildExpressionUI(vrm, em) {
    exprButtons.innerHTML = '';
    let names = [];

    if (vrm?.expressionManager?.expressions) {
        for (const e of vrm.expressionManager.expressions) {
            if (e.expressionName) names.push(e.expressionName);
        }
    } else {
        names = em.listExpressions();
    }

    if (!names.length) { exprSection.classList.add('hidden'); return; }
    names.sort();
    exprSection.classList.remove('hidden');

    names.forEach(name => {
        const btn = document.createElement('button');
        btn.className = 'chip chip-expr';
        btn.textContent = name;
        btn.addEventListener('click', () => {
            if (vrm?.expressionManager) {
                names.forEach(n => vrm.expressionManager.setValue(n, 0));
                vrm.expressionManager.setValue(name, 1);
            } else {
                em.clearExpressions();
                em.setExpression(name, 1);
            }
            exprButtons.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
        });
        exprButtons.appendChild(btn);
    });
}

// ── Voice design ──────────────────────────────────────────────────────────────
designVoiceBtn.addEventListener('click', async () => {
    const name = voiceName.value.trim() || (personaSelect.selectedOptions[0]?.text + '_voice');
    const instruct = voiceInstruct.value.trim();
    const sample = voiceSample.value.trim();
    if (!instruct || !sample) {
        setStatus(voiceDesignStatus, 'Please fill in instruct and sample text.', false);
        return;
    }
    setStatus(voiceDesignStatus, 'Designing voice… (may take a moment)');
    designVoiceBtn.disabled = true;

    try {
        const res = await fetch(`${API}/api/voice/design`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                persona_id: activePersonaId ?? '',
                name,
                gender: voiceGender.value,
                language: voiceLanguage.value,
                instruct,
                sample_text: sample,
            }),
        });
        if (!res.ok) throw new Error((await res.json()).detail ?? await res.text());
        const data = await res.json();
        activeSpeakerId = data.speaker_id;
        setStatus(voiceDesignStatus, `Voice ready! speaker_id: ${activeSpeakerId}`, true);
        voicePreviewSection.classList.remove('hidden');
    } catch (e) {
        setStatus(voiceDesignStatus, `Error: ${e.message}`, false);
    } finally {
        designVoiceBtn.disabled = false;
    }
});

// ── Voice preview ─────────────────────────────────────────────────────────────
speakBtn.addEventListener('click', async () => {
    const text = voiceText.value.trim();
    if (!text || !activeSpeakerId) {
        setStatus(voicePreviewStatus, !activeSpeakerId ? 'Design a voice first.' : 'Enter some text.', false);
        return;
    }
    setStatus(voicePreviewStatus, 'Generating speech…');
    speakBtn.disabled = true;

    try {
        const res = await fetch(`${API}/api/voice/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                speaker_id: activeSpeakerId,
                text,
                language: voiceLanguage.value,
            }),
        });
        if (!res.ok) throw new Error((await res.json()).detail ?? await res.text());
        const blob = await res.blob();
        voiceAudio.src = URL.createObjectURL(blob);
        voiceAudio.classList.add('visible');
        voiceAudio.play();
        setStatus(voicePreviewStatus, 'Playing…', true);
    } catch (e) {
        setStatus(voicePreviewStatus, `Error: ${e.message}`, false);
    } finally {
        speakBtn.disabled = false;
    }
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function setStatus(el, msg, ok = null) {
    el.textContent = msg;
    el.className = 'status' + (ok === true ? ' ok' : ok === false ? ' err' : '');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
loadPersonas();
