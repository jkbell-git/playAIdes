/**
 * debugPanel.js — opt-in (?debug=1) camera tuner.
 *
 * Six axes — camera X/Y/Z and look-target X/Y/Z — each with an editable number
 * field AND a slider, plus a live pose readout + copy button. Lets a shot be
 * hand-framed on-device (type exact values or drag) and the numbers baked into
 * scene.js (focusOnHead) and the camera director's shots. Non-kiosk only (it
 * drives OrbitControls; kiosk hands the camera to the director). Does nothing
 * unless ?debug=1 is present.
 *
 * Axes (Three.js, avatar facing +Z toward the camera):
 *   X = left(-)/right(+),  Y = down(-)/up(+),  Z = behind(-)/in-front(+).
 *
 * @param {import('three').PerspectiveCamera} camera
 * @param {{target: import('three').Vector3, update: () => void, addEventListener: Function}} controls  OrbitControls
 */
export function createDebugPanel(camera, controls) {
    const params = new URLSearchParams(window.location.search);
    if (params.get('debug') !== '1') return null;

    // [id, label, min, max]; cam* drive camera.position, tgt* drive controls.target.
    const ROWS = [
        ['cx', 'cam X', -3, 3],
        ['cy', 'cam Y', 0, 3],
        ['cz', 'cam Z', -3, 3],
        ['tx', 'tgt X', -2, 2],
        ['ty', 'tgt Y', 0, 2.5],
        ['tz', 'tgt Z', -2, 2],
    ];

    const panel = document.createElement('div');
    panel.id = 'debug-panel';
    panel.style.cssText =
        'position:fixed;top:64px;right:14px;z-index:300;width:248px;' +
        'background:rgba(10,8,18,.92);border:1px solid #c9a24b;border-radius:8px;' +
        'color:#f4ecd8;font:12px/1.5 monospace;padding:10px 12px;pointer-events:auto;';
    panel.innerHTML =
        '<div style="color:#c9a24b;font-weight:bold;margin-bottom:6px">CAMERA DEBUG</div>' +
        ROWS.map(([id, label, min, max]) =>
            '<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">' +
              `<span style="width:42px">${label}</span>` +
              `<input id="dbg-${id}-n" type="number" step="0.01" ` +
                'style="width:56px;background:#0a0812;color:#f4ecd8;border:1px solid #555;font:inherit">' +
              `<input id="dbg-${id}" type="range" min="${min}" max="${max}" step="0.01" style="flex:1">` +
            '</div>',
        ).join('') +
        '<pre id="dbg-out" style="margin:8px 0 4px;white-space:pre-wrap;color:#8aa0b8"></pre>' +
        '<button id="dbg-copy" style="width:100%;padding:4px;cursor:pointer">copy pose</button>';
    document.body.appendChild(panel);

    const q = (sel) => panel.querySelector(sel);
    const sliders = {}, nums = {};
    ROWS.forEach(([id]) => { sliders[id] = q(`#dbg-${id}`); nums[id] = q(`#dbg-${id}-n`); });
    const out = q('#dbg-out');

    function renderReadout() {
        const p = camera.position, t = controls.target;
        out.textContent =
            `pos  ${p.x.toFixed(2)}, ${p.y.toFixed(2)}, ${p.z.toFixed(2)}\n` +
            `tgt  ${t.x.toFixed(2)}, ${t.y.toFixed(2)}, ${t.z.toFixed(2)}`;
    }

    // Push the typed/dragged values onto the camera (numbers are the source of
    // truth, so typed values outside a slider's range still apply).
    function apply() {
        const g = (id) => parseFloat(nums[id].value) || 0;
        controls.target.set(g('tx'), g('ty'), g('tz'));
        camera.position.set(g('cx'), g('cy'), g('cz'));
        controls.update();
        renderReadout();
    }

    // Pull the current camera/target into both controls (on init + manual orbit).
    function syncControls() {
        const p = camera.position, t = controls.target;
        const v = { cx: p.x, cy: p.y, cz: p.z, tx: t.x, ty: t.y, tz: t.z };
        ROWS.forEach(([id]) => {
            const s = v[id].toFixed(2);
            nums[id].value = s;
            sliders[id].value = s;
        });
        renderReadout();
    }

    ROWS.forEach(([id]) => {
        sliders[id].addEventListener('input', () => { nums[id].value = sliders[id].value; apply(); });
        nums[id].addEventListener('input', () => { sliders[id].value = nums[id].value; apply(); });
    });
    q('#dbg-copy').addEventListener('click', () => {
        if (navigator.clipboard) navigator.clipboard.writeText(out.textContent);
    });
    controls.addEventListener('end', syncControls);   // track manual orbits too

    // focusOnHead may still be easing when this runs; resync after it settles.
    syncControls();
    setTimeout(syncControls, 1500);
    return { syncControls };
}
