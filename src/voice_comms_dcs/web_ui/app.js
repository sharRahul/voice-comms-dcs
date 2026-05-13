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

let liveSocket;
let signalSocket;
let peerConnection;
let dataChannel;

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

function setPill(element, text, cls) {
  element.className = `pill ${cls || ''}`;
  element.textContent = text;
}

function fmt(value, decimals = 0) {
  const num = Number(value);
  if (!Number.isFinite(num)) return '--';
  return num.toFixed(decimals);
}

function updateStatus(payload) {
  const age = Number(payload.telemetry_age_seconds);
  if (Number.isFinite(age) && age < 2.0) {
    setPill(connectionStatus, `Telemetry live ${age.toFixed(1)}s`, 'ok');
  } else {
    setPill(connectionStatus, 'Telemetry stale / waiting', 'warn');
  }

  const ptt = payload.ptt || {};
  setPill(pttStatus, ptt.active ? `PTT active ${ptt.source || ''}` : 'PTT idle', ptt.active ? 'ok' : '');
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
    }
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
      audio: {
        echoCancellation: false,
        noiseSuppression: true,
        autoGainControl: true
      },
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
      logLine('system', 'SYSTEM', 'WebRTC connected');
    } else if (answer.type === 'nimbus') {
      logLine('', 'NIMBUS', answer.text || '');
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

connectLiveSocket();
