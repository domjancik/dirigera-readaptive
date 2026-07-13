const csrfToken = document.querySelector('meta[name="panel-csrf"]').content;
const state = { data: null, selected: 0, initial: null, dirty: false };

const levelFields = [
  ['min_light_level', 'Night'],
  ['morning_light_level', 'Morning'],
  ['max_light_level', 'Peak'],
  ['evening_light_level', 'Evening'],
  ['pre_sleep_light_level', 'Pre-sleep'],
];

const byId = (id) => document.getElementById(id);

function profile() { return state.data.profiles[state.selected]; }

function api(url, options = {}) {
  return fetch(url, { cache: 'no-store', ...options }).then(async (response) => {
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Request failed.');
    return payload;
  });
}

function setToast(message, isError = false) {
  const toast = byId('toast');
  toast.textContent = message;
  toast.style.background = isError ? '#9e3735' : '#172227';
  toast.classList.add('visible');
  window.clearTimeout(setToast.timer);
  setToast.timer = window.setTimeout(() => toast.classList.remove('visible'), 3600);
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return 'Unavailable';
  return `${(bytes / (1024 ** 3)).toFixed(1)} GB free`;
}

function activeClass(unit) {
  return unit?.active === 'active' ? 'good' : 'warning';
}

function renderStatus() {
  const system = state.data.system || {};
  const units = system.units || {};
  const firmware = system.firmware || {};
  const health = firmware.throttled || 'Unavailable';
  const throttled = !health.includes('0x0');
  const metrics = [
    ['Recovery', units.recovery?.active || 'Unavailable', units.recovery?.restarts ? `${units.recovery.restarts} restarts` : '', activeClass(units.recovery)],
    ['Schedule timer', units.scheduleTimer?.active || 'Unavailable', units.scheduleTimer?.nextRun || '', activeClass(units.scheduleTimer)],
    ['Storage', formatBytes(system.disk?.freeBytes), system.journal?.usage || '', ''],
    ['Pi health', throttled ? 'Attention' : 'Normal', `${firmware.temperature || ''} ${health}`.trim(), throttled ? 'warning' : 'good'],
  ];
  const root = byId('status');
  root.replaceChildren(...metrics.map(([label, value, detail, klass]) => {
    const element = document.createElement('div');
    element.className = 'metric';
    const labelNode = document.createElement('span'); labelNode.className = 'metric-label'; labelNode.textContent = label;
    const valueNode = document.createElement('span'); valueNode.className = `metric-value ${klass}`; valueNode.textContent = value;
    const detailNode = document.createElement('span'); detailNode.className = 'metric-detail'; detailNode.textContent = detail;
    element.append(labelNode, valueNode, detailNode);
    return element;
  }));
}

function renderTabs() {
  const root = byId('profile-tabs');
  root.replaceChildren(...state.data.profiles.map((item, index) => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'profile-tab'; button.role = 'tab';
    button.setAttribute('aria-selected', String(index === state.selected));
    button.textContent = item.profileName;
    button.addEventListener('click', () => { state.selected = index; renderControls(); renderTabs(); drawPreview(); });
    return button;
  }));
}

function fieldControl(field, label, min, max, step = 1) {
  const row = document.createElement('div'); row.className = 'control-row';
  const labelNode = document.createElement('label'); labelNode.htmlFor = `range-${field}`; labelNode.textContent = label;
  const range = document.createElement('input'); range.id = `range-${field}`; range.type = 'range'; range.min = min; range.max = max; range.step = step; range.value = profile().curve[field];
  const numeric = document.createElement('input'); numeric.className = 'value-input'; numeric.type = 'number'; numeric.min = min; numeric.max = max; numeric.step = step; numeric.value = profile().curve[field];
  const update = (value) => { profile().curve[field] = Number(value); range.value = value; numeric.value = value; markDirty(); schedulePreview(); };
  range.addEventListener('input', () => update(range.value)); numeric.addEventListener('change', () => update(numeric.value));
  row.append(labelNode, range, numeric); return row;
}

function renderControls() {
  const current = profile();
  byId('profile-title').textContent = current.profileName;
  byId('level-controls').replaceChildren(...levelFields.map(([field, label]) => fieldControl(field, label, 1, 100)));
  const extension = byId('extension-toggle'); extension.checked = current.curve.extend_day_after_late_sunset;
  const extensionRoot = byId('extension-controls'); extensionRoot.className = current.curve.extend_day_after_late_sunset ? 'extension-controls' : 'extension-controls muted';
  extensionRoot.replaceChildren(fieldControl('latest_sleep_time', 'Latest sleep', 18, 23.75, 0.25), fieldControl('min_evening_ramp_hours', 'Min. ramp', 0.25, 5, 0.25));
  extension.onchange = () => { current.curve.extend_day_after_late_sunset = extension.checked; markDirty(); renderControls(); schedulePreview(); };
}

function markDirty() { state.dirty = true; byId('change-state').textContent = 'Unsaved changes'; }

function schedulePreview() {
  window.clearTimeout(schedulePreview.timer);
  const requestId = (schedulePreview.requestId || 0) + 1;
  schedulePreview.requestId = requestId;
  schedulePreview.timer = window.setTimeout(async () => {
    try {
      const preview = await api('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Panel-CSRF': csrfToken },
        body: JSON.stringify({ profiles: state.data.profiles }),
      });
      if (requestId !== schedulePreview.requestId) return;
      state.data.date = preview.date;
      state.data.sun = preview.sun;
      state.data.profiles = preview.profiles;
      renderPreviewMeta();
      drawPreview();
    } catch (error) {
      if (requestId === schedulePreview.requestId) setToast(error.message, true);
    }
  }, 220);
}

function drawPreview() {
  const canvas = byId('curve-canvas');
  const rect = canvas.getBoundingClientRect(); const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
  const context = canvas.getContext('2d'); context.scale(ratio, ratio);
  const width = rect.width; const height = rect.height; const pad = { left: 39, right: 15, top: 18, bottom: 30 };
  const graphWidth = width - pad.left - pad.right; const graphHeight = height - pad.top - pad.bottom;
  context.clearRect(0, 0, width, height); context.font = '11px system-ui'; context.fillStyle = '#71807b'; context.strokeStyle = '#e2e8e4';
  for (let hour = 0; hour <= 24; hour += 6) { const x = pad.left + graphWidth * hour / 24; context.beginPath(); context.moveTo(x, pad.top); context.lineTo(x, pad.top + graphHeight); context.stroke(); context.fillText(String(hour).padStart(2, '0'), x - 6, height - 10); }
  for (let value = 0; value <= 100; value += 25) { const y = pad.top + graphHeight * (1 - value / 100); context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke(); context.fillText(String(value), 6, y + 4); }
  const entries = profile().preview;
  const x = (entry) => pad.left + graphWidth * (Number(entry.startTime.slice(0, 2)) + Number(entry.startTime.slice(3)) / 60) / 24;
  const lightY = (entry) => pad.top + graphHeight * (1 - entry.lightLevel / 100);
  const tempY = (entry) => pad.top + graphHeight * (1 - (entry.colorTemperature - 1000) / 3600);
  const line = (color, y) => { context.beginPath(); entries.forEach((entry, index) => index ? context.lineTo(x(entry), y(entry)) : context.moveTo(x(entry), y(entry))); context.strokeStyle = color; context.lineWidth = 2.2; context.stroke(); };
  line('#e58732', lightY); line('#217b94', tempY);
}

function formatHour(value) { const hour = Math.floor(value); const minute = Math.round((value - hour) * 60); return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`; }

function renderPreviewMeta() {
  byId('date-title').textContent = state.data.date;
  const sun = state.data.sun; const values = [['Nautical dawn', sun.nautical_sunrise], ['Sunrise', sun.sunrise], ['Solar noon', sun.solar_noon], ['Sunset', sun.sunset]];
  const root = byId('sun-times'); root.replaceChildren(...values.map(([label, value]) => { const node = document.createElement('span'); const strong = document.createElement('strong'); strong.textContent = `${label} `; node.append(strong, formatHour(value)); return node; }));
}

function render() { renderStatus(); renderTabs(); renderControls(); renderPreviewMeta(); drawPreview(); byId('updated-at').textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`; }

async function load() { state.data = await api('/api/state'); state.initial = structuredClone(state.data); state.selected = Math.min(state.selected, state.data.profiles.length - 1); state.dirty = false; byId('change-state').textContent = ''; render(); }

byId('refresh').addEventListener('click', () => load().catch((error) => setToast(error.message, true)));
byId('reset').addEventListener('click', () => { if (state.initial) { state.data = structuredClone(state.initial); state.dirty = false; byId('change-state').textContent = ''; render(); } });
byId('save').addEventListener('click', async () => {
  try {
    const result = await api('/api/apply', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Panel-CSRF': csrfToken }, body: JSON.stringify({ profiles: state.data.profiles }) });
    state.data = result.state;
    state.initial = structuredClone(state.data); state.dirty = false; byId('change-state').textContent = ''; render(); setToast('Configuration saved.');
  } catch (error) { setToast(error.message, true); }
});
window.addEventListener('resize', () => { if (state.data) drawPreview(); });
load().catch((error) => setToast(error.message, true));
