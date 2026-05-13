const terminal = document.getElementById('terminal');
const connectionStatus = document.getElementById('connectionStatus');
const pttStatus = document.getElementById('pttStatus');
const modeStatus = document.getElementById('modeStatus');
const fuelGauge = document.getElementById('fuelGauge');
const altGauge = document.getElementById('altGauge');
const speedGauge = document.getElementById('speedGauge');
const gGauge = document.getElementById('gGauge');
const contextBox = document.getElementById('contextBox');
const manualForm = document.getElementById('manualForm');
const manualText = document.getElementById('manualText');
const remoteAudio = document.getElementById('remoteAudio');
const connectBtn = document.getElementById('connectBtn');
const pttStartBtn = document.getElementById('pttStartBtn');
const pttStopBtn = document.getElementById('pttStopBtn');
const languageSelect = document.getElementById('languageSelect');
const personalitySelect = document.getElementById('personalitySelect');
const skinSelect = document.getElementById('skinSelect');
const joystickPresetSelect = document.getElementById('joystickPresetSelect');
const joystickPresetHint = document.getElementById('joystickPresetHint');

let liveSocket;
let signalSocket;
let peerConnection;
let dataChannel;
let activeLanguage = localStorage.getItem('vcdcs-language') || 'en';
let translations = {};

function logLine(kind, speaker, text) {
  const line = document.createElement('div');
  line.className = `line ${kind || ''}`;
  line.innerHTML = `<strong>${speaker}</strong> ${escapeHtml(text)}`;
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>'"]/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[ch]));
}

function t(key, fallback) {
  return translations[key] || fallback || key;
}

async function loadLanguage(language, notifyBackend = true) {
  activeLanguage = language;
  localStorage.setItem('vcdcs-language', language);
  languageSelect.value = language;
  const response = await fetch(`/api/i18n/${language}`);
  translations = await response.json();
  document.documentElement.lang = language;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n, el.textContent);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder, el.placeholder);
  });
  if (!notifyBackend) return;
  await fetch('/api/language', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language })
  }).catch(() => {});
  if (signalSocket && signalSocket.readyState === WebSocket.OPEN) {
    signalSocket.send(JSON.stringify({ type: 'language', language }));
  }
}

function setPill(element, text, cls) {
  element.className = `pill ${cls || ''}`;
  element.textContent = text;
}

function fmt(value, decimals = 0) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  return num.toFixed(decimals);
}

function applySettings(settings = {}) {
  if (settings.personality && personalitySelect) {
    personalitySelect.value = settings.personality;
  }
  if (settings.skin && skinSelect) {
    skinSelect.value = settings.skin;
    document.body.dataset.skin = settings.skin;
    localStorage.setItem('vcdcs-skin', settings.skin);
  }
}

async function postSettings(settings) {
  applySettings(settings);
  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  }).catch(error => logLine('error', 'SETTINGS', error.message || error));
  if (signalSocket && signalSocket.readyState === WebSocket.OPEN) {
    signalSocket.send(JSON.stringify({ type: 'settings', ...settings }));
  }
}

async function loadJoystickPresets() {
  try {
    const response = await fetch('/api/joystick-presets');
    const payload = await response.json();
    for (const preset of payload.presets || []) {
      const option = document.createElement('option');
      option.value = preset.id;
      option.textContent = preset.label;
      option.dataset.hint = `${preset.device_hint || preset.label}: joystick ${preset.joystick_index}, button ${preset.button_index}, hotkey ${preset.hotkey}. ${preset.notes || ''}`;
      joystickPresetSelect.appendChild(option);
    }
  } catch (error) {
    logLine('error', 'PRESETS', error.message || error);
  }
}

async function applyJoystickPreset(profileId) {
  if (!profileId) return;
  const option = joystickPresetSelect.selectedOptions[0];
  if (option?.dataset.hint) joystickPresetHint.textContent = option.dataset.hint;
  try {
    const response = await fetch('/api/joystick-preset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: profileId })
    });
    if (!response.ok) throw new Error(await response.text());
    const preset = await response.json();
    logLine('system', 'PTT', `Loaded ${preset.label}: joystick ${preset.joystick_index}, button ${preset.button_index}`);
  } catch (error) {
    logLine('error', 'PRESET', error.message || error);
  }
}

function updateStatus(payload) {
  const age = Number(payload.telemetry_age_seconds);
  if (payload.language && payload.language !== activeLanguage) {
    languageSelect.value = payload.language;
  }
  if (payload.settings) applySettings(payload.settings);

  if (Number.isFinite(age) && age < 2.0) {
    setPill(connectionStatus, `Telemetry live ${age.toFixed(1)}s`, 'ok');
  } else {
    setPill(connectionStatus, 'Telemetry stale / waiting', 'warn');
  }

  const ptt = payload.ptt || {};
  setPill(pttStatus, ptt.active ? `PTT active ${ptt.source || ''}` : t('status.ptt_idle', 'PTT idle'), ptt.active ? 'ok' : '');
  setPill(modeStatus, `Mode ${payload.mode || 'unknown'}`, payload.mode === 'combat' ? 'danger' : 'ok');

  const internal = payload.internal || {};
  const spatial = payload.spatial || {};
  fuelGauge.textContent = fmt(internal.fuel_total_kg);
  altGauge.textContent = fmt(spatial.altitude_asl_ft);
  speedGauge.textContent = fmt(spatial.ias_kt);
  gGauge.textContent = fmt(internal.g_load, 1);
  contextBox.textContent = payload.context || 'Waiting for telemetry...';
}

function connectLiveSocket() {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/live`;
  liveSocket = new WebSocket(url);
  liveSocket.onopen = () => logLine('system', 'SYSTEM', 'Dashboard live socket connected');
  liveSocket.onclose = () => {
    logLine('system', 'SYSTEM', 'Dashboard live socket disconnected; retrying...');
    setTimeout(connectLiveSocket, 1500);
  };
  liveSocket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === 'status') updateStatus(message.payload);
    if (message.type === 'ptt') updateStatus({ ptt: message.state, telemetry_age_seconds: NaN });
    if (message.type === 'transcript') logLine('pilot', 'PILOT', message.text || '');
    if (message.type === 'conversation') {
      logLine('pilot', 'PILOT', message.pilot || '');
      logLine('', 'NIMBUS', `${message.nimbus || ''} [${message.intent || 'intent'}]`);
      if (message.settings) applySettings(message.settings);
    }
    if (message.type === 'language' && message.language !== activeLanguage) {
      loadLanguage(message.language, false).catch(() => {});
    }
    if (message.type === 'settings') applySettings(message);
    if (message.type === 'joystick_preset') logLine('system', 'PTT', `Preset active: ${message.label}`);
    if (message.type === 'system') logLine('system', 'SYSTEM', message.message || '');
    if (message.type === 'error') logLine('error', 'ERROR', message.message || 'Unknown error');
  };
}

async function connectWebRtc() {
  if (peerConnection) return;
  signalSocket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  await new Promise((resolve, reject) => {
    signalSocket.onopen = resolve;
    signalSocket.onerror = reject;
  });

  peerConnection = new RTCPeerConnection({ iceServers: [] });
  dataChannel = peerConnection.createDataChannel('nimbus-control');
  dataChannel.onmessage = event => logLine('', 'NIMBUS', event.data);

  peerConnection.ontrack = event => {
    remoteAudio.srcObject = event.streams[0];
  };

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: true },
      video: false
    });
    for (const track of stream.getAudioTracks()) {
      peerConnection.addTrack(track, stream);
    }
  } catch (error) {
    logLine('error', 'MIC', `Microphone permission failed: ${error}`);
  }

  const offer = await peerConnection.createOffer();
  await peerConnection.setLocalDescription(offer);
  signalSocket.send(JSON.stringify({ type: 'offer', sdp: offer.sdp }));
  signalSocket.onmessage = async event => {
    const answer = JSON.parse(event.data);
    if (answer.type === 'answer') {
      await peerConnection.setRemoteDescription(answer);
      signalSocket.send(JSON.stringify({ type: 'language', language: activeLanguage }));
      signalSocket.send(JSON.stringify({ type: 'settings', personality: personalitySelect.value, skin: skinSelect.value }));
      logLine('system', 'SYSTEM', 'WebRTC connected');
    } else if (answer.type === 'nimbus') {
      logLine('', 'NIMBUS', answer.text || '');
    } else if (answer.type === 'settings') {
      applySettings(answer);
    }
  };
}

manualForm.addEventListener('submit', event => {
  event.preventDefault();
  const text = manualText.value.trim();
  if (!text) return;
  if (signalSocket && signalSocket.readyState === WebSocket.OPEN) {
    signalSocket.send(JSON.stringify({ type: 'transcript', text }));
  } else if (dataChannel && dataChannel.readyState === 'open') {
    dataChannel.send(text);
  } else {
    logLine('error', 'SYSTEM', 'Connect WebRTC before sending transcript tests.');
  }
  manualText.value = '';
});

connectBtn.addEventListener('click', () => connectWebRtc().catch(err => logLine('error', 'WEBRTC', err.message || err)));
pttStartBtn.addEventListener('click', () => signalSocket?.send(JSON.stringify({ type: 'ptt_start' })));
pttStopBtn.addEventListener('click', () => signalSocket?.send(JSON.stringify({ type: 'ptt_stop' })));
languageSelect.addEventListener('change', () => loadLanguage(languageSelect.value));
personalitySelect?.addEventListener('change', () => postSettings({ personality: personalitySelect.value }));
skinSelect?.addEventListener('change', () => postSettings({ skin: skinSelect.value }));
joystickPresetSelect?.addEventListener('change', () => applyJoystickPreset(joystickPresetSelect.value));

applySettings({ skin: localStorage.getItem('vcdcs-skin') || 'default' });
loadJoystickPresets();
loadLanguage(activeLanguage).then(connectLiveSocket).catch(() => connectLiveSocket());
