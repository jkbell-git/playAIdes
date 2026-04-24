/**
 * personaCreator.js — Persona Creator page orchestrator.
 * NOW POWERED BY WEBSOCKETS via ConnectionManager
 */

import { scene, camera, renderer, controls, clock } from './scene.js';
import { loadModel } from './modelLoader.js';
import { AnimationManager } from './animationManager.js';
import { ExpressionManager } from './expressionManager.js';
import { ConnectionManager } from './connectionManager.js';
import { VisemeManager } from './visemeManager.js';
import { LipSyncManager } from './lipSyncManager.js';

// HTTP Upload API base
const HTTP_API = 'http://localhost:8765';

// WebSocket connection
const conn = new ConnectionManager('ws://localhost:8765/ws');

// ── DOM refs ─────────────────────────────────────────────────────────────────
const personaSelect = document.getElementById('persona-select');

// Unified editor
const personaEditor = document.getElementById('persona-editor');
const editPersonaName = document.getElementById('edit-persona-name');
const editPersonaDesc = document.getElementById('edit-persona-desc');
const savePersonaBtn = document.getElementById('save-persona-btn');
const savePersonaStatus = document.getElementById('save-persona-status');

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

const defaultAnimSection = document.getElementById('default-anim-section');
const defaultAnimButtons = document.getElementById('default-anim-buttons');

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
const refAudioPlayer = document.getElementById('ref-audio-player');
const saveVoiceBtn = document.getElementById('save-voice-btn');

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
let visemeManager = new VisemeManager();
let lipSyncManager = null;

function renderLoop() {
    requestAnimationFrame(renderLoop);
    const delta = clock.getDelta();
    controls.update();
    if (animManager) animManager.update(delta);
    if (lipSyncManager) lipSyncManager.update();
    if (currentVrm) currentVrm.update(delta);
    renderer.render(scene, camera);
}
renderLoop();

// ── State ─────────────────────────────────────────────────────────────────────
let activePersona = null;
let activePersonaId = null;

// ── WebSocket Listens ─────────────────────────────────────────────────────────
conn.addEventListener('connected', () => {
    console.log("Connected to PlayAIdes server");
    loadPersonas();
});

conn.addEventListener('disconnected', () => {
    personaSelect.innerHTML = '<option value="">⚠ Server unreachable</option>';
});

conn.addEventListener('personas_list', (e) => {
    const list = e.detail.personas;
    personaSelect.innerHTML = '<option value="">— select a persona —</option><option value="__new__">── Create New Persona ──</option>';
    list.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        personaSelect.appendChild(opt);
    });
    // Reselect active persona if it exists
    if (activePersonaId) {
        personaSelect.value = activePersonaId;
    }
});

conn.addEventListener('persona_data', (e) => {
    setActivePersona(e.detail.persona);
});

conn.addEventListener('persona_created', (e) => {
    const p = e.detail.persona;
    savePersonaStatus.textContent = `Created "${p.name}"`;
    savePersonaStatus.className = 'status ok';
    
    // Refresh the list
    loadPersonas();
    
    // Assume ID and make it active
    activePersonaId = p.id;
    setActivePersona(p);
    
    savePersonaBtn.disabled = false;
});

conn.addEventListener('persona_updated', (e) => {
    const p = e.detail.persona;
    
    savePersonaStatus.textContent = `Saved "${p.name}"`;
    savePersonaStatus.className = 'status ok';
    savePersonaBtn.disabled = false;

    if (activePersonaId === p.id) {
        setActivePersona(p); // update local state and UI
    }
});

conn.addEventListener('model_uploaded', (e) => {
    // Expected to reload the current persona
    if (activePersonaId === e.detail.persona_id) {
        setStatus(modelStatus, 'Uploaded. Loading model…', true);
        loadAvatar(e.detail.url);
        conn.send('get_persona', { id: activePersonaId }); // fetch new JSON state
    }
});

conn.addEventListener('animation_uploaded', (e) => {
    if (activePersonaId === e.detail.persona_id) {
        conn.send('get_persona', { id: activePersonaId }); // refresh list of anims
    }
});

conn.addEventListener('voice_designed', (e) => {
    activeSpeakerId = e.detail.speaker_id;
    setStatus(voiceDesignStatus, `Voice design sampled! Preview ready.`, true);
    saveVoiceBtn.style.display = 'block';
    voicePreviewSection.classList.remove('hidden');
    designVoiceBtn.disabled = false;

    // Show ref audio player with the designed voice sample
    if (e.detail.ref_audio_url) {
        refAudioPlayer.src = e.detail.ref_audio_url;
        refAudioPlayer.style.display = 'block';
    }
});

conn.addEventListener('voice_tested', (e) => {
    voiceAudio.src = e.detail.url; // URL provided by backend
    voiceAudio.classList.add('visible');

    // Start lip sync from the audio element when it plays
    voiceAudio.onplay = () => {
        if (lipSyncManager && currentVrm) {
            lipSyncManager.startFromAudioElement(voiceAudio);
        }
    };

    // Handle autoplay policy: .play() returns a promise that may reject
    const playPromise = voiceAudio.play();
    if (playPromise !== undefined) {
        playPromise.then(() => {
            setStatus(voicePreviewStatus, 'Playing audio…', true);
        }).catch(() => {
            // Autoplay blocked — audio controls are visible, user can click play
            setStatus(voicePreviewStatus, 'Audio ready — click ▶ to play', true);
        });
    }
    speakBtn.disabled = false;
});

conn.addEventListener('voice_test_failed', (e) => {
    setStatus(voicePreviewStatus, `Error: ${e.detail.error}`, false);
    speakBtn.disabled = false;
});

// Connect WebSocket
conn.connect();

// Load default animations via REST
async function loadDefaultAnimations() {
    try {
        const res = await fetch(`${HTTP_API}/api/default_animations`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.animations && data.animations.length > 0) {
            defaultAnimSection.classList.remove('hidden');
            data.animations.forEach(a => addAnimChip(a.name, a.url, true));
        }
    } catch (e) {
        console.warn('Could not load default animations:', e);
    }
}
loadDefaultAnimations();

// ── Persona list ──────────────────────────────────────────────────────────────
function loadPersonas() {
    conn.send('get_personas');
}

personaSelect.addEventListener('change', () => {
    const id = personaSelect.value;
    activePersonaId = id;
    if (!id) { 
        setActivePersona(null); 
        return; 
    }
    if (id === '__new__') {
        setActivePersona(null); 
        return;
    }
    conn.send('get_persona', { id });
});

function setActivePersona(persona) {
    activePersona = persona;
    const isNew = activePersonaId === '__new__';
    const hasPerson = !!persona || isNew;
    
    // Determine visibility
    personaEditor.classList.toggle('visible', hasPerson);
    [modelSection, animUploadSection, voiceDesignSection].forEach(el =>
        el.classList.toggle('hidden', !hasPerson || isNew) // file uploads disabled for brand new
    );
    
    if (isNew) {
        // Show create mode
        savePersonaBtn.textContent = 'Create Persona';
        editPersonaName.value = '';
        editPersonaName.readOnly = false;
        editPersonaDesc.value = '';
        savePersonaStatus.textContent = '';
        savePersonaStatus.className = 'status';
        
        // Remove active model from viewport
        if (currentModel) {
            scene.remove(currentModel);
            currentModel = null;
            currentVrm = null;
            animManager = null;
        }
        
    } else if (hasPerson) {
        // Show Edit mode
        savePersonaBtn.textContent = 'Save Changes';
        editPersonaName.value = persona.name || '';
        editPersonaName.readOnly = true; // changing id/name breaks paths for now
        editPersonaDesc.value = persona.back_ground || '';
        savePersonaStatus.textContent = '';
        savePersonaStatus.className = 'status';
        
        voiceName.placeholder = `${persona.name}_voice`;
    }

    if (!hasPerson || isNew) {
        animSection.classList.add('hidden');
        exprSection.classList.add('hidden');
        voicePreviewSection.classList.add('hidden');
        saveVoiceBtn.style.display = 'none';
        refAudioPlayer.style.display = 'none';
        return;
    }

    // Load Model directly from Python's avatar dict
    if (persona.avatar && persona.avatar.model_url) {
        loadAvatar(persona.avatar.model_url);
    } else {
        // Clear scene if no model
        if (currentModel) {
            scene.remove(currentModel);
            currentModel = null;
            currentVrm = null;
            animManager = null;
        }
        animSection.classList.add('hidden');
        exprSection.classList.add('hidden');
    }

    // Restore animation buttons (saved in persona.animations)
    animButtons.innerHTML = '';
    if (persona.animations && persona.animations.length) {
        animSection.classList.remove('hidden');
        persona.animations.forEach(a => addAnimChip(a.name, a.url));
    } else {
        animSection.classList.add('hidden');
    }

    // Restore voice speaker (saved in persona.persona_voice)
    if (persona.persona_voice && persona.persona_voice.speaker_uuid) {
        activeSpeakerId = persona.persona_voice.speaker_uuid;

        // Populate voice design form fields from saved data
        voiceLanguage.value = persona.language || "English";
        voiceGender.value = persona.gender || "Female";
        voiceName.value = persona.name ? `${persona.name}_voice` : '';
        // Join the saved voice_instruct array into the textarea
        if (persona.persona_voice.voice_instruct && persona.persona_voice.voice_instruct.length) {
            voiceInstruct.value = persona.persona_voice.voice_instruct.join('\n');
        } else {
            voiceInstruct.value = '';
        }

        voicePreviewSection.classList.remove('hidden');
        saveVoiceBtn.style.display = 'block';
        setStatus(voiceDesignStatus, `Using saved voice: ${activeSpeakerId}`, true);

        // Show the reference audio player for the existing designed voice
        const refUrl = `${HTTP_API}/api/speakers/${activeSpeakerId}/ref_audio`;
        refAudioPlayer.src = refUrl;
        refAudioPlayer.style.display = 'block';
    } else {
        activeSpeakerId = null;
        saveVoiceBtn.style.display = 'none';
        voicePreviewSection.classList.add('hidden');
        refAudioPlayer.style.display = 'none';
        voiceInstruct.value = '';
        voiceName.value = '';
        setStatus(voiceDesignStatus, ''); // clear status
    }
}

// ── Create or Save persona ──────────────────────────────────────────────────
savePersonaBtn.addEventListener('click', () => {
    const name = editPersonaName.value.trim();
    const desc = editPersonaDesc.value.trim();
    if (!name) { savePersonaStatus.textContent = 'Name is required.'; savePersonaStatus.className = 'status err'; return; }

    if (activePersonaId === '__new__') {
        savePersonaStatus.textContent = 'Creating…';
        savePersonaStatus.className = 'status';
        savePersonaBtn.disabled = true;
        conn.send('create_persona', { name, description: desc });
    } else {
        savePersonaStatus.textContent = 'Saving changes…';
        savePersonaStatus.className = 'status';
        savePersonaBtn.disabled = true;
        
        // Push the background onto the activePersona object
        activePersona.back_ground = desc;
        conn.send('update_persona', activePersona);
    }
});

// ── Model upload HTTP ─────────────────────────────────────────────────────────
uploadModelBtn.addEventListener('click', async () => {
    const file = modelFile.files[0];
    if (!file || !activePersonaId) return;

    setStatus(modelStatus, 'Uploading…');
    uploadModelBtn.disabled = true;
    try {
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch(`${HTTP_API}/api/personas/${activePersonaId}/model`, { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await res.text());
        // Do not call loadAvatar here; wait for WebSocket model_uploaded callback from backend
        setStatus(modelStatus, 'Model uploaded. Awaiting backend confirmation...', true);
    } catch (e) {
        setStatus(modelStatus, e.message, false);
    } finally {
        uploadModelBtn.disabled = false;
    }
});

let isAvatarLoading = false;
async function loadAvatar(url) {
    if (isAvatarLoading) return;
    // Only reload if URL changed
    if (currentModel && currentModel.userData.avatarUrl === url) return;

    try {
        isAvatarLoading = true;
        setStatus(modelStatus, 'Loading 3D model…');
        const { model, skinnedMeshes, vrm } = await loadModel(url, prog => {
            const pct = prog.total ? Math.round(prog.loaded / prog.total * 100) : '…';
            setStatus(modelStatus, `Loading ${pct}%`);
        });

        if (currentModel) {
            scene.remove(currentModel);
            // Free memory if necessary, but at least remove from scene immediately
        }
        currentModel = model;
        currentModel.userData.avatarUrl = url;
        currentVrm = vrm;
        scene.add(model);

        animManager = new AnimationManager(model, null);
        exprManager.setMeshes(skinnedMeshes);
        visemeManager.setMeshes(skinnedMeshes);
        if (vrm && vrm.expressionManager) {
            visemeManager.setExpressionManager(vrm.expressionManager);
        }

        // Stop existing lip sync and create a new one for this model
        if (lipSyncManager) lipSyncManager.stop();
        lipSyncManager = new LipSyncManager(visemeManager);

        setStatus(modelStatus, 'Model loaded', true);
        buildExpressionUI(vrm, exprManager);
    } catch (e) {
        setStatus(modelStatus, `Load failed: ${e.message}`, false);
    } finally {
        isAvatarLoading = false;
    }
}

// ── Animation upload HTTP ─────────────────────────────────────────────────────
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
            const res = await fetch(`${HTTP_API}/api/personas/${activePersonaId}/animations`, { method: 'POST', body: fd });
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
async function loadAndPlayVRMA(name, url, btn) {
    if (!animManager || !currentVrm) return;
    
    // Check if we already loaded it
    const existing = animManager.clips.get(name);
    if (existing) {
        animManager.play(name, { loop: animLoopChk.checked, crossFadeDuration: 0.4 });
        document.querySelectorAll('.chip-anim').forEach(c => c.classList.remove('active'));
        btn.classList.add('active');
        return;
    }

    // Need to load it first
    try {
        const { loadVRMAAnimation } = await import('./vrmaLoader.js');
        const clip = await loadVRMAAnimation(url, currentVrm);
        if (clip) {
            clip.name = name;
            animManager.loadClips([clip]);
            animManager.play(name, { loop: animLoopChk.checked, crossFadeDuration: 0.4 });
            document.querySelectorAll('.chip-anim').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
        }
    } catch(e) {
        console.error("Failed to load animation:", e);
    }
}

function addAnimChip(name, url, isDefault=false) {
    if (isDefault) {
        if (defaultAnimButtons.querySelector(`[data-clip="${CSS.escape(name)}"]`)) return;
    } else {
        animSection.classList.remove('hidden');
        if (animButtons.querySelector(`[data-clip="${CSS.escape(name)}"]`)) return;
    }

    const btn = document.createElement('button');
    btn.className = 'chip chip-anim';
    btn.textContent = name;
    btn.dataset.clip = name;
    btn.addEventListener('click', () => {
        loadAndPlayVRMA(name, url, btn);
    });
    
    if (isDefault) {
        defaultAnimButtons.appendChild(btn);
    } else {
        animButtons.appendChild(btn);
    }
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

// ── Voice design WS ───────────────────────────────────────────────────────────
designVoiceBtn.addEventListener('click', () => {
    const name = voiceName.value.trim() || (personaSelect.selectedOptions[0]?.text + '_voice');
    const instruct = voiceInstruct.value.trim();
    const sample = voiceSample.value.trim();
    if (!instruct || !sample) {
        setStatus(voiceDesignStatus, 'Please fill in instruct and sample text.', false);
        return;
    }
    
    setStatus(voiceDesignStatus, 'Designing voice… (may take a moment)');
    designVoiceBtn.disabled = true;

    conn.send('design_voice', {
        name,
        gender: voiceGender.value,
        language: voiceLanguage.value,
        instruct,
        sample_text: sample,
    });
});

saveVoiceBtn.addEventListener('click', () => {
    if (!activePersona || !activeSpeakerId) return;

    // Build voice_instruct array from textarea (one entry per non-empty line)
    const instructLines = voiceInstruct.value
        .split('\n')
        .map(l => l.trim())
        .filter(l => l.length > 0);

    // Send update_persona with the new voice structure — persists to persona.json
    activePersona.persona_voice = {
        speaker_uuid: activeSpeakerId,
        voice_instruct: instructLines
    };
    activePersona.language = voiceLanguage.value;
    activePersona.gender = voiceGender.value;

    conn.send('update_persona', activePersona);
    setStatus(voiceDesignStatus, 'Voice saved to persona JSON.', true);
});

// ── Voice preview WS ──────────────────────────────────────────────────────────
speakBtn.addEventListener('click', () => {
    const text = voiceText.value.trim();
    if (!text || !activeSpeakerId) {
        setStatus(voicePreviewStatus, !activeSpeakerId ? 'Design a voice first or save it.' : 'Enter some text.', false);
        return;
    }
    
    setStatus(voicePreviewStatus, 'Generating speech segment…');
    speakBtn.disabled = true;

    conn.send('test_voice', {
        speaker_id: activeSpeakerId,
        text,
        language: voiceLanguage.value,
    });
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function setStatus(el, msg, ok = null) {
    el.textContent = msg;
    el.className = 'status' + (ok === true ? ' ok' : ok === false ? ' err' : '');
}
