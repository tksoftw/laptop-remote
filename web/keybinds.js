'use strict';
(() => {
  const storageKey = 'laptop-remote-keys';
  const dialog = $('keybind-dialog');
  const list = $('keybind-list');
  const content = dialog.querySelector('.keybind-content');
  const form = $('keybind-form');
  const keySelect = $('keybind-key');
  const modifiers = [...$('keybind-modifiers').querySelectorAll('input')];
  let keymap;
  let saved;
  let editing = null;
  let adding = false;
  let drag = null;

  function validate(items, failure = 'Choose a supported key combination.') {
    if (!Array.isArray(items) || items.some(item =>
      !item ||
      !keymap.has(item.key) || !Array.isArray(item.modifiers) || item.modifiers.length > 4 ||
      item.modifiers.some(m => !['ctrl', 'alt', 'shift', 'win'].includes(m)) ||
      new Set(item.modifiers).size !== item.modifiers.length)) throw new Error(failure);
    if (items.length > 64) throw new Error('You can save up to 64 keys.');
    if (items.some(item => item.key === 'delete' && item.modifiers.includes('ctrl') && item.modifiers.includes('alt'))) throw new Error('Windows does not allow Ctrl+Alt+Delete through a remote shortcut.');
    return items;
  }

  function chord(item) {
    return [...item.modifiers.map(m => ({ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', win: 'Win'}[m])), keymap.get(item.key).label].join('+');
  }

  function error(text = '') {
    $('keybind-error').textContent = text;
    $('keybind-error').hidden = !text;
  }

  function syncForm() {
    keySelect.value = editing ? editing.key : '';
    keySelect.options[0].textContent = adding ? 'Choose a key…' : 'None';
    keySelect.disabled = editing === null && !adding;
    for (const input of modifiers) {
      input.checked = editing ? editing.modifiers.includes(input.value) : false;
      input.disabled = keySelect.disabled;
    }
  }

  function renderKeys() {
    $('key-actions').replaceChildren(...saved.map(item => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'input-button';
      button.textContent = chord(item);
      button.title = chord(item);
      button.setAttribute('aria-label', chord(item));
      button.addEventListener('click', () => document.dispatchEvent(new CustomEvent('remotekey', {detail: item})));
      return button;
    }));
    document.dispatchEvent(new Event('keybindschange'));
  }

  function renderList() {
    list.replaceChildren(...saved.map((item, index) => {
      const row = document.createElement('li');
      row.dataset.index = index;
      const name = document.createElement('div');
      name.className = 'keybind-name';
      name.textContent = chord(item);
      name.tabIndex = 0;
      name.setAttribute('role', 'button');
      name.setAttribute('aria-label', `${chord(item)}. Select to edit. Drag to reorder, or use the up and down arrow keys.`);
      name.addEventListener('click', event => { if (event.detail === 0) selectItem(index); });
      name.addEventListener('keydown', event => {
        if (['Enter', ' '].includes(event.key)) { event.preventDefault(); selectItem(index); return; }
        if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        move(index, event.key === 'ArrowUp' ? -1 : 1);
      });
      row.append(name);
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = '×'; button.setAttribute('aria-label', `Delete ${chord(item)}`);
      button.addEventListener('click', () => remove(index)); row.append(button);
      return row;
    }));
    updateSelection();
  }

  function updateSelection() {
    for (const row of list.children) {
      const selected = saved[Number(row.dataset.index)] === editing;
      row.classList.toggle('editing', selected);
      row.querySelector('.keybind-name').setAttribute('aria-pressed', String(selected));
    }
  }

  function save(items, selected) {
    try {
      validate(items);
      localStorage.setItem(storageKey, JSON.stringify(items));
    } catch (issue) {
      syncForm(); renderList();
      error(`Keys were not saved: ${issue.message}`);
      return false;
    }
    saved = items;
    editing = selected;
    adding = false;
    syncForm(); renderKeys(); renderList(); error();
    return true;
  }

  function remove(index) {
    finishDrag(false);
    save(saved.filter((_, position) => position !== index), saved[index] === editing ? null : editing);
  }

  function move(index, direction) {
    finishDrag(false);
    const target = index + direction;
    if (target < 0 || target >= saved.length) return;
    const items = [...saved];
    [items[index], items[target]] = [items[target], items[index]];
    if (save(items, editing)) list.children[target].querySelector('.keybind-name').focus();
  }

  function positionDrag() {
    const {row, placeholder, y, offset} = drag;
    row.style.top = `${y - offset}px`;
    const next = [...list.children].find(other => {
      if (other === row || other === placeholder) return false;
      const bounds = other.getBoundingClientRect();
      return y < bounds.top + bounds.height / 2;
    });
    list.insertBefore(placeholder, next || null);
  }

  function scrollDrag(timestamp) {
    if (!drag) return;
    const bounds = content.getBoundingClientRect();
    const edge = 48;
    const speed = drag.y < bounds.top + edge ? -Math.min(1, (bounds.top + edge - drag.y) / edge)
      : drag.y > bounds.bottom - edge ? Math.min(1, (drag.y - bounds.bottom + edge) / edge) : 0;
    const elapsed = drag.tick === null ? 0 : Math.min(timestamp - drag.tick, 32);
    drag.tick = timestamp;
    if (speed) { content.scrollTop += speed * elapsed * .6; positionDrag(); }
    drag.frame = requestAnimationFrame(scrollDrag);
  }

  function finishDrag(commit) {
    if (!drag) return;
    const current = drag;
    drag = null;
    cancelAnimationFrame(current.frame);
    if (list.hasPointerCapture(current.pointer)) list.releasePointerCapture(current.pointer);
    if (!current.placeholder) {
      if (commit) selectItem(current.index);
      return;
    }
    if (commit) {
      const target = [...list.children].filter(row => row !== current.row).indexOf(current.placeholder);
      const items = [...saved];
      items.splice(target, 0, items.splice(current.index, 1)[0]);
      save(items, editing);
    } else renderList();
  }

  list.addEventListener('pointerdown', event => {
    const row = event.target.closest('li');
    if (!event.isPrimary || event.button !== 0 || drag || !row || event.target.closest('button')) return;
    event.preventDefault();
    list.setPointerCapture(event.pointerId);
    drag = {row, index: Number(row.dataset.index), pointer: event.pointerId, startX: event.clientX, startY: event.clientY, y: event.clientY, placeholder: null, frame: null};
  });

  function startDrag() {
    const row = drag.row;
    const bounds = row.getBoundingClientRect();
    const placeholder = document.createElement('li');
    placeholder.className = 'keybind-placeholder';
    placeholder.setAttribute('aria-hidden', 'true');
    placeholder.style.height = `${bounds.height}px`;
    row.before(placeholder);
    row.classList.add('dragging');
    row.inert = true;
    row.style.left = `${bounds.left}px`; row.style.width = `${bounds.width}px`; row.style.height = `${bounds.height}px`;
    Object.assign(drag, {placeholder, offset: drag.startY - bounds.top, tick: null});
    error(); positionDrag();
    drag.frame = requestAnimationFrame(scrollDrag);
  }

  list.addEventListener('pointermove', event => {
    if (drag?.pointer !== event.pointerId) return;
    event.preventDefault(); drag.y = event.clientY;
    if (!drag.placeholder) {
      if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 6) return;
      startDrag();
    } else positionDrag();
  });
  list.addEventListener('pointerup', event => { if (drag?.pointer === event.pointerId) finishDrag(true); });
  for (const type of ['pointercancel', 'lostpointercapture']) list.addEventListener(type, event => { if (drag?.pointer === event.pointerId) finishDrag(false); });
  list.addEventListener('contextmenu', event => event.preventDefault());
  window.addEventListener('blur', () => finishDrag(false));
  document.addEventListener('visibilitychange', () => { if (document.hidden) finishDrag(false); });
  // A second finger or viewport movement belongs to the browser's zoom gesture.
  dialog.addEventListener('pointerdown', event => { if (!event.isPrimary) finishDrag(false); }, {capture: true});
  for (const type of ['resize', 'scroll']) window.visualViewport.addEventListener(type, () => finishDrag(false));

  function selectItem(index) {
    finishDrag(false);
    editing = saved[index];
    adding = false;
    syncForm(); updateSelection();
    form.scrollIntoView({block: 'nearest'});
    error();
  }

  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('change', () => {
    if (!keySelect.value || (editing === null && !adding)) return;
    finishDrag(false);
    const item = {key: keySelect.value, modifiers: modifiers.filter(input => input.checked).map(input => input.value)};
    const items = [...saved];
    if (editing === null) items.push(item);
    else items[saved.indexOf(editing)] = item;
    save(items, item);
  });
  $('keybind-add').addEventListener('click', () => {
    finishDrag(false);
    editing = null; adding = true; syncForm(); updateSelection(); error();
    form.scrollIntoView({block: 'nearest'}); keySelect.focus();
  });
  function deselect() {
    finishDrag(false);
    editing = null; adding = false; syncForm(); updateSelection(); error();
  }
  dialog.addEventListener('pointerdown', event => {
    if (event.isPrimary && (editing !== null || adding) && !event.target.closest('#keybind-list li, #keybind-form, #keybind-add, form[method="dialog"]')) deselect();
  });
  $('edit-keys').addEventListener('click', () => {
    document.dispatchEvent(new Event('inputeditoropen'));
    deselect(); renderList();
    dialog.showModal(); document.body.classList.add('editing-keys');
  });
  // Native dialog forms close first; selection cleanup must never trap the user.
  dialog.addEventListener('close', () => {
    document.body.classList.remove('editing-keys');
    deselect();
  });

  async function load() {
    try {
      const response = await fetch('/keymap.json', {cache: 'no-store'});
      if (!response.ok) throw new Error('The key list could not load. Reopen Laptop Remote.');
      const entries = await response.json();
      keymap = new Map(entries.map(item => [item.key, item]));
      for (const item of entries) keySelect.add(new Option(item.label, item.key));
      const stored = localStorage.getItem(storageKey);
      saved = validate(stored === null ? ['backspace', 'enter', 'tab', 'escape'].map(key => ({key, modifiers: []})) : JSON.parse(stored), 'Saved keys are invalid. They have not been replaced.');
      renderKeys(); $('edit-keys').disabled = false;
    } catch (issue) { message(`Keys could not load: ${issue.message}`); }
  }
  load();
})();
