const API_BASE = window.location.origin;
let currentSonar = null;
let currentCamera = null;
let currentFeed = 'sonar'; // 'sonar' or 'camera'
let ws = null;
let prevBlobUrl = null;
let frameCount = 0;
let lastFpsTime = Date.now();
let applyDebounceTimer = null;
let envWaterDebounceTimer = null;
let envLightingDebounceTimer = null;
let currentMode = 'single';
let snapshotBlobUrl = null;

// Sonar slider parameter definitions
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

// ===== ENVIRONMENT: WATER =====
const ENV_WATER_PARAMS = [
    'backscatter_r', 'backscatter_g', 'backscatter_b',
    'backscatter_coeff_r', 'backscatter_coeff_g', 'backscatter_coeff_b',
    'attenuation_coeff_r', 'attenuation_coeff_g', 'attenuation_coeff_b'
];

const ENV_WATER_DEFAULTS = {
    backscatter_r: 0.0, backscatter_g: 0.31, backscatter_b: 0.24,
    backscatter_coeff_r: 0.05, backscatter_coeff_g: 0.05, backscatter_coeff_b: 0.2,
    attenuation_coeff_r: 0.05, attenuation_coeff_g: 0.05, attenuation_coeff_b: 0.05,
};

const ENV_WATER_PRESETS = {
    'Clear Tropical': {
        backscatter_r: 0.0, backscatter_g: 0.05, backscatter_b: 0.1,
        backscatter_coeff_r: 0.01, backscatter_coeff_g: 0.01, backscatter_coeff_b: 0.02,
        attenuation_coeff_r: 0.02, attenuation_coeff_g: 0.02, attenuation_coeff_b: 0.02,
    },
    'Coastal': {
        backscatter_r: 0.0, backscatter_g: 0.31, backscatter_b: 0.24,
        backscatter_coeff_r: 0.05, backscatter_coeff_g: 0.05, backscatter_coeff_b: 0.2,
        attenuation_coeff_r: 0.05, attenuation_coeff_g: 0.05, attenuation_coeff_b: 0.05,
    },
    'Murky Harbor': {
        backscatter_r: 0.15, backscatter_g: 0.4, backscatter_b: 0.3,
        backscatter_coeff_r: 0.2, backscatter_coeff_g: 0.2, backscatter_coeff_b: 0.35,
        attenuation_coeff_r: 0.15, attenuation_coeff_g: 0.15, attenuation_coeff_b: 0.12,
    },
    'Deep Ocean': {
        backscatter_r: 0.0, backscatter_g: 0.1, backscatter_b: 0.2,
        backscatter_coeff_r: 0.02, backscatter_coeff_g: 0.02, backscatter_coeff_b: 0.05,
        attenuation_coeff_r: 0.08, attenuation_coeff_g: 0.06, attenuation_coeff_b: 0.03,
    },
    'Near Zero Vis': {
        backscatter_r: 0.3, backscatter_g: 0.5, backscatter_b: 0.4,
        backscatter_coeff_r: 0.4, backscatter_coeff_g: 0.4, backscatter_coeff_b: 0.5,
        attenuation_coeff_r: 0.3, attenuation_coeff_g: 0.3, attenuation_coeff_b: 0.25,
    },
};

// ===== ENVIRONMENT: ACOUSTIC (SONAR WATER) =====
const ENV_ACOUSTIC_PARAMS = ['acoustic_attenuation', 'gau_noise', 'ray_noise'];

const ENV_ACOUSTIC_DEFAULTS = {
    acoustic_attenuation: 0.2,
    gau_noise: 0.05,
    ray_noise: 0.02,
};

let envAcousticDebounceTimer = null;

// ===== ENVIRONMENT: LIGHTING =====
const ENV_LIGHTING_PARAMS = ['lighting_intensity', 'lighting_color_temperature', 'lighting_elevation', 'lighting_azimuth'];

const ENV_LIGHTING_DEFAULTS = {
    lighting_intensity: 50000.0,
    lighting_color_temperature: 6500.0,
    lighting_elevation: 45.0,
    lighting_azimuth: 0.0,
    lighting_enabled: true,
};

const ENV_LIGHTING_PRESETS = {
    'Shallow Sunlit': {
        lighting_intensity: 100000, lighting_color_temperature: 5500,
        lighting_elevation: 70, lighting_azimuth: 0, lighting_enabled: true,
    },
    'Deep Ocean': {
        lighting_intensity: 5000, lighting_color_temperature: 8000,
        lighting_elevation: 80, lighting_azimuth: 0, lighting_enabled: true,
    },
    'Twilight Zone': {
        lighting_intensity: 1000, lighting_color_temperature: 9000,
        lighting_elevation: 30, lighting_azimuth: -45, lighting_enabled: true,
    },
    'Night': {
        lighting_intensity: 200, lighting_color_temperature: 4000,
        lighting_elevation: 10, lighting_azimuth: 0, lighting_enabled: true,
    },
};

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
    fetchSonarList();
    fetchCameraList();
    setInterval(fetchSonarList, 15000);
    setInterval(fetchCameraList, 15000);
    fetchWaterParams();
    fetchLightingParams();

    // Feed selector
    document.getElementById('feed-select').addEventListener('change', onFeedChanged);

    document.getElementById('sonar-select').addEventListener('change', onSonarSelected);
    document.getElementById('camera-select').addEventListener('change', onCameraSelected);
    document.getElementById('apply-btn').addEventListener('click', applyParams);
    document.getElementById('download-btn').addEventListener('click', downloadRawData);
    document.getElementById('reset-all-btn').addEventListener('click', resetAll);

    // Mode buttons
    document.getElementById('mode-single').addEventListener('click', () => setMode('single'));
    document.getElementById('mode-compare').addEventListener('click', () => setMode('compare'));

    // Compare controls
    document.getElementById('snapshot-btn').addEventListener('click', takeSnapshot);
    document.getElementById('swap-ab-btn').addEventListener('click', swapAB);

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Sync sliders <-> number inputs (sonar)
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

    // Reset buttons (sonar)
    document.querySelectorAll('.reset-btn:not(.env-reset)').forEach(btn => {
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

    // ===== Environment: Water slider sync =====
    ENV_WATER_PARAMS.forEach(param => {
        const slider = document.getElementById(`${param}-slider`);
        const num = document.getElementById(`${param}-num`);
        if (slider && num) {
            slider.addEventListener('input', () => { num.value = slider.value; onWaterParamChanged(); });
            num.addEventListener('input', () => { slider.value = num.value; onWaterParamChanged(); });
        }
    });

    // Environment reset buttons
    document.querySelectorAll('.env-reset').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const param = btn.dataset.envParam;
            if (param.startsWith('lighting_')) {
                const def = ENV_LIGHTING_DEFAULTS[param];
                document.getElementById(`${param}-slider`).value = def;
                document.getElementById(`${param}-num`).value = def;
                onLightingParamChanged();
            } else if (ENV_ACOUSTIC_DEFAULTS[param] !== undefined) {
                const def = ENV_ACOUSTIC_DEFAULTS[param];
                document.getElementById(`${param}-slider`).value = def;
                document.getElementById(`${param}-num`).value = def;
                onAcousticParamChanged();
            } else {
                const def = ENV_WATER_DEFAULTS[param];
                document.getElementById(`${param}-slider`).value = def;
                document.getElementById(`${param}-num`).value = def;
                onWaterParamChanged();
            }
        });
    });

    document.getElementById('env-water-reset-btn').addEventListener('click', resetWaterDefaults);

    // ===== Environment: Lighting slider sync =====
    ENV_LIGHTING_PARAMS.forEach(param => {
        const slider = document.getElementById(`${param}-slider`);
        const num = document.getElementById(`${param}-num`);
        if (slider && num) {
            slider.addEventListener('input', () => { num.value = slider.value; onLightingParamChanged(); });
            num.addEventListener('input', () => { slider.value = num.value; onLightingParamChanged(); });
        }
    });

    document.getElementById('lighting_enabled').addEventListener('change', onLightingParamChanged);
    document.getElementById('env-lighting-reset-btn').addEventListener('click', resetLightingDefaults);

    // Collapsible sections
    document.querySelectorAll('.section-toggle').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const target = document.getElementById(toggle.dataset.target);
            if (target) {
                target.classList.toggle('collapsed');
                toggle.classList.toggle('collapsed');
            }
        });
    });

    // ===== Environment: Acoustic slider sync =====
    ENV_ACOUSTIC_PARAMS.forEach(param => {
        const slider = document.getElementById(`${param}-slider`);
        const num = document.getElementById(`${param}-num`);
        if (slider && num) {
            slider.addEventListener('input', () => { num.value = slider.value; onAcousticParamChanged(); });
            num.addEventListener('input', () => { slider.value = num.value; onAcousticParamChanged(); });
        }
    });

    document.getElementById('env-acoustic-reset-btn').addEventListener('click', resetAcousticDefaults);

    fetchAcousticParams();
    renderWaterConditionPresets();
    renderWaterPresets();
    renderLightingPresets();
});

// ===== FEED SELECTOR =====
function onFeedChanged() {
    currentFeed = document.getElementById('feed-select').value;
    document.getElementById('sonar-select-label').classList.toggle('hidden', currentFeed !== 'sonar');
    document.getElementById('camera-select-label').classList.toggle('hidden', currentFeed !== 'camera');

    // Close existing websocket and reconnect to the right feed
    if (ws) { ws.close(); ws = null; }

    if (currentFeed === 'sonar' && currentSonar) {
        connectWebSocket('sonar', currentSonar);
    } else if (currentFeed === 'camera' && currentCamera) {
        connectWebSocket('camera', currentCamera);
    }
}

// ===== VIEW MODES =====
function setMode(mode) {
    currentMode = mode;
    ['single', 'compare'].forEach(m => {
        document.getElementById(`view-${m}`).classList.toggle('hidden', m !== mode);
        document.getElementById(`mode-${m}`).classList.toggle('btn-toggle', m === mode);
    });
}

// ===== SONAR PARAMS =====
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

function loadPresets() {}

function renderPresets() {
    const grid = document.getElementById('preset-grid');
    grid.innerHTML = '';
    const all = { ...BUILTIN_PRESETS, ...getCustomPresets() };
    for (const [name, params] of Object.entries(all)) {
        const chip = document.createElement('div');
        chip.className = 'preset-chip';
        chip.innerHTML = name;
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
    if (currentFeed === 'sonar') {
        connectWebSocket('sonar', name);
    }
}

// ===== CAMERA LIST =====
async function fetchCameraList() {
    try {
        const resp = await fetch(`${API_BASE}/api/camera/list`);
        const data = await resp.json();
        const select = document.getElementById('camera-select');
        const prev = select.value;
        select.innerHTML = '';
        if (data.cameras.length === 0) {
            select.innerHTML = '<option value="">-- no cameras --</option>';
            return;
        }
        data.cameras.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        });
        if (prev && data.cameras.includes(prev)) {
            select.value = prev;
        } else {
            select.value = data.cameras[0];
            onCameraSelected();
        }
    } catch (e) {}
}

function onCameraSelected() {
    const name = document.getElementById('camera-select').value;
    if (!name) return;
    currentCamera = name;
    if (currentFeed === 'camera') {
        connectWebSocket('camera', name);
    }
}

// ===== WEBSOCKET =====
function connectWebSocket(type, name) {
    if (ws) { ws.close(); ws = null; }
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws/${type}/${name}`;
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

        const targets = ['sonar-image'];
        if (currentMode === 'compare') targets.push('compare-img-a');

        targets.forEach(id => {
            const img = document.getElementById(id);
            if (img) img.src = url;
        });

        if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
        prevBlobUrl = url;

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
        setTimeout(() => {
            if (currentFeed === 'sonar' && currentSonar === name) connectWebSocket('sonar', name);
            if (currentFeed === 'camera' && currentCamera === name) connectWebSocket('camera', name);
        }, 2000);
    };

    ws.onerror = () => setWsStatus('disconnected', 'Error');
}

function setWsStatus(state, text) {
    document.getElementById('ws-dot').className = `status-dot ${state}`;
    document.getElementById('ws-status').textContent = text;
}

// ===== A/B COMPARE =====
function takeSnapshot() {
    const imgA = document.getElementById('compare-img-a');
    if (imgA.src) {
        const imgB = document.getElementById('compare-img-b');
        imgB.src = imgA.src;
        if (snapshotBlobUrl) URL.revokeObjectURL(snapshotBlobUrl);
        snapshotBlobUrl = imgA.src;
        document.getElementById('compare-b-name').textContent = 'Snapshot';
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

// ===== ENVIRONMENT: WATER =====
function onWaterParamChanged() {
    const autoApply = document.getElementById('env-auto-apply');
    if (!autoApply || !autoApply.checked) return;
    clearTimeout(envWaterDebounceTimer);
    envWaterDebounceTimer = setTimeout(applyWaterParams, 150);
}

function gatherWaterParams() {
    const params = {};
    ENV_WATER_PARAMS.forEach(p => {
        params[p] = parseFloat(document.getElementById(`${p}-num`).value);
    });
    return params;
}

function populateWaterControls(params) {
    ENV_WATER_PARAMS.forEach(p => {
        if (params[p] !== undefined) {
            const slider = document.getElementById(`${p}-slider`);
            const num = document.getElementById(`${p}-num`);
            if (slider) slider.value = params[p];
            if (num) num.value = params[p];
        }
    });
}

async function applyWaterParams() {
    const params = gatherWaterParams();
    try {
        await fetch(`${API_BASE}/api/environment/water`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
    } catch (e) {
        console.error('Failed to apply water params:', e);
    }
}

async function fetchWaterParams() {
    try {
        const resp = await fetch(`${API_BASE}/api/environment/water`);
        const params = await resp.json();
        populateWaterControls(params);
    } catch (e) {}
}

function resetWaterDefaults() {
    populateWaterControls(ENV_WATER_DEFAULTS);
    onWaterParamChanged();
}

function renderWaterPresets() {
    const grid = document.getElementById('water-preset-grid');
    if (!grid) return;
    grid.innerHTML = '';
    for (const [name, params] of Object.entries(ENV_WATER_PRESETS)) {
        const chip = document.createElement('div');
        chip.className = 'preset-chip';
        chip.textContent = name;
        chip.addEventListener('click', () => {
            populateWaterControls(params);
            onWaterParamChanged();
            grid.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
        });
        grid.appendChild(chip);
    }
}

// ===== ENVIRONMENT: LIGHTING =====
function onLightingParamChanged() {
    const autoApply = document.getElementById('env-auto-apply');
    if (!autoApply || !autoApply.checked) return;
    clearTimeout(envLightingDebounceTimer);
    envLightingDebounceTimer = setTimeout(applyLightingParams, 150);
}

function gatherLightingParams() {
    return {
        intensity: parseFloat(document.getElementById('lighting_intensity-num').value),
        color_temperature: parseFloat(document.getElementById('lighting_color_temperature-num').value),
        elevation: parseFloat(document.getElementById('lighting_elevation-num').value),
        azimuth: parseFloat(document.getElementById('lighting_azimuth-num').value),
        enabled: document.getElementById('lighting_enabled').value === 'true',
    };
}

function populateLightingControls(params) {
    const mapping = {
        intensity: 'lighting_intensity',
        color_temperature: 'lighting_color_temperature',
        elevation: 'lighting_elevation',
        azimuth: 'lighting_azimuth',
    };
    for (const [apiKey, htmlKey] of Object.entries(mapping)) {
        if (params[apiKey] !== undefined) {
            const slider = document.getElementById(`${htmlKey}-slider`);
            const num = document.getElementById(`${htmlKey}-num`);
            if (slider) slider.value = params[apiKey];
            if (num) num.value = params[apiKey];
        }
    }
    if (params.enabled !== undefined) {
        document.getElementById('lighting_enabled').value = params.enabled ? 'true' : 'false';
    }
}

function populateLightingControlsFromPreset(params) {
    ENV_LIGHTING_PARAMS.forEach(p => {
        if (params[p] !== undefined) {
            const slider = document.getElementById(`${p}-slider`);
            const num = document.getElementById(`${p}-num`);
            if (slider) slider.value = params[p];
            if (num) num.value = params[p];
        }
    });
    if (params.lighting_enabled !== undefined) {
        document.getElementById('lighting_enabled').value = params.lighting_enabled ? 'true' : 'false';
    }
}

async function applyLightingParams() {
    const params = gatherLightingParams();
    try {
        await fetch(`${API_BASE}/api/environment/lighting`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
    } catch (e) {
        console.error('Failed to apply lighting params:', e);
    }
}

async function fetchLightingParams() {
    try {
        const resp = await fetch(`${API_BASE}/api/environment/lighting`);
        const params = await resp.json();
        populateLightingControls(params);
    } catch (e) {}
}

function resetLightingDefaults() {
    populateLightingControlsFromPreset(ENV_LIGHTING_DEFAULTS);
    onLightingParamChanged();
}

function renderLightingPresets() {
    const grid = document.getElementById('lighting-preset-grid');
    if (!grid) return;
    grid.innerHTML = '';
    for (const [name, params] of Object.entries(ENV_LIGHTING_PRESETS)) {
        const chip = document.createElement('div');
        chip.className = 'preset-chip';
        chip.textContent = name;
        chip.addEventListener('click', () => {
            populateLightingControlsFromPreset(params);
            onLightingParamChanged();
            grid.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
        });
        grid.appendChild(chip);
    }
}

// ===== ENVIRONMENT: ACOUSTIC (SONAR WATER) =====
function onAcousticParamChanged() {
    const autoApply = document.getElementById('env-auto-apply');
    if (!autoApply || !autoApply.checked) return;
    clearTimeout(envAcousticDebounceTimer);
    envAcousticDebounceTimer = setTimeout(applyAcousticParams, 150);
}

function gatherAcousticParams() {
    const params = {};
    ENV_ACOUSTIC_PARAMS.forEach(p => {
        params[p] = parseFloat(document.getElementById(`${p}-num`).value);
    });
    return params;
}

function populateAcousticControls(params) {
    ENV_ACOUSTIC_PARAMS.forEach(p => {
        if (params[p] !== undefined) {
            const slider = document.getElementById(`${p}-slider`);
            const num = document.getElementById(`${p}-num`);
            if (slider) slider.value = params[p];
            if (num) num.value = params[p];
        }
    });
}

async function applyAcousticParams() {
    const params = gatherAcousticParams();
    try {
        await fetch(`${API_BASE}/api/environment/sonar_water`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params),
        });
    } catch (e) {
        console.error('Failed to apply acoustic params:', e);
    }
}

async function fetchAcousticParams() {
    try {
        const resp = await fetch(`${API_BASE}/api/environment/sonar_water`);
        const params = await resp.json();
        populateAcousticControls(params);
    } catch (e) {}
}

function resetAcousticDefaults() {
    populateAcousticControls(ENV_ACOUSTIC_DEFAULTS);
    onAcousticParamChanged();
}

// ===== WATER CONDITION PRESETS =====
function renderWaterConditionPresets() {
    const grid = document.getElementById('water-condition-preset-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const presets = {
        'clear_ocean': 'Clear Ocean',
        'coastal': 'Coastal',
        'murky_harbor': 'Murky Harbor',
        'turbid_river': 'Turbid River',
    };
    for (const [key, label] of Object.entries(presets)) {
        const chip = document.createElement('div');
        chip.className = 'preset-chip';
        chip.textContent = label;
        chip.addEventListener('click', async () => {
            try {
                const resp = await fetch(`${API_BASE}/api/environment/water_preset/${key}`, { method: 'PUT' });
                const data = await resp.json();
                if (data.success) {
                    // Refresh both optical and acoustic controls from server
                    fetchWaterParams();
                    fetchAcousticParams();
                    grid.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    // Clear active state on old optical-only presets
                    const waterGrid = document.getElementById('water-preset-grid');
                    if (waterGrid) waterGrid.querySelectorAll('.preset-chip').forEach(c => c.classList.remove('active'));
                }
            } catch (e) {
                console.error('Failed to apply water condition preset:', e);
            }
        });
        grid.appendChild(chip);
    }
}

// ===== OBJECTS TAB: MATERIALS =====
let _materialsCache = null;

async function fetchMaterials() {
    try {
        const resp = await fetch(`${API_BASE}/api/materials`);
        const data = await resp.json();
        _materialsCache = data.materials;
        const select = document.getElementById("obj-material-select");
        // Preserve the "Custom" option at the top
        select.innerHTML = '<option value="custom">Custom</option>';
        for (const [name, info] of Object.entries(data.materials)) {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = `${name.charAt(0).toUpperCase() + name.slice(1)} (R=${info.reflectivity})`;
            select.appendChild(opt);
        }
    } catch (e) {
        console.error("Failed to fetch materials:", e);
    }
}

function onMaterialChanged() {
    const materialSelect = document.getElementById("obj-material-select");
    const material = materialSelect.value;
    const reflSlider = document.getElementById("obj-reflectivity-slider");
    const reflNum = document.getElementById("obj-reflectivity-num");

    if (material !== "custom" && _materialsCache && _materialsCache[material]) {
        const refl = _materialsCache[material].reflectivity;
        reflSlider.value = refl;
        reflNum.value = refl;
        reflSlider.disabled = true;
        reflNum.disabled = true;
    } else {
        reflSlider.disabled = false;
        reflNum.disabled = false;
    }
}

// ===== OBJECTS TAB =====
async function fetchAssets() {
    try {
        const select = document.getElementById("obj-asset-select");
        select.innerHTML = "";
        
        // Built-in primitives (instant spawn, no file loading)
        const builtins = ["Cube", "Sphere", "Cylinder", "Cone", "Capsule"];
        const optgroup1 = document.createElement("optgroup");
        optgroup1.label = "Built-in Shapes";
        builtins.forEach(name => {
            const opt = document.createElement("option");
            opt.value = name;
            opt.textContent = name;
            optgroup1.appendChild(opt);
        });
        select.appendChild(optgroup1);
        
        // USD assets from server
        const resp = await fetch(`${API_BASE}/api/environment/assets`);
        const data = await resp.json();
        if (data.assets.length > 0) {
            const optgroup2 = document.createElement("optgroup");
            optgroup2.label = "USD Assets";
            data.assets.forEach(a => {
                const opt = document.createElement("option");
                opt.value = a.full_path;
                opt.textContent = `${a.name} (${a.rel_path})`;
                optgroup2.appendChild(opt);
            });
            select.appendChild(optgroup2);
        }
    } catch (e) {
        console.error("Failed to fetch assets:", e);
    }
}

async function spawnObject() {
    const assetPath = document.getElementById("obj-asset-select").value;
    const primName = document.getElementById("obj-name").value.trim();
    if (!assetPath || !primName) { alert("Select an asset and enter a name"); return; }

    const materialSelect = document.getElementById("obj-material-select");
    const material = materialSelect.value !== "custom" ? materialSelect.value : null;

    const body = {
        asset_path: assetPath,
        prim_name: primName,
        position: [
            parseFloat(document.getElementById("obj-pos-x").value),
            parseFloat(document.getElementById("obj-pos-y").value),
            parseFloat(document.getElementById("obj-pos-z").value),
        ],
        rotation: [
            parseFloat(document.getElementById("obj-rot-x").value),
            parseFloat(document.getElementById("obj-rot-y").value),
            parseFloat(document.getElementById("obj-rot-z").value),
        ],
        scale: [
            parseFloat(document.getElementById("obj-scl-x").value),
            parseFloat(document.getElementById("obj-scl-y").value),
            parseFloat(document.getElementById("obj-scl-z").value),
        ],
        reflectivity: parseFloat(document.getElementById("obj-reflectivity-num").value),
        material: material,
    };

    try {
        await fetch(`${API_BASE}/api/environment/objects`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        setTimeout(refreshObjects, 500);
    } catch (e) {
        console.error("Spawn failed:", e);
    }
}

async function deleteObject(primName) {
    try {
        await fetch(`${API_BASE}/api/environment/objects/${primName}`, { method: "DELETE" });
        setTimeout(refreshObjects, 500);
    } catch (e) {
        console.error("Delete failed:", e);
    }
}

async function refreshObjects() {
    try {
        const resp = await fetch(`${API_BASE}/api/environment/objects`);
        const data = await resp.json();
        const list = document.getElementById("spawned-list");
        const entries = Object.entries(data.objects);
        if (entries.length === 0) {
            list.innerHTML = "<p class=\"text-muted\">No objects spawned</p>";
            return;
        }
        list.innerHTML = "";
        entries.forEach(([path, info]) => {
            const item = document.createElement("div");
            item.className = "spawned-item";
            const pos = info.position || [0,0,0];
            const matLabel = info.material ? ` [${info.material}]` : '';
            const reflLabel = info.reflectivity !== undefined ? ` R=${info.reflectivity}` : '';
            item.innerHTML = `
                <div class="spawned-info">
                    <span class="spawned-name">${info.prim_name || path}</span>
                    <span class="spawned-detail">${info.asset_name}${matLabel}${reflLabel} @ [${pos.map(v=>v.toFixed(1)).join(", ")}]</span>
                </div>
                <button class="btn btn-small btn-delete" data-name="${info.prim_name}">&#x2715;</button>
            `;
            list.appendChild(item);
        });
        list.querySelectorAll(".btn-delete").forEach(btn => {
            btn.addEventListener("click", () => deleteObject(btn.dataset.name));
        });
    } catch (e) {}
}

// Init objects tab on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
    fetchAssets();
    fetchMaterials();
    document.getElementById("spawn-btn").addEventListener("click", spawnObject);
    document.getElementById("refresh-objects-btn").addEventListener("click", refreshObjects);
    document.getElementById("obj-material-select").addEventListener("change", onMaterialChanged);
    const reflSlider = document.getElementById("obj-reflectivity-slider");
    const reflNum = document.getElementById("obj-reflectivity-num");
    reflSlider.addEventListener("input", () => { reflNum.value = reflSlider.value; });
    reflNum.addEventListener("input", () => { reflSlider.value = reflNum.value; });
    refreshObjects();
});
