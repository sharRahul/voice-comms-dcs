/* ── state ─────────────────────────────────────────────────────────── */
const state = {
  ws: null,
  wsRetryDelay: 1000,
  wsConnected: false,
  pttActive: false,
  typingId: null,
  peerConnection: null,
  signalSocket: null,
  translations: {},
  activeLanguage: localStorage.getItem('vcdcs-language') || 'en',
  dashboardToken: sessionStorage.getItem('vcdcs-dashboard-token') || '',
};

/* ── DOM refs ──────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const chatLog          = $('chatLog');
const contextBox       = $('contextBox');
const connectBtn       = $('connectBtn');
const pttStartBtn      = $('pttStartBtn');
const pttStopBtn       = $('pttStopBtn');
const clearBtn         = $('clearBtn');
const manualForm       = $('manualForm');
const manualText       = $('manualText');
const remoteAudio      = $('remoteAudio');
const connectionPill   = $('connectionPill');
const pttPill          = $('pttPill');
const modePill         = $('modePill');
const connectionLabel  = $('connectionLabel');
const pttLabel         = $('pttLabel');
const modeLabel        = $('modeLabel');
const languageSelect   = $('languageSelect');
const skinSelect       = $('skinSelect');
const personalitySelect = $('personalitySelect');
const joystickPresetSelect = $('joystickPresetSelect');
const joystickPresetHint   = $('joystickPresetHint');
const telemetryAge     = $('telemetryAge');
const fuelGauge        = $('fuelGauge');
const altGauge         = $('altGauge');
const speedGauge       = $('speedGauge');
const gGauge           = $('gGauge');
const hdgVal           = $('hdgVal');
const gearVal          = $('gearVal');
const flapsVal         = $('flapsVal');
const pttIndicator     = $('pttIndicator');

/* ── token ─────────────────────────────────────────────────────────── */
(function initToken() {
  const params = new URLSearchParams(location.search);
  const token = params.get('token');
  if (token) {
    state.dashboardToken = token;
    sessionStorage.setItem('vcdcs-dashboard-token', token);
    params.delete('token');
    const q = params.toString();
    history.replaceState({}, '', `${location.pathname}${q ? '?' + q : ''}${location.hash}`);
  }
})();

function authHeaders(extra = {}) {
  const h = { ...extra };
  if (state.dashboardToken) h['X-Voice-Comms-DCS-Token'] = state.dashboardToken;
  return h;
}

async function apiFetch(url, opts = {}) {
  const resp = await fetch(url, { ...opts, headers: authHeaders(opts.headers || {}) });
  if (resp.status === 401 || resp.status === 403) {
    appendMsg('error', 'AUTH', 'Dashboard authorization failed. Reopen the startup URL.');
    throw new Error('Unauthorized');
  }
  return resp;
}

function wsUrl(path) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const u = new URL(`${proto}://${location.host}${path}`);
  if (state.dashboardToken) u.searchParams.set('token', state.dashboardToken);
  return u.toString();
}

/* ── i18n ──────────────────────────────────────────────────────────── */
function t(key, fallback) {
  return state.translations[key] || fallback || key;
}

async function loadI18n(lang, notifyBackend = true) {
  state.activeLanguage = lang;
  localStorage.setItem('vcdcs-language', lang);
  if (languageSelect) languageSelect.value = lang;
  try {
    const resp = await apiFetch(`/api/i18n/${lang}`);
    state.translations = await resp.json();
  } catch (_) { /* keep current translations on network error */ }
  document.documentElement.lang = lang;
  applyI18n();
  if (!notifyBackend) return;
  apiFetch('/api/language', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language: lang }),
  }).catch(() => {});
  if (state.signalSocket?.readyState === WebSocket.OPEN) {
    state.signalSocket.send(JSON.stringify({ type: 'language', language: lang }));
  }
}

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    const val = t(key);
    if (val !== key) el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    const val = t(key);
    if (val !== key) el.placeholder = val;
  });
}

/* ── pills ─────────────────────────────────────────────────────────── */
function setPill(pill, label, labelEl, cls) {
  pill.className = `pill ${cls || ''}`;
  if (labelEl) labelEl.textContent = label;
}

/* ── SVG arc gauges ────────────────────────────────────────────────── */
const ARC_LEN = 113;

function setArc(arcId, fraction) {
  const el = $(arcId);
  if (!el) return;
  const f = Math.max(0, Math.min(1, Number.isFinite(fraction) ? fraction : 0));
  el.style.strokeDashoffset = String(ARC_LEN * (1 - f));
}

function fmt(v, decimals = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(decimals) : '–';
}

/* ── chat bubbles ──────────────────────────────────────────────────── */
function escHtml(s) {
  return String(s).replace(/[&<>'"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c])
  );
}

function appendMsg(role, speaker, text, badge) {
  const wrap = document.createElement('div');
  wrap.className = `msg msg-${role}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const header = document.createElement('div');
  header.className = 'bubble-header';
  header.innerHTML = `<span class="bubble-speaker">${escHtml(speaker)}</span>`;
  if (badge) {
    header.innerHTML += ` <span class="bubble-badge">${escHtml(badge)}</span>`;
  }
  const ts = document.createElement('span');
  ts.className = 'bubble-ts';
  ts.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  header.appendChild(ts);

  const body = document.createElement('div');
  body.className = 'bubble-body';
  body.textContent = text;

  bubble.appendChild(header);
  bubble.appendChild(body);
  wrap.appendChild(bubble);
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
  return wrap;
}

function showTyping() {
  if (state.typingId) return;
  const wrap = document.createElement('div');
  wrap.className = 'msg msg-nimbus typing-wrap';
  wrap.id = 'typingIndicator';
  wrap.innerHTML = '<div class="bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
  state.typingId = true;
}

function hideTyping() {
  const el = $('typingIndicator');
  if (el) el.remove();
  state.typingId = null;
}

/* ── telemetry update ──────────────────────────────────────────────── */
function applySettings(s = {}) {
  if (s.personality && personalitySelect) personalitySelect.value = s.personality;
  if (s.skin && skinSelect) {
    skinSelect.value = s.skin;
    document.body.dataset.skin = s.skin;
    localStorage.setItem('vcdcs-skin', s.skin);
  }
}

function updateStatus(payload) {
  const age = Number(payload.telemetry_age_seconds);
  if (payload.language && payload.language !== state.activeLanguage) {
    loadI18n(payload.language, false).catch(() => {});
  }
  if (payload.settings) applySettings(payload.settings);

  if (Number.isFinite(age) && age < 2.0) {
    setPill(connectionPill, `${t('status.telemetry_live', 'Telemetry')} ${age.toFixed(1)}s`, connectionLabel, 'ok');
  } else {
    setPill(connectionPill, t('status.telemetry_stale', 'Telemetry stale'), connectionLabel, 'warn');
  }

  const ptt = payload.ptt || {};
  const pttActive = Boolean(ptt.active);
  const pttText = pttActive
    ? `${t('status.ptt_active', 'PTT active')} ${ptt.source || ''}`
    : t('status.ptt_idle', 'PTT idle');
  setPill(pttPill, pttText, pttLabel, pttActive ? 'ok' : '');
  pttIndicator.classList.toggle('active', pttActive);

  const mode = payload.mode || 'unknown';
  setPill(modePill, `${t('status.mode', 'Mode')} ${mode}`, modeLabel, mode === 'combat' ? 'danger' : 'ok');

  const internal = payload.internal || {};
  const spatial  = payload.spatial  || {};

  fuelGauge.textContent  = fmt(internal.fuel_total_kg);
  altGauge.textContent   = fmt(spatial.altitude_asl_ft);
  speedGauge.textContent = fmt(spatial.ias_kt);
  gGauge.textContent     = fmt(internal.g_load, 1);

  setArc('fuelArc', (internal.fuel_total_kg   || 0) / 10000);
  setArc('altArc',  (spatial.altitude_asl_ft  || 0) / 50000);
  setArc('iasArc',  (spatial.ias_kt           || 0) / 700);
  setArc('gArc',    (internal.g_load          || 0) / 9);

  const orientation = payload.orientation || {};
  hdgVal.textContent   = Number.isFinite(Number(orientation.heading_deg)) ? fmt(orientation.heading_deg) : '–';
  gearVal.textContent  = internal.gear_down != null ? (internal.gear_down ? 'DN' : 'UP') : '–';
  flapsVal.textContent = internal.flaps_pct  != null ? `${fmt(internal.flaps_pct)}%` : '–';

  if (telemetryAge) {
    telemetryAge.textContent = Number.isFinite(age) ? `${age.toFixed(1)}s` : '–';
    telemetryAge.className = `badge ${age < 2.0 ? 'ok' : 'warn'}`;
  }

  if (contextBox) contextBox.textContent = payload.context || 'Waiting for telemetry…';
}

/* ── WebSocket live feed ───────────────────────────────────────────── */
function connectLiveSocket() {
  const ws = new WebSocket(wsUrl('/api/live'));
  state.ws = ws;

  ws.onopen = () => {
    state.wsConnected = true;
    state.wsRetryDelay = 1000;
    setPill(connectionPill, t('status.connecting', 'Connected'), connectionLabel, 'ok');
  };

  ws.onclose = () => {
    state.wsConnected = false;
    setPill(connectionPill, t('status.disconnected', 'Disconnected'), connectionLabel, 'warn');
    const delay = state.wsRetryDelay;
    state.wsRetryDelay = Math.min(delay * 2, 30000);
    setTimeout(connectLiveSocket, delay);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = ({ data }) => {
    let msg;
    try { msg = JSON.parse(data); } catch { return; }

    switch (msg.type) {
      case 'status':
        updateStatus(msg.payload || msg);
        break;
      case 'ptt':
        updateStatus({ ptt: msg.state, telemetry_age_seconds: NaN });
        break;
      case 'transcript':
        hideTyping();
        appendMsg('pilot', 'PILOT', msg.text || '');
        showTyping();
        break;
      case 'conversation':
        hideTyping();
        if (msg.pilot)  appendMsg('pilot',  'PILOT',  msg.pilot);
        if (msg.nimbus) appendMsg('nimbus', 'NIMBUS', msg.nimbus, msg.intent || null);
        if (msg.settings) applySettings(msg.settings);
        break;
      case 'language':
        if (msg.language !== state.activeLanguage) loadI18n(msg.language, false).catch(() => {});
        break;
      case 'settings':
        applySettings(msg);
        break;
      case 'joystick_preset':
        appendMsg('system', 'PTT', `Preset active: ${msg.label}`);
        break;
      case 'system':
        appendMsg('system', 'SYSTEM', msg.message || '');
        break;
      case 'error':
        hideTyping();
        appendMsg('error', 'ERROR', msg.message || 'Unknown error');
        break;
    }
  };
}

/* ── WebRTC ────────────────────────────────────────────────────────── */
async function connectWebRtc() {
  if (state.peerConnection) return;

  const sig = new WebSocket(wsUrl('/ws'));
  state.signalSocket = sig;
  await new Promise((res, rej) => { sig.onopen = res; sig.onerror = rej; });

  const pc = new RTCPeerConnection({ iceServers: [] });
  state.peerConnection = pc;

  const dc = pc.createDataChannel('nimbus-control');
  dc.onmessage = ({ data }) => appendMsg('nimbus', 'NIMBUS', data);

  pc.ontrack = ({ streams }) => { remoteAudio.srcObject = streams[0]; };

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: true },
      video: false,
    });
    stream.getAudioTracks().forEach(track => pc.addTrack(track, stream));
  } catch (err) {
    appendMsg('error', 'MIC', `Microphone access failed: ${err.message || err}`);
  }

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  sig.send(JSON.stringify({ type: 'offer', sdp: offer.sdp }));

  sig.onmessage = async ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.type === 'answer') {
      await pc.setRemoteDescription(msg);
      sig.send(JSON.stringify({ type: 'language', language: state.activeLanguage }));
      sig.send(JSON.stringify({ type: 'settings', personality: personalitySelect?.value, skin: skinSelect?.value }));
      appendMsg('system', 'WEBRTC', 'Connected — mic live');
      connectBtn.textContent = '🔴 Mic connected';
      connectBtn.disabled = true;
    } else if (msg.type === 'nimbus') {
      hideTyping();
      appendMsg('nimbus', 'NIMBUS', msg.text || '');
    } else if (msg.type === 'settings') {
      applySettings(msg);
    }
  };

  sig.onclose = () => {
    state.peerConnection?.close();
    state.peerConnection = null;
    state.signalSocket = null;
    connectBtn.textContent = '📡 Connect mic';
    connectBtn.disabled = false;
    appendMsg('system', 'WEBRTC', 'Disconnected');
  };
}

/* ── PTT keyboard shortcut ─────────────────────────────────────────── */
function sendPtt(start) {
  const sig = state.signalSocket;
  if (sig?.readyState === WebSocket.OPEN) {
    sig.send(JSON.stringify({ type: start ? 'ptt_start' : 'ptt_stop' }));
  }
}

document.addEventListener('keydown', e => {
  if (e.repeat) return;
  const tag = document.activeElement?.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
  if (e.code === 'Space' || e.code === 'ControlRight') {
    e.preventDefault();
    sendPtt(true);
  }
});
document.addEventListener('keyup', e => {
  if (e.code === 'Space' || e.code === 'ControlRight') sendPtt(false);
});

/* ── HOTAS presets ─────────────────────────────────────────────────── */
async function loadJoystickPresets() {
  try {
    const resp = await apiFetch('/api/joystick-presets');
    const payload = await resp.json();
    for (const preset of payload.presets || []) {
      const opt = document.createElement('option');
      opt.value = preset.id;
      opt.textContent = preset.label;
      opt.dataset.hint = `${preset.device_hint || preset.label}: joystick ${preset.joystick_index}, button ${preset.button_index}, hotkey ${preset.hotkey}. ${preset.notes || ''}`;
      joystickPresetSelect?.appendChild(opt);
    }
  } catch (err) {
    appendMsg('error', 'PRESETS', err.message || err);
  }
}

async function applyJoystickPreset(profileId) {
  if (!profileId) return;
  const opt = joystickPresetSelect?.selectedOptions[0];
  if (opt?.dataset.hint && joystickPresetHint) joystickPresetHint.textContent = opt.dataset.hint;
  try {
    const resp = await apiFetch('/api/joystick-preset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: profileId }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const preset = await resp.json();
    appendMsg('system', 'PTT', `Loaded ${preset.label}: joystick ${preset.joystick_index}, button ${preset.button_index}`);
  } catch (err) {
    appendMsg('error', 'PRESET', err.message || err);
  }
}

/* ── settings persistence ──────────────────────────────────────────── */
async function postSettings(settings) {
  applySettings(settings);
  apiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  }).catch(err => appendMsg('error', 'SETTINGS', err.message || err));
  if (state.signalSocket?.readyState === WebSocket.OPEN) {
    state.signalSocket.send(JSON.stringify({ type: 'settings', ...settings }));
  }
}

/* ── event listeners ───────────────────────────────────────────────── */
connectBtn.addEventListener('click', () =>
  connectWebRtc().catch(err => appendMsg('error', 'WEBRTC', err.message || err))
);
pttStartBtn.addEventListener('click', () => sendPtt(true));
pttStopBtn.addEventListener('click',  () => sendPtt(false));

clearBtn?.addEventListener('click', () => { chatLog.innerHTML = ''; });

manualForm.addEventListener('submit', e => {
  e.preventDefault();
  const text = manualText.value.trim();
  if (!text) return;
  if (state.signalSocket?.readyState === WebSocket.OPEN) {
    state.signalSocket.send(JSON.stringify({ type: 'transcript', text }));
  } else if (state.ws?.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: 'transcript', text }));
  } else {
    appendMsg('error', 'SYSTEM', 'Connect WebRTC before sending transcript tests.');
  }
  manualText.value = '';
});

languageSelect?.addEventListener('change', () => loadI18n(languageSelect.value));
personalitySelect?.addEventListener('change', () => postSettings({ personality: personalitySelect.value }));
skinSelect?.addEventListener('change', () => postSettings({ skin: skinSelect.value }));
joystickPresetSelect?.addEventListener('change', () => applyJoystickPreset(joystickPresetSelect.value));

/* ── boot ──────────────────────────────────────────────────────────── */
applySettings({ skin: localStorage.getItem('vcdcs-skin') || 'default' });
loadJoystickPresets();
loadI18n(state.activeLanguage).then(connectLiveSocket).catch(connectLiveSocket);
