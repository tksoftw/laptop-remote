'use strict';

// The scanned URL is parsed as data. Never navigate to it or fetch its host.
function pairingKeyFromLink(value) {
  let url;
  try { url = new URL(value.trim()); } catch { throw new Error('This QR code is not a Laptop Remote pairing link.'); }
  const parameters = new URLSearchParams(url.hash.slice(1));
  const keys = [...parameters.keys()];
  const key = parameters.get('key');
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || keys.length !== 1 || keys[0] !== 'key' || !/^[A-Za-z0-9_-]{43}$/.test(key || '')) {
    throw new Error('This QR code is not a Laptop Remote pairing link.');
  }
  return key;
}

async function readPairingPhoto(file) {
  if (!file || !file.type.startsWith('image/')) throw new Error('Choose a photo of the QR code.');
  if (file.size > 20 * 1024 * 1024) throw new Error('That photo is larger than 20 MB. Take a smaller photo of the QR code.');
  const objectUrl = URL.createObjectURL(file);
  try {
    const photo = new Image();
    photo.src = objectUrl;
    try { await photo.decode(); } catch { throw new Error('The photo could not be opened. Choose a JPEG or PNG photo.'); }
    if (!photo.naturalWidth || !photo.naturalHeight || photo.naturalWidth * photo.naturalHeight > 80000000) throw new Error('The photo has unsupported dimensions. Take a smaller photo.');
    // Keep small QR codes legible in full camera photos. ZXing scans several
    // scales internally; decoding runs off the UI thread.
    const scale = Math.min(1, 4096 / Math.max(photo.naturalWidth, photo.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(photo.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(photo.naturalHeight * scale));
    const context = canvas.getContext('2d', {willReadFrequently: true});
    if (!context) throw new Error('The browser could not open the QR reader.');
    context.drawImage(photo, 0, 0, canvas.width, canvas.height);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
    return pairingKeyFromLink(await decodeQr(pixels));
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

async function decodeQr(pixels) {
  const worker = new Worker('/qr-reader.js');
  let deadline;
  try {
    return await new Promise((resolve, reject) => {
      deadline = setTimeout(() => reject(new Error('Reading the QR code took too long. Take a closer photo of the code.')), 45000);
      worker.onmessage = ({data}) => data.error ? reject(new Error(data.error)) : resolve(data.text);
      worker.onerror = () => reject(new Error('The QR reader could not load. Check your connection to the laptop and reopen the app.'));
      worker.onmessageerror = () => reject(new Error('The QR reader could not process this photo.'));
      worker.postMessage(pixels, [pixels.data.buffer]);
    });
  } finally {
    clearTimeout(deadline);
    worker.terminate();
  }
}

(() => {
  const photo = $('qr-photo');
  let pairing = false;
  function setBusy(value) {
    pairing = value;
    for (const id of ['scan-qr', 'pair-link', 'pairing-link']) $(id).disabled = value;
  }
  async function pair(readKey) {
    if (pairing) return;
    setBusy(true);
    message('');
    try {
      const key = await readKey();
      $('scan-status').textContent = 'Pairing…';
      await pairWithKey(key);
      $('pairing-link').value = '';
      $('scan-status').textContent = '';
    } catch (error) {
      $('scan-status').textContent = '';
      // A rejected photo or key stays an explicit failure. No navigation or
      // automatic switch to a different pairing method.
      message(error.status === 401 ? 'The QR code was rejected. Click Pair in Laptop Remote and use its current code.' : readableError(error));
    } finally {
      photo.value = '';
      setBusy(false);
    }
  }
  $('scan-qr').addEventListener('click', () => {
    if (!pairing) {
      message('');
      $('scan-status').textContent = '';
      photo.click();
    }
  });
  photo.addEventListener('change', () => {
    if (photo.files.length !== 1) return;
    const file = photo.files[0];
    $('scan-status').textContent = 'Reading QR code…';
    pair(() => readPairingPhoto(file));
  });
  $('pair-link').addEventListener('click', () => pair(() => pairingKeyFromLink($('pairing-link').value)));
  $('pairing-link').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); $('pair-link').click(); } });
})();
