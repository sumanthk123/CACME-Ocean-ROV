const API_BASE = window.location.origin;
let currentSonar = null;
let ws = null;
let prevBlobUrl = null;
let frameCount = 0;
let lastFpsTime = Date.now();
let applyDebounceTimer = null;
let currentMode = 'single';
let snapshotBlobUrl = null;
let sweepInterval = null;

// Slider parameter definitions
const SLIDER_PARAMS = [
    'attenuation', 'gau_noise_param', 'ray_noise_param',
    'intensity_offset', 'intensity_gain', 'central_peak', 'central_std'
];

const PARAM_DEFAULTS = {
    binning_method: 'sum',
    normalizing_method: 'range',
    attenuation: 0.1,
    gau_noise_param: 0.2,
    ray_noise_param: 0.05,
    intensity_offset: 0.0,
    intensity_gain: 1.0,
    central_peak: 2.0,
    central_std: 0.001
};

const PARAM_RANGES = {
    attenuation: { min: 0, max: 1 },
    gau_noise_param: { min: 0, max: 1 },
    ray_noise_param: { min: 0, max: 0.5 },
    intensity_offset: { min: -1, max: 1 },
    intensity_gain: { min: 0.1, max: 5 },
    central_peak: { min: 0, max: 10 },
    central_std: { min: 0.0001, max: 0.1 }
};

// Built-in presets
const BUILTIN_PRESETS = {
    'Default': { ...PARAM_DEFAULTS },
    'Clean': {
        binning_method: 'sum', normalizing_method: 'range',
        attenuation: 0.05, gau_noise_param: 0, ray_noise_param: 0,
        intensity_offset: 0, intensity_gain: 1.5, central_peak: 0, central_std: 0.001
    },
    'Noisy': {
        binning_method: 'sum', normalizing_method: 'range',
        attenuation: 0.2, gau_noise_param: 0.5, ray_noise_param: 0.15,
        intensity_offset: 0, intensity_gain: 1.2, central_peak: 4, central_std: 0.005
    },
    'High Gain': {
        binning_method: 'sum', normalizing_method: 'all',
        attenuation: 0.05, gau_noise_param: 0.1, ray_noise_param: 0.02,
        intensity_offset: 0.1, intensity_gain: 3.0, central_peak: 1, central_std: 0.001
    },
    'Long Range': {
        binning_method: 'mean', normalizing_method: 'range',
        attenuation: 0.3, gau_noise_param: 0.15, ray_noise_param: 0.08,
        intensity_offset: 0.05, intensity_gain: 2.0, central_peak: 3, central_std: 0.003
    }
};

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
    fetchSonarList();
    setInterval(fetchSonarList, 5000);

    document.getElementById('sonar-select').addEventListener('change', onSonarSelected);
    document.getElementById('apply-btn').addEventListener('click', applyParams);
    document.getElementById('download-btn').addEventListener('click', downloadRawData);
    document.getElementById('reset-all-btn').addEventListener('click', resetAll);

    // Mode buttons
    document.getElementById('mode-single').addEventListener('click', () => setMode('single'));
    document.getElementById('mode-compare').addEventListener('click', () => setMode('compare'));
    document.getElementById('mode-sweep').addEventListener('click', () => setMode('sweep'));

    // Compare controls
    document.getElementById('snapshot-btn').addEventListener('click', takeSnapshot);
    document.getElementById('swap-ab-btn').addEventListener('click', swapAB);

    // Sweep controls
    document.getElementById('sweep-start-btn').addEventListener('click', startSweep);
    document.getElementById('sweep-stop-btn').addEventListener('click', stopSweep);
    document.getElementById('sweep-param').addEventListener('change', updateSweepRange);

    // Sync sliders <-> number inputs
    SLIDER_PARAMS.forEach(param => {
        const slider = document.getElementById(`${param}-slider`);
        const num = document.getElementById(`${param}-num`);
        slider.addEventListener('input', () => {
            num.value = slider.value;
            onParamChanged();
        });
        num.addEventListener('input', () => {
            slider.value = num.value;
            onParamChanged();
        });
    });

    // Dropdown auto-apply
    ['binning_method', 'normalizing_method'].forEach(id => {
        document.getElementById(id).addEventListener('change', onParamChanged);
    });

    // Reset buttons
    document.querySelectorAll('.reset-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const param = btn.dataset.param;
            const def = PARAM_DEFAULTS[param];
            document.getElementById(`${param}-slider`).value = def;
            document.getElementById(`${param}-num`).value = def;
            onParamChanged();
        });
    });

    // Save preset
    document.getElementById('save-preset-btn').addEventListener('click', savePreset);

    loadPresets();
    renderPresets();
    updateSweepRange();
});

// ===== VIEW MODES =====
function setMode(mode) {
    currentMode = mode;
    ['single', 'compare', 'sweep'].forEach(m => {
        document.getElementById(`view-${m}`).classList.toggle('hidden', m !== mode);
        document.getElementById(`mode-${m}`).classList.toggle('btn-toggle', m === mode);
    });
    if (mode === 'sweep') stopSweep();
}

// ===== PARAMS =====
function onParamChanged() {
    if (!document.getElementById('auto-apply').checked) return;
    clearTimeout(applyDebounceTimer);
    applyDebounceTimer = setTimeout(applyParams, 150);
}

function populateControls(params) {
    if (params.binning_method) document.getElementById('binning_method').value = params.binning_method;
    if (params.normalizing_method) document.getElementById('normalizing_method').value = params.normalizing_method;
    SLIDER_PARAMS.forEach(p => {
        if (params[p] !== undefined) {
            document.getElementById(`${p}-slider`).value = params[p];
            document.getElementById(`${p}-num`).value = params[p];
        }
    });
}

function gatherParams() {
    const params = {
        binning_method: document.getElementById('binning_method').value,
        normalizing_method: document.getElementById('normalizing_method').value,
    };
    SLIDER_PARAMS.forEach(p => {
        params[p] = parseFloat(document.getElementById(`${p}-num`).value);
    });
    return params;
}

async function applyParams() {
    if (!currentSonar) return;
    const params = gatherParams();
    try {
        await fetch(`${API_BASE}/api/sonar/${currentSonar}/params`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
    } catch (e) {
        console.error('Failed to apply params:', e);
    }
}

function resetAll() {
    populateControls(PARAM_DEFAULTS);
    onParamChanged();
}

// ===== PRESETS =====
function getCustomPresets() {
    try { return JSON.parse(localStorage.getItem('oceansim_presets') || '{}'); }
    catch { return {}; }
}

function saveCustomPresets(presets) {
    localStorage.setItem('oceansim_presets', JSON.stringify(presets));
}

function loadPresets() { /* presets loaded on render */ }

function renderPresets() {
    const grid = document.getElementById('preset-grid');
    grid.innerHTML = '';
    const all = { ...BUILTIN_PRESETS, ...getCustomPresets() };
    for (const [name, params] of Object.entries(all)) {
        const chip = document.createElement('div');
        chip.className = 'preset-chip';
        chip.innerHTML = name;
        // Only custom presets get delete button
        if (!BUILTIN_PRESETS[name]) {
            const del = document.createElement('span');
            del.className = 'delete-preset';
            del.textContent = '\u00d7';
            del.addEventListener('click', (e) => {
                e.stopPropagation();
                const custom = getCustomPresets();
                delete custom[name];
                saveCustomPresets(custom);
                renderPresets();
            });
            chip.appendChild(del);
        }
        chip.addEventListener('click', () => {
            populateControls(params);
            onParamChanged();
            // Highlight active
            grid.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
        });
        grid.appendChild(chip);
    }
}

function savePreset() {
    const input = document.getElementById('preset-name-input');
    const name = input.value.trim();
    if (!name) return;
    const custom = getCustomPresets();
    custom[name] = gatherParams();
    saveCustomPresets(custom);
    input.value = '';
    renderPresets();
}

// ===== SONAR LIST =====
async function fetchSonarList() {
    try {
        const resp = await fetch(`${API_BASE}/api/sonar/list`);
        const data = await resp.json();
        const select = document.getElementById('sonar-select');
        const prev = select.value;
        select.innerHTML = '';
        if (data.sonars.length === 0) {
            select.innerHTML = '<option value="">-- no sonars --</option>';
            return;
        }
        data.sonars.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.name;
            opt.textContent = s.name;
            select.appendChild(opt);
        });
        if (prev && data.sonars.some(s => s.name === prev)) {
            select.value = prev;
        } else {
            select.value = data.sonars[0].name;
            onSonarSelected();
        }
    } catch (e) {}
}

async function onSonarSelected() {
    const name = document.getElementById('sonar-select').value;
    if (!name) return;
    currentSonar = name;
    try {
        const resp = await fetch(`${API_BASE}/api/sonar/${name}/params`);
        const params = await resp.json();
        populateControls(params);
    } catch (e) {}
    try {
        const resp = await fetch(`${API_BASE}/api/sonar/list`);
        const data = await resp.json();
        const info = data.sonars.find(s => s.name === name);
        if (info) {
            document.getElementById('sonar-info').innerHTML = `
                <p>Range: ${info.min_range}m - ${info.max_range}m (res: ${info.range_res}m)</p>
                <p>FOV: ${info.hori_fov} x ${info.vert_fov} deg | ${info.hori_res}px</p>
                <p>Map: ${info.sonar_map_shape[0]} x ${info.sonar_map_shape[1]} bins</p>
            `;
        }
    } catch (e) {}
    connectWebSocket(name);
}

// ===== WEBSOCKET =====
function connectWebSocket(name) {
    if (ws) { ws.close(); ws = null; }
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws/sonar/${name}`;
    setWsStatus('waiting', 'Connecting...');
    ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
        setWsStatus('connected', 'Live');
        frameCount = 0;
        lastFpsTime = Date.now();
    };

    ws.onmessage = (event) => {
        const blob = new Blob([event.data], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);

        // Update all relevant image elements
        const targets = ['sonar-image'];
        if (currentMode === 'compare') targets.push('compare-img-a');
        if (currentMode === 'sweep') targets.push('sweep-image');

        targets.forEach(id => {
            const img = document.getElementById(id);
            if (img) img.src = url;
        });

        // Clean up previous blob
        if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
        prevBlobUrl = url;

        // FPS counter
        frameCount++;
        const now = Date.now();
        if (now - lastFpsTime >= 1000) {
            document.getElementById('fps-counter').textContent = `${frameCount} fps`;
            frameCount = 0;
            lastFpsTime = now;
        }
    };

    ws.onclose = () => {
        setWsStatus('disconnected', 'Disconnected');
        setTimeout(() => { if (currentSonar === name) connectWebSocket(name); }, 2000);
    };

    ws.onerror = () => setWsStatus('disconnected', 'Error');
}

function setWsStatus(state, text) {
    document.getElementById('ws-dot').className = `status-dot ${state}`;
    document.getElementById('ws-status').textContent = text;
}

// ===== A/B COMPARE =====
function takeSnapshot() {
    if (!currentSonar) return;
    // Grab current frame as snapshot for B
    const imgA = document.getElementById('compare-img-a');
    if (imgA.src) {
        const imgB = document.getElementById('compare-img-b');
        imgB.src = imgA.src;
        if (snapshotBlobUrl) URL.revokeObjectURL(snapshotBlobUrl);
        snapshotBlobUrl = imgA.src;
        // Label with current params summary
        const params = gatherParams();
        const summary = `gain=${params.intensity_gain} noise=${params.gau_noise_param}`;
        document.getElementById('compare-b-name').textContent = summary;
        document.getElementById('compare-a-name').textContent = 'Live';
    }
}

function swapAB() {
    const imgA = document.getElementById('compare-img-a');
    const imgB = document.getElementById('compare-img-b');
    const nameA = document.getElementById('compare-a-name');
    const nameB = document.getElementById('compare-b-name');
    const tmpSrc = imgB.src;
    const tmpName = nameB.textContent;
    imgB.src = imgA.src;
    nameB.textContent = nameA.textContent;
    imgA.src = tmpSrc;
    nameA.textContent = tmpName;
}

// ===== PARAMETER SWEEP =====
function updateSweepRange() {
    const param = document.getElementById('sweep-param').value;
    const range = PARAM_RANGES[param];
    if (range) {
        document.getElementById('sweep-from').value = range.min;
        document.getElementById('sweep-to').value = range.max;
    }
}

function startSweep() {
    if (!currentSonar) return;
    stopSweep();

    const param = document.getElementById('sweep-param').value;
    const from = parseFloat(document.getElementById('sweep-from').value);
    const to = parseFloat(document.getElementById('sweep-to').value);
    const steps = parseInt(document.getElementById('sweep-steps').value);
    const speed = parseInt(document.getElementById('sweep-speed').value);

    const paramLabel = document.getElementById('sweep-param').selectedOptions[0].textContent;
    document.getElementById('sweep-param-label').textContent = paramLabel;
    document.getElementById('sweep-start-btn').classList.add('hidden');
    document.getElementById('sweep-stop-btn').classList.remove('hidden');

    let step = 0;
    let direction = 1; // ping-pong

    sweepInterval = setInterval(async () => {
        const t = step / (steps - 1);
        const value = from + t * (to - from);

        // Update the slider and number display
        const slider = document.getElementById(`${param}-slider`);
        const num = document.getElementById(`${param}-num`);
        if (slider) slider.value = value;
        if (num) num.value = value.toFixed(4);

        document.getElementById('sweep-param-value').textContent = value.toFixed(4);

        // Apply
        const params = gatherParams();
        params[param] = value;
        try {
            await fetch(`${API_BASE}/api/sonar/${currentSonar}/params`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params),
            });
        } catch (e) {}

        // Ping-pong
        step += direction;
        if (step >= steps) { direction = -1; step = steps - 1; }
        if (step < 0) { direction = 1; step = 0; }
    }, speed);
}

function stopSweep() {
    if (sweepInterval) {
        clearInterval(sweepInterval);
        sweepInterval = null;
    }
    document.getElementById('sweep-start-btn').classList.remove('hidden');
    document.getElementById('sweep-stop-btn').classList.add('hidden');
}

// ===== DOWNLOAD =====
async function downloadRawData() {
    if (!currentSonar) return;
    try {
        const resp = await fetch(`${API_BASE}/api/sonar/${currentSonar}/data`);
        const data = await resp.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `sonar_data_${currentSonar}.json`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {}
}
