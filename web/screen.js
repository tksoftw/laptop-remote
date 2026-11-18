'use strict';
(() => {
  const checkbox = $('show-screen');
  const panel = $('live-screen');
  const viewport = $('screen-viewport');
  const picture = $('screen-image');
  const status = $('screen-status');
  const dialog = $('screen-crop-dialog');
  const slider = $('crop-zoom');
  const pointers = new Map();
  let online = Boolean(latest);
  let running = false;
  let failed = false;
  let timer;
  let abort;
  let generation = 0;
  let imageUrl;
  let snapshotReady = false;
  let view = {x: 0.5, y: 0.5, zoom: 1};
  let savedView;
  let gesture;
  let screenRatio = 16 / 9;

  checkbox.checked = localStorage.getItem('laptop-remote-show-screen') === 'true';

  function active() {
    return checkbox.checked && online && !$('desktop-screen').hidden && !document.hidden;
  }

  function clearImage() {
    picture.hidden = true;
    picture.removeAttribute('src');
    if (imageUrl) URL.revokeObjectURL(imageUrl);
    imageUrl = undefined;
    picture.style.transform = '';
    setCropReady(false);
  }

  function stop() {
    running = false;
    generation++;
    clearTimeout(timer);
    abort?.abort();
    clearImage();
    pointers.clear();
    gesture = null;
  }

  async function frame(ticket, still = false) {
    const controller = new AbortController();
    abort = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    let pendingUrl;
    try {
      const requestedView = still ? {x: 0.5, y: 0.5, zoom: 1} : view;
      const response = await fetch('/api/screen?' + new URLSearchParams(requestedView), {
        headers: {'X-Remote-Request': '1'}, credentials: 'same-origin',
        cache: 'no-store', signal: controller.signal,
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || `Screen request failed (${response.status}).`);
      }
      if (!(response.headers.get('Content-Type') || '').startsWith('image/jpeg')) throw new Error('The laptop returned an invalid screen frame.');
      const width = Number(response.headers.get('X-Screen-Width'));
      const height = Number(response.headers.get('X-Screen-Height'));
      if (!(width > 0 && height > 0)) throw new Error('The laptop returned invalid screen dimensions.');
      pendingUrl = URL.createObjectURL(await response.blob());
      const next = new Image();
      next.src = pendingUrl;
      await next.decode();
      if (ticket !== generation || (still ? !dialog.open : !active() || dialog.open)) return;
      const previous = imageUrl;
      imageUrl = pendingUrl;
      pendingUrl = undefined;
      picture.src = imageUrl;
      picture.hidden = false;
      viewport.style.aspectRatio = `${width} / ${height}`;
      screenRatio = width / height;
      fitEditor();
      if (still) {
        setCropReady(true);
        paintCrop();
      }
      status.textContent = '';
      status.hidden = true;
      if (previous) URL.revokeObjectURL(previous);
      if (!still) timer = setTimeout(() => frame(ticket), 150);
    } catch (error) {
      if (ticket !== generation || (still ? !dialog.open : !active() || dialog.open)) return;
      failed = true;
      stop();
      status.hidden = false;
      status.textContent = error.name === 'AbortError' ? 'The screen preview timed out. Tap Retry.' : error.message;
      $('screen-retry').hidden = false;
      $('crop-retry').hidden = !still;
    } finally {
      clearTimeout(timeout);
      if (pendingUrl) URL.revokeObjectURL(pendingUrl);
      if (abort === controller) abort = undefined;
    }
  }

  function sync() {
    $('advanced-screen').hidden = $('desktop-screen').hidden;
    panel.hidden = !checkbox.checked;
    $('desktop-heading').hidden = checkbox.checked;
    $('screen-crop').disabled = !online;
    // A crop session owns one frozen, full-screen image. Media-state polls and
    // foreground events must never restart the live frame loop inside it.
    if (dialog.open && checkbox.checked && !$('desktop-screen').hidden) return;
    if (!active()) {
      if (dialog.open && ($('desktop-screen').hidden || !checkbox.checked)) finishCrop(false);
      stop();
      failed = false;
      status.hidden = false;
      status.textContent = online ? 'Connecting…' : 'Connect to your laptop to see its screen.';
      $('screen-retry').hidden = true;
      return;
    }
    if (!running && !failed) {
      running = true;
      status.hidden = false;
      status.textContent = 'Connecting…';
      frame(++generation);
    }
  }

  function setView(next) {
    const zoom = Math.max(1, Math.min(6, next.zoom));
    const half = 0.5 / zoom;
    view = {zoom, x: Math.max(half, Math.min(1 - half, next.x)), y: Math.max(half, Math.min(1 - half, next.y))};
    slider.value = zoom;
    slider.style.setProperty('--fill', `${(zoom - 1) * 20}%`);
    $('crop-zoom-value').textContent = `${Number(zoom.toFixed(2))}×`;
    paintCrop();
  }

  function setCropReady(ready) {
    snapshotReady = ready;
    for (const id of ['crop-zoom', 'crop-fit', 'crop-done']) $(id).disabled = !ready;
  }

  function paintCrop() {
    if (!dialog.open || !snapshotReady) return;
    const x = (0.5 - view.x * view.zoom) * 100;
    const y = (0.5 - view.y * view.zoom) * 100;
    picture.style.transform = `translate3d(${x}%, ${y}%, 0) scale(${view.zoom})`;
  }

  function loadStill() {
    stop();
    failed = false;
    $('crop-retry').hidden = true;
    $('screen-retry').hidden = true;
    status.hidden = false;
    status.textContent = 'Connecting…';
    frame(++generation, true);
  }

  function startCrop() {
    savedView = {...view};
    $('crop-stage').append(viewport);
    dialog.showModal();
    document.body.classList.add('cropping');
    fitEditor();
    setView(view);
    loadStill();
  }

  function finishCrop(save) {
    if (!dialog.open) return;
    if (save && !snapshotReady) return;
    if (!save) setView(savedView);
    pointers.clear();
    gesture = null;
    panel.prepend(viewport);
    viewport.style.width = '';
    viewport.style.height = '';
    dialog.close();
    document.body.classList.remove('cropping');
    stop();
    failed = false;
    $('screen-retry').hidden = true;
    sync();
  }

  function fitEditor() {
    if (!dialog.open) return;
    const stage = $('crop-stage');
    const width = Math.min(stage.clientWidth, stage.clientHeight * screenRatio);
    viewport.style.width = `${width}px`;
    viewport.style.height = `${width / screenRatio}px`;
  }
  new ResizeObserver(fitEditor).observe($('crop-stage'));

  function gestureStart() {
    const points = [...pointers.values()];
    if (!points.length) { gesture = null; return; }
    const a = points[0], b = points[1] || a;
    gesture = {view: {...view}, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, distance: Math.hypot(a.x - b.x, a.y - b.y)};
  }

  viewport.addEventListener('pointerdown', event => {
    if (!dialog.open || !snapshotReady || event.button !== 0 || pointers.size >= 2) return;
    event.preventDefault();
    viewport.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    gestureStart();
  });
  viewport.addEventListener('pointermove', event => {
    if (!pointers.has(event.pointerId) || !gesture) return;
    event.preventDefault();
    pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
    const points = [...pointers.values()], a = points[0], b = points[1] || a;
    const x = (a.x + b.x) / 2, y = (a.y + b.y) / 2;
    const distance = Math.hypot(a.x - b.x, a.y - b.y);
    const zoom = Math.max(1, Math.min(6, gesture.distance > 0 ? gesture.view.zoom * distance / gesture.distance : gesture.view.zoom));
    const bounds = viewport.getBoundingClientRect();
    const anchorX = (gesture.x - bounds.left) / bounds.width - 0.5;
    const anchorY = (gesture.y - bounds.top) / bounds.height - 0.5;
    setView({zoom,
      x: gesture.view.x + anchorX / gesture.view.zoom - ((x - bounds.left) / bounds.width - 0.5) / zoom,
      y: gesture.view.y + anchorY / gesture.view.zoom - ((y - bounds.top) / bounds.height - 0.5) / zoom,
    });
  });
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) viewport.addEventListener(type, event => {
    pointers.delete(event.pointerId);
    gestureStart();
  });
  viewport.addEventListener('contextmenu', event => event.preventDefault());
  viewport.addEventListener('wheel', event => {
    if (!dialog.open || !snapshotReady) return;
    event.preventDefault();
    setView({...view, zoom: view.zoom * Math.exp(-event.deltaY * 0.002)});
  }, {passive: false});
  viewport.addEventListener('keydown', event => {
    if (!dialog.open || !snapshotReady) return;
    const moves = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
    if (!moves[event.key]) return;
    event.preventDefault();
    const [dx, dy] = moves[event.key];
    setView({...view, x: view.x + dx * 0.05 / view.zoom, y: view.y + dy * 0.05 / view.zoom});
  });
  slider.addEventListener('input', () => setView({...view, zoom: Number(slider.value)}));
  $('crop-fit').addEventListener('click', () => setView({x: 0.5, y: 0.5, zoom: 1}));
  $('crop-done').addEventListener('click', () => finishCrop(true));
  for (const id of ['crop-cancel', 'crop-close']) $(id).addEventListener('click', () => finishCrop(false));
  dialog.addEventListener('cancel', event => { event.preventDefault(); finishCrop(false); });
  $('screen-crop').addEventListener('click', startCrop);
  $('crop-retry').addEventListener('click', loadStill);
  $('screen-retry').addEventListener('click', () => { failed = false; $('screen-retry').hidden = true; sync(); });
  checkbox.addEventListener('change', () => {
    localStorage.setItem('laptop-remote-show-screen', String(checkbox.checked));
    sync();
  });
  document.addEventListener('remoteconnection', event => { online = event.detail; sync(); });
  document.addEventListener('remotescreenchange', sync);
  document.addEventListener('visibilitychange', sync);
  window.addEventListener('pagehide', () => { finishCrop(false); stop(); });
  window.addEventListener('pageshow', sync);
  sync();
})();
