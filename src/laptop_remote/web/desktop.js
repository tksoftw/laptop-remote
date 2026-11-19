'use strict';
(() => {
  const pad = $('joystick');
  const thumb = $('joystick-thumb');
  const screen = $('desktop-screen');
  const mouseHolds = new Map();
  let online = false;
  let sending = false;
  let pointer = null;
  let vector = {x: 0, y: 0};
  let movement = null;
  let frame = null;
  let lastTick = 0;
  let remainder = {x: 0, y: 0};

  function controls() {
    for (const button of screen.querySelectorAll('.joystick-panel button, .key-actions button')) button.disabled = !online || sending;
    $('type-text').disabled = !online || sending;
    $('send-text').disabled = !online || sending || !$('type-text').value.length;
    pad.setAttribute('aria-disabled', String(!online || sending));
  }

  function stopJoystick() {
    const heldPointer = pointer;
    pointer = null;
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    vector = {x: 0, y: 0};
    remainder = {x: 0, y: 0};
    thumb.style.transform = '';
    pad.classList.remove('held');
    if (heldPointer !== null && pad.hasPointerCapture(heldPointer)) pad.releasePointerCapture(heldPointer);
  }

  async function input(data, timeout = 4000) {
    return request('/api/input', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)}, timeout);
  }

  function failed(error) {
    stopJoystick();
    releaseHolds();
    message(`${readableError(error)} The command was not confirmed. Check your laptop before trying again.`);
  }

  async function discrete(data) {
    if (!online || sending) return false;
    stopJoystick();
    sending = true;
    controls();
    message('');
    try {
      // Finish the last bounded movement before clicking or typing. Never retry
      // clicks, keys or text after a lost reply.
      if (movement) await movement;
      if (!await releaseHolds()) throw new Error('Mouse release was not confirmed.');
      if (!online || document.hidden) throw new Error('The remote is no longer active.');
      await input(data);
      return true;
    } catch (error) {
      failed(error);
      return false;
    } finally {
      sending = false;
      controls();
    }
  }

  function holdId() {
    return [...crypto.getRandomValues(new Uint8Array(16))].map(n => n.toString(16).padStart(2, '0')).join('');
  }

  function startHold(button, element, pointerId) {
    if (!online || sending || mouseHolds.has(button)) return;
    const hold = {id: holdId(), element, pointerId, ending: false, timer: null};
    mouseHolds.set(button, hold);
    element.classList.add('mouse-held');
    element.setAttribute('aria-pressed', 'true');
    const command = state => input({action: 'button', button, state, hold: hold.id}, 1500);
    hold.command = command;
    hold.pending = command('down');
    async function renew() {
      try {
        await hold.pending;
        if (hold.ending) return;
        hold.timer = setTimeout(() => {
          if (hold.ending) return;
          hold.pending = command('renew');
          renew();
        }, 600);
      } catch (error) {
        failed(error);
      }
    }
    renew();
  }

  async function endHold(button) {
    const hold = mouseHolds.get(button);
    if (!hold || hold.ending) return hold?.release;
    hold.ending = true;
    clearTimeout(hold.timer);
    hold.element.classList.remove('mouse-held');
    hold.element.setAttribute('aria-pressed', 'false');
    hold.release = (async () => {
      // Send up after any pending down/renew, including an uncertain reply.
      try { await hold.pending; } catch { /* The up below explicitly releases this hold. */ }
      try { await hold.command('up'); return true; }
      catch (error) { message(`${readableError(error)} The mouse hold will expire automatically.`); return false; }
      finally { if (mouseHolds.get(button) === hold) mouseHolds.delete(button); }
    })();
    return hold.release;
  }

  function releaseHolds() {
    return Promise.all([...mouseHolds.keys()].map(endHold)).then(results => results.every(result => result !== false));
  }

  for (const button of ['left', 'right']) {
    const element = $(`${button}-click`);
    element.setAttribute('aria-pressed', 'false');
    element.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !online || sending || mouseHolds.has(button)) return;
      event.preventDefault();
      element.setPointerCapture(event.pointerId);
      startHold(button, element, event.pointerId);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) element.addEventListener(type, event => {
      if (mouseHolds.get(button)?.pointerId === event.pointerId) endHold(button);
    });
    element.addEventListener('contextmenu', event => event.preventDefault());
    element.addEventListener('click', event => { if (event.detail === 0) discrete({action: 'click', button}); });
  }

  function tick(timestamp) {
    frame = null;
    if (pointer === null || !online || sending || document.hidden || screen.hidden) return;
    if (!movement && timestamp - lastTick >= 40) {
      lastTick = timestamp;
      const magnitude = Math.hypot(vector.x, vector.y);
      if (magnitude > 0.12) {
        const speed = Math.pow((magnitude - 0.12) / 0.88, 1.6) * 24;
        const x = vector.x / magnitude * speed + remainder.x;
        const y = vector.y / magnitude * speed + remainder.y;
        const dx = Math.trunc(x), dy = Math.trunc(y);
        remainder = {x: x - dx, y: y - dy};
        if (dx || dy) {
          const pending = input({action: 'move', dx, dy}, 1500);
          movement = pending;
          pending.catch(failed).finally(() => { if (movement === pending) movement = null; });
        }
      }
    }
    if (pointer !== null) frame = requestAnimationFrame(tick);
  }

  function position(event) {
    const bounds = pad.getBoundingClientRect();
    const radius = bounds.width / 2 - thumb.offsetWidth / 2 - 12;
    let x = (event.clientX - bounds.left - bounds.width / 2) / radius;
    let y = (event.clientY - bounds.top - bounds.height / 2) / radius;
    const length = Math.hypot(x, y);
    if (length > 1) { x /= length; y /= length; }
    vector = {x, y};
    thumb.style.transform = `translate(${x * radius}px, ${y * radius}px)`;
  }

  pad.addEventListener('pointerdown', (event) => {
    if (!online || sending || pointer !== null || event.button !== 0) return;
    event.preventDefault();
    pointer = event.pointerId;
    pad.setPointerCapture(pointer);
    pad.classList.add('held');
    message('');
    position(event);
    lastTick = 0;
    frame = requestAnimationFrame(tick);
  });
  pad.addEventListener('pointermove', (event) => { if (event.pointerId === pointer) { event.preventDefault(); position(event); } });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) pad.addEventListener(name, (event) => { if (event.pointerId === pointer) stopJoystick(); });
  pad.addEventListener('contextmenu', (event) => event.preventDefault());
  pad.addEventListener('keydown', (event) => {
    const directions = {ArrowLeft: [-8, 0], ArrowRight: [8, 0], ArrowUp: [0, -8], ArrowDown: [0, 8]};
    if (directions[event.key]) {
      event.preventDefault();
      const [dx, dy] = directions[event.key];
      discrete({action: 'move', dx, dy});
    }
  });

  $('screen-toggle').addEventListener('click', () => {
    stopJoystick();
    releaseHolds();
    const show = screen.hidden;
    screen.hidden = !show;
    $('media-screen').hidden = show;
    $('screen-toggle').setAttribute('aria-expanded', String(show));
    $('screen-toggle').setAttribute('aria-label', show ? 'Media controls' : 'Mouse and keyboard');
    $('screen-toggle').title = show ? 'Media controls' : 'Mouse and keyboard';
    $('screen-icon').setAttribute('href', show ? '#i-play' : '#i-mouse');
    message('');
    document.dispatchEvent(new Event('remotescreenchange'));
  });
  $('scroll-up').addEventListener('click', () => discrete({action: 'scroll', steps: 2}));
  $('scroll-down').addEventListener('click', () => discrete({action: 'scroll', steps: -2}));
  document.addEventListener('remotekey', event => discrete({action: 'key', key: event.detail.key, modifiers: event.detail.modifiers}));
  document.addEventListener('keybindschange', controls);
  async function sendText() {
    const text = $('type-text').value;
    if (!text) return;
    $('text-status').textContent = '';
    if (await discrete({action: 'text', text})) {
      $('type-text').value = '';
      $('text-status').textContent = 'Text sent';
      controls();
    }
  }
  $('send-text').addEventListener('click', sendText);
  $('type-text').addEventListener('input', () => { $('text-status').textContent = ''; controls(); });
  $('type-text').addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); sendText(); } });
  function stopInput() { stopJoystick(); releaseHolds(); }
  document.addEventListener('remoteconnection', (event) => { online = event.detail; if (!online) stopInput(); controls(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopInput(); });
  window.addEventListener('blur', stopInput);
  window.addEventListener('pagehide', stopInput);
  document.addEventListener('inputeditoropen', stopInput);
  controls();
})();
