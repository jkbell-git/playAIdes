/**
 * creator.js — Persona Forge page orchestrator.
 *
 * Wires:
 *   • The 3D stage (creatorScene.js) to the current persona's VRM
 *   • Tab navigation (Identity / Vessel / Repertoire / Voice)
 *   • Persona CRUD via the /ws WebSocket (handled server-side by PlayAIdes)
 *   • File uploads (VRM, VRMA) via REST endpoints on IncarnationServer
 *   • Voice design + preview via the same WS channel
 */
import { createCreatorScene } from './creatorScene.js';
import { ConnectionManager } from './connectionManager.js';

// ── Constants ─────────────────────────────────────────────────────────────
const params = new URLSearchParams(window.location.search);
const WS_URL = params.get('ws') || 'ws://localhost:8765/ws';
const API_BASE = params.get('api') || 'http://localhost:8765';

// ── Scene setup ───────────────────────────────────────────────────────────
const viewerCanvas = document.getElementById('viewer');
const stage = createCreatorScene(viewerCanvas);

// ── State ─────────────────────────────────────────────────────────────────
/** @type {null | object} */
let activePersona = null;        // full persona dict
let personasById = new Map();    // id -> persona dict (lightweight)
let pendingSpeakerId = null;     // set after DESIGN, cleared after SAVE VOICE

// ── DOM refs ──────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const personaSelect = $('persona-select');
const newBtn        = $('new-persona-btn');
const saveBtn       = $('save-persona-btn');
const connDot       = $('conn-dot');
const stageName     = $('stage-name');

const pName       = $('p-name');
const pBackground = $('p-background');
const pGender     = $('p-gender');
const pLanguage   = $('p-language');
const traitsList  = $('traits-list');
const traitInput  = $('trait-input');
const traitAddBtn = $('trait-add-btn');

const modelDrop    = $('model-drop');
const modelFile    = $('model-file');
const modelStatus  = $('model-status');
const defaultAnims = $('default-anims');
const customAnims  = $('custom-anims');
const animDrop     = $('anim-drop');
const animFile     = $('anim-file');
const idleAnim     = $('idle-anim');

const vInstruct    = $('v-instruct');
const vSample      = $('v-sample');
const designBtn    = $('design-voice-btn');
const saveVoiceBtn = $('save-voice-btn');
const voiceRef     = $('voice-ref');
const vTestText    = $('v-test-text');
const testVoiceBtn = $('test-voice-btn');

const previewBtn   = $('preview-anim-btn');
const focusBtn     = $('focus-head-btn');
const resetBtn     = $('reset-cam-btn');

// ── Tabs ──────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
        const name = tab.dataset.tab;
        document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t === tab));
        document.querySelectorAll('.tab-panel').forEach((p) =>
            p.classList.toggle('active', p.dataset.panel === name)
        );
    });
});

// ── Connection ────────────────────────────────────────────────────────────
const conn = new ConnectionManager();

conn.addEventListener('connected', () => {
    connDot.classList.remove('error');
    connDot.classList.add('connected');
    toast('ok', 'Linked', 'Connected to PlayAIdes');
    conn.send('get_personas');
});
conn.addEventListener('disconnected', () => {
    connDot.classList.remove('connected');
});
conn.addEventListener('error', () => {
    connDot.classList.remove('connected');
    connDot.classList.add('error');
});

conn.addEventListener('personas_list', (ev) => {
    const list = ev.detail?.personas || [];
    populatePersonaSelect(list);
});

conn.addEventListener('persona_data', (ev) => {
    const p = ev.detail?.persona;
    if (p) setActivePersona(p);
});

conn.addEventListener('persona_created', (ev) => {
    const p = ev.detail?.persona;
    if (!p) return;
    toast('ok', 'Forged', `Persona "${p.name}" created`);
    conn.send('get_personas');
    // auto-select
    setTimeout(() => {
        personaSelect.value = p.id;
        conn.send('get_persona', { id: p.id });
    }, 80);
});

conn.addEventListener('persona_updated', (ev) => {
    const p = ev.detail?.persona;
    if (!p) return;
    toast('ok', 'Saved', `"${p.name}" updated`);
    conn.send('get_personas');
});

conn.addEventListener('voice_designed', (ev) => {
    const { speaker_id, ref_audio_url } = ev.detail || {};
    if (!speaker_id) return;
    pendingSpeakerId = speaker_id;
    saveVoiceBtn.disabled = false;
    if (ref_audio_url) {
        voiceRef.src = ref_audio_url;
        voiceRef.load();
    }
    toast('ok', 'Voice', `Designed speaker ${speaker_id.slice(0, 8)}…`);
});

conn.addEventListener('voice_tested', (ev) => {
    const url = ev.detail?.url;
    if (!url) return;
    voiceRef.src = url;
    voiceRef.load();
    voiceRef.play().catch(() => { /* autoplay may be blocked */ });
});

conn.addEventListener('voice_test_failed', (ev) => {
    toast('err', 'Voice', ev.detail?.error || 'Test failed');
});

conn.connect(WS_URL);

// ── Persona select + CRUD ─────────────────────────────────────────────────
function populatePersonaSelect(list) {
    personasById.clear();
    personaSelect.innerHTML = '<option value="">— select persona —</option>';
    for (const p of list) {
        personasById.set(p.id, p);
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        personaSelect.appendChild(opt);
    }
    if (activePersona && personasById.has(activePersona.id || '')) {
        personaSelect.value = activePersona.id;
    }
}

personaSelect.addEventListener('change', () => {
    const id = personaSelect.value;
    if (!id) { clearActivePersona(); return; }
    conn.send('get_persona', { id });
});

newBtn.addEventListener('click', () => {
    const name = prompt('Name your new persona:');
    if (!name) return;
    const description = prompt('A one-line background (optional):') || '';
    conn.send('create_persona', { name: name.trim(), description: description.trim() });
});

saveBtn.addEventListener('click', () => {
    if (!activePersona?.id) {
        toast('err', 'Save', 'No persona selected. Use + NEW first.');
        return;
    }
    const payload = buildPersonaPayload();
    conn.send('update_persona', { id: activePersona.id, ...payload });
});

function buildPersonaPayload() {
    const traits = [...traitsList.querySelectorAll('.trait-pill')]
        .map((el) => el.dataset.trait)
        .filter(Boolean);

    return {
        name: pName.value.trim() || 'Unnamed',
        back_ground: pBackground.value.trim(),
        psyche: { traits },
        gender: pGender.value,
        language: pLanguage.value,
        avatar: activePersona?.avatar ?? null,
        persona_voice: activePersona?.persona_voice ?? null,
        memories: activePersona?.memories ?? null,
        animations: activePersona?.animations ?? [],
    };
}

function setActivePersona(p) {
    activePersona = p;
    stageName.textContent = p.name || '— Unnamed —';
    pName.value       = p.name || '';
    pBackground.value = p.back_ground || '';
    pGender.value     = p.gender || 'Female';
    pLanguage.value   = p.language || 'English';
    renderTraits(p.psyche?.traits || []);
    renderCustomAnims(p.animations || [], p.avatar?.idle_animation || '');
    updateIdleSelect(p);

    // Voice fields
    vInstruct.value = (p.persona_voice?.voice_instruct || []).join(' ');
    vSample.value = vSample.value || 'Welcome, traveller. I am at your service.';
    pendingSpeakerId = null;
    saveVoiceBtn.disabled = true;
    voiceRef.removeAttribute('src');
    if (p.persona_voice?.speaker_uuid) {
        voiceRef.src = `${API_BASE}/api/speakers/${p.persona_voice.speaker_uuid}/ref_audio`;
    }

    // Load avatar into stage
    if (p.avatar?.model_url) {
        loadVesselFromUrl(p.avatar.model_url);
    } else {
        stage.clearVrm();
        modelStatus.textContent = 'No vessel bound to this persona yet.';
        modelStatus.className = 'status';
    }
}

function clearActivePersona() {
    activePersona = null;
    stageName.textContent = '— No Persona —';
    pName.value = pBackground.value = '';
    traitsList.innerHTML = '';
    customAnims.innerHTML = '';
    idleAnim.innerHTML = '<option value="">— none selected —</option>';
    vInstruct.value = '';
    voiceRef.removeAttribute('src');
    stage.clearVrm();
}

// ── Traits ────────────────────────────────────────────────────────────────
function renderTraits(traits) {
    traitsList.innerHTML = '';
    traits.forEach(addTraitPill);
}
function addTraitPill(trait) {
    const pill = document.createElement('span');
    pill.className = 'trait-pill';
    pill.dataset.trait = trait;
    pill.innerHTML = `${escape(trait)} <span class="rm" title="remove">✕</span>`;
    pill.querySelector('.rm').addEventListener('click', () => pill.remove());
    traitsList.appendChild(pill);
}
function commitTrait() {
    const v = traitInput.value.trim();
    if (!v) return;
    addTraitPill(v);
    traitInput.value = '';
}
traitAddBtn.addEventListener('click', commitTrait);
traitInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); commitTrait(); }
});

// ── Model upload ──────────────────────────────────────────────────────────
modelDrop.addEventListener('click', () => modelFile.click());
['dragenter', 'dragover'].forEach((evt) =>
    modelDrop.addEventListener(evt, (e) => { e.preventDefault(); modelDrop.classList.add('dragover'); })
);
['dragleave', 'drop'].forEach((evt) =>
    modelDrop.addEventListener(evt, (e) => { e.preventDefault(); modelDrop.classList.remove('dragover'); })
);
modelDrop.addEventListener('drop', (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (f) uploadModel(f);
});
modelFile.addEventListener('change', (e) => {
    const f = e.target.files?.[0];
    if (f) uploadModel(f);
});

async function uploadModel(file) {
    if (!activePersona?.id) {
        toast('err', 'Upload', 'Select or create a persona first.');
        return;
    }
    if (!file.name.toLowerCase().endsWith('.vrm')) {
        toast('err', 'Upload', 'Only .vrm files are accepted here.');
        return;
    }
    modelStatus.textContent = `Uploading ${file.name}…`;
    modelStatus.className = 'status';
    try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(`${API_BASE}/api/personas/${activePersona.id}/model`, {
            method: 'POST', body: form,
        });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const data = await res.json();
        modelStatus.textContent = `✓ Vessel bound: ${data.filename}`;
        modelStatus.className = 'status ok';
        toast('ok', 'Vessel', `${data.filename} uploaded`);
        loadVesselFromUrl(data.url);
        // Persist to persona record
        activePersona.avatar = { ...(activePersona.avatar || {}), model_url: data.url };
    } catch (err) {
        modelStatus.textContent = `✕ Upload failed: ${err.message}`;
        modelStatus.className = 'status err';
        toast('err', 'Vessel', err.message);
    }
}

async function loadVesselFromUrl(url) {
    try {
        await stage.loadVrm(url);
    } catch (err) {
        console.error(err);
        toast('err', 'Vessel', `Failed to render: ${err.message}`);
    }
}

// ── Animations ────────────────────────────────────────────────────────────
async function loadDefaults() {
    try {
        const res = await fetch(`${API_BASE}/api/default_animations`);
        const data = await res.json();
        defaultAnims.innerHTML = '';
        for (const anim of data.animations || []) {
            const li = document.createElement('li');
            li.textContent = anim.name;
            li.dataset.name = anim.name;
            li.dataset.url = anim.url;
            li.addEventListener('click', () => selectDefault(li));
            defaultAnims.appendChild(li);
        }
        refreshIdleOptions();
    } catch (err) {
        toast('err', 'Animations', `Load defaults failed: ${err.message}`);
    }
}
loadDefaults();

function selectDefault(li) {
    li.classList.toggle('selected');
    refreshIdleOptions();
}

function renderCustomAnims(anims, idle) {
    customAnims.innerHTML = '';
    for (const a of anims) {
        const li = document.createElement('li');
        li.textContent = a.name;
        li.dataset.name = a.name;
        li.dataset.url = a.url;
        li.addEventListener('click', () => { li.classList.toggle('selected'); refreshIdleOptions(); });
        customAnims.appendChild(li);
    }
    refreshIdleOptions(idle);
}

function refreshIdleOptions(selectedIdle) {
    const names = new Set();
    [...defaultAnims.querySelectorAll('li'), ...customAnims.querySelectorAll('li')]
        .forEach((li) => names.add(li.dataset.name));
    idleAnim.innerHTML = '<option value="">— none —</option>';
    for (const n of [...names].sort()) {
        const o = document.createElement('option');
        o.value = n; o.textContent = n;
        idleAnim.appendChild(o);
    }
    const current = selectedIdle ?? activePersona?.avatar?.idle_animation ?? '';
    if (current) idleAnim.value = current;
}

idleAnim.addEventListener('change', () => {
    if (!activePersona) return;
    activePersona.avatar = activePersona.avatar || {};
    activePersona.avatar.idle_animation = idleAnim.value || 'idle';
});

// Animation upload
animDrop.addEventListener('click', () => animFile.click());
['dragenter', 'dragover'].forEach((evt) =>
    animDrop.addEventListener(evt, (e) => { e.preventDefault(); animDrop.classList.add('dragover'); })
);
['dragleave', 'drop'].forEach((evt) =>
    animDrop.addEventListener(evt, (e) => { e.preventDefault(); animDrop.classList.remove('dragover'); })
);
animDrop.addEventListener('drop', (e) => {
    const files = [...(e.dataTransfer?.files || [])].filter((f) => f.name.toLowerCase().endsWith('.vrma'));
    if (files.length) uploadAnimations(files);
});
animFile.addEventListener('change', (e) => {
    const files = [...(e.target.files || [])];
    if (files.length) uploadAnimations(files);
});

async function uploadAnimations(files) {
    if (!activePersona?.id) {
        toast('err', 'Upload', 'Select or create a persona first.');
        return;
    }
    for (const file of files) {
        try {
            const form = new FormData();
            form.append('file', file);
            const res = await fetch(`${API_BASE}/api/personas/${activePersona.id}/animations`, {
                method: 'POST', body: form,
            });
            if (!res.ok) throw new Error(`${res.status}`);
            const data = await res.json();
            toast('ok', 'Animation', `${data.name} uploaded`);
            activePersona.animations = activePersona.animations || [];
            if (!activePersona.animations.find((a) => a.name === data.name)) {
                activePersona.animations.push({ name: data.name, url: data.url });
            }
            renderCustomAnims(activePersona.animations, activePersona.avatar?.idle_animation);
        } catch (err) {
            toast('err', 'Animation', `${file.name}: ${err.message}`);
        }
    }
}

function updateIdleSelect(p) {
    refreshIdleOptions(p.avatar?.idle_animation || '');
}

// ── Stage controls ────────────────────────────────────────────────────────
previewBtn.addEventListener('click', () => {
    // Find first "selected" custom animation, else idle
    const sel = customAnims.querySelector('li.selected') || defaultAnims.querySelector('li.selected');
    if (!sel) { toast('err', 'Preview', 'Select an animation first.'); return; }
    toast('ok', 'Preview', `Playing "${sel.dataset.name}" — WIP, not yet wired to mixer`);
    // TODO: wire to stage's animation mixer once default animation loading is
    // extracted from Incarnation into creatorScene.
});
focusBtn.addEventListener('click', () => stage.focusOnFace());
resetBtn.addEventListener('click', () => stage.resetCamera());

// ── Voice design ──────────────────────────────────────────────────────────
designBtn.addEventListener('click', () => {
    if (!activePersona?.id) {
        toast('err', 'Voice', 'Select a persona first.');
        return;
    }
    const instruct = vInstruct.value.trim();
    if (!instruct) {
        toast('err', 'Voice', 'Give the voice a style instruction first.');
        return;
    }
    conn.send('design_voice', {
        name: activePersona.name,
        gender: pGender.value,
        language: pLanguage.value,
        instruct,
        sample_text: vSample.value || 'Hello.',
    });
    designBtn.disabled = true;
    setTimeout(() => (designBtn.disabled = false), 4000);
});

saveVoiceBtn.addEventListener('click', () => {
    if (!activePersona?.id || !pendingSpeakerId) return;
    activePersona.persona_voice = {
        speaker_uuid: pendingSpeakerId,
        voice_instruct: [vInstruct.value.trim()].filter(Boolean),
    };
    conn.send('update_persona', { id: activePersona.id, ...buildPersonaPayload() });
    pendingSpeakerId = null;
    saveVoiceBtn.disabled = true;
});

testVoiceBtn.addEventListener('click', () => {
    const speakerId = pendingSpeakerId || activePersona?.persona_voice?.speaker_uuid;
    if (!speakerId) {
        toast('err', 'Voice', 'Design or select a voice first.');
        return;
    }
    const text = vTestText.value.trim() || vSample.value || 'Hello.';
    conn.send('test_voice', {
        speaker_id: speakerId,
        text,
        language: pLanguage.value,
    });
});

// ── Toasts ────────────────────────────────────────────────────────────────
const toastBar = document.getElementById('toast-bar');
function toast(kind, prefix, text) {
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.innerHTML = `<span class="prefix">${escape(prefix)}</span> ${escape(text)}`;
    toastBar.appendChild(el);
    setTimeout(() => {
        el.style.transition = 'opacity .3s ease';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 350);
    }, 2600);
}

// ── Utilities ─────────────────────────────────────────────────────────────
function escape(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}
