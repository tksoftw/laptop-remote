'use strict';
const $ = (id) => document.getElementById(id);
let sessionReady = false;
let latest = null;
let busy = false;
let dragging = false;
let pollTimer;
let reading = null;
let connectionError = false;
let needsPairing = false;

function showPairing(required) {
  const wasRequired = needsPairing;
  needsPairing = required;
  $('pairing-panel').hidden = !required;
  $('screen-toggle').disabled = required;
  if (required || wasRequired) {
    $('media-screen').hidden = required;
    $('desktop-screen').hidden = true;
    $('screen-toggle').setAttribute('aria-expanded', 'false');
    $('screen-toggle').setAttribute('aria-label', 'Mouse and keyboard');
    $('screen-toggle').title = 'Mouse and keyboard';
    $('screen-icon').setAttribute('href', '#i-mouse');
  }
}

function message(text) {
  $('message').textContent = text;
  $('message').hidden = !text;
}

function connection(online, label) {
  $('connection').className = `connection ${online ? 'online' : 'offline'}`;
  $('connection').lastElementChild.textContent = label || (online ? 'Connected' : 'Disconnected');
  $('retry').hidden = online || !sessionReady;
  document.dispatchEvent(new CustomEvent('remoteconnection', {detail: online}));
}

function setControls() {
  const media = latest?.media;
  const playing = media?.status === 'playing';
  $('play').disabled = busy || !latest || !media || !(playing ? media.can_pause : media.can_play);
  for (const id of ['volume', 'quieter', 'louder', 'mute']) $(id).disabled = busy || !latest;
}

function showVolume(value) {
  $('volume-value').textContent = value;
  $('volume').style.setProperty('--fill', `${value}%`);
}

function render(state) {
  latest = state;
  showPairing(false);
  connection(true);
  const media = state.media;
  const playing = media?.status === 'playing';
  document.body.classList.toggle('playing', playing);
  $('playback-status').textContent = media ? (playing ? 'NOW PLAYING' : media.status.toUpperCase()) : 'YOUR LAPTOP';
  $('track-title').textContent = media ? (media.title || 'Untitled media') : 'No player found';
  $('track-detail').textContent = media ? (media.artist || media.app) : 'Start a video or song on your laptop.';
  $('play-icon').setAttribute('href', playing ? '#i-pause' : '#i-play');
  $('play').setAttribute('aria-label', playing ? 'Pause' : 'Play');
  $('play-label').textContent = media ? (playing ? 'Pause' : 'Play') : 'Play / pause';
  if (!dragging) {
    $('volume').value = state.volume;
    showVolume(state.volume);
  }
  $('mute').setAttribute('aria-pressed', String(state.muted));
  $('mute-label').textContent = state.muted ? 'Unmute' : 'Mute';
  $('mute-icon').setAttribute('href', state.muted ? '#i-muted' : '#i-volume');
  $('output').textContent = state.output;
  $('computer').textContent = state.computer;
  setControls();
}

async function request(path, options = {}, timeoutMs = 10000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...options,
      headers: {'X-Remote-Request': '1', ...(options.headers || {})},
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    });
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) throw new Error('The connection returned an unexpected page. Check Laptop Remote on your laptop.');
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.error || `Request failed (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return result;
  } finally {
    clearTimeout(timeout);
  }
}

function readableError(error) {
  if (error.status === 401) return 'Pair this app to continue. Tap Scan QR code.';
  if (error.name === 'AbortError' || error instanceof TypeError) return 'The laptop did not respond. Check that Laptop Remote is running.';
  return error.message;
}

async function refresh() {
  if (!sessionReady || document.hidden) return;
  if (reading) return reading;
  reading = (async () => {
    try {
      render(await request('/api/state'));
      if (connectionError) { message(''); connectionError = false; }
    } catch (error) {
      latest = null;
      connection(false, error.status === 401 ? 'Pairing needed' : undefined);
      if (error.status === 401) {
        sessionReady = false;
        clearTimeout(pollTimer);
        showPairing(true);
        $('retry').hidden = true;
      }
      setControls();
      message(readableError(error));
      connectionError = true;
    }
  })();
  try { await reading; } finally { reading = null; }
}

async function poll() {
  clearTimeout(pollTimer);
  if (!busy) await refresh();
  if (sessionReady) pollTimer = setTimeout(poll, 2000);
}

async function send(action, value) {
  if (busy || !latest) return;
  busy = true;
  setControls();
  message('');
  connectionError = false;
  // Do not retry commands: a lost reply does not prove the action failed.
  try {
    if (reading) await reading;
    const body = value === undefined ? {action} : {action, value};
    await request('/api/command', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    await refresh();
  } catch (error) {
    message(`${readableError(error)} Check the player or volume before trying again.`);
  } finally {
    busy = false;
    setControls();
  }
}

$('play').addEventListener('click', () => send(latest.media.status === 'playing' ? 'pause' : 'play'));
$('mute').addEventListener('click', () => send('mute', !latest.muted));
$('quieter').addEventListener('click', () => send('volume', Math.max(0, latest.volume - 5)));
$('louder').addEventListener('click', () => send('volume', Math.min(100, latest.volume + 5)));
$('volume').addEventListener('input', () => { dragging = true; showVolume(Number($('volume').value)); });
$('volume').addEventListener('change', () => { const value = Number($('volume').value); dragging = false; send('volume', value); });
$('volume').addEventListener('pointercancel', () => { dragging = false; if (latest) render(latest); });
$('retry').addEventListener('click', () => { message(''); poll(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

async function pairWithKey(pairingKey) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(pairingKey)) throw new Error('The pairing key is invalid. Click Pair in Laptop Remote on your laptop.');
  sessionReady = false;
  clearTimeout(pollTimer);
  if (reading) await reading;
  await request('/api/pair', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: pairingKey})});
  // Verify this app's cookie before claiming that pairing succeeded.
  const state = await request('/api/state');
  localStorage.setItem('laptop-remote-key', pairingKey);
  sessionReady = true;
  connectionError = false;
  message('');
  render(state);
  pollTimer = setTimeout(poll, 2000);
}

async function connectSession() {
  try {
    const incoming = new URLSearchParams(location.hash.slice(1)).get('key');
    const pairingKey = incoming || localStorage.getItem('laptop-remote-key');
    // A remembered pairing key explicitly signs this browser in. Installed iOS
    // apps use the HttpOnly session cookie copied by Safari at installation.
    if (pairingKey) {
      await pairWithKey(pairingKey);
      if (incoming) {
        history.replaceState(null, '', location.pathname);
      }
    } else {
      sessionReady = true;
      poll();
    }
  } catch (error) {
    sessionReady = false;
    showPairing(true);
    connection(false, 'Pairing needed');
    $('retry').hidden = true;
    $('track-detail').textContent = 'Pairing could not be completed.';
    message(readableError(error));
  }
}
connectSession();
