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
  let draft;
  let editIndex = null;
  let drag = null;

  function validate(items, failure = 'Choose a supported key combination.') {
    if (!Array.isArray(items) || items.length > 64 || items.some(item =>
      !item ||
      !keymap.has(item.key) || !Array.isArray(item.modifiers) || item.modifiers.length > 4 ||
      item.modifiers.some(m => !['ctrl', 'alt', 'shift', 'win'].includes(m)) ||
      new Set(item.modifiers).size !== item.modifiers.length)) throw new Error(failure);
    return items;
  }

  function chord(item) {
    return [...item.modifiers.map(m => ({ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift', win: 'Win'}[m])), keymap.get(item.key).label].join('+');
  }

  function error(text = '') {
    $('keybind-error').textContent = text;
    $('keybind-error').hidden = !text;
  }

  function resetForm() {
    form.reset();
    editIndex = null;
    $('keybind-save').textContent = 'Add key';
    $('keybind-edit-cancel').hidden = true;
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

  function renderDraft() {
    list.replaceChildren(...draft.map((item, index) => {
      const row = document.createElement('li');
      row.dataset.index = index;
      const name = document.createElement('div');
      name.className = 'keybind-name';
      name.textContent = chord(item);
      name.tabIndex = 0;
      name.setAttribute('aria-label', `${chord(item)}. Drag to reorder, or use the up and down arrow keys.`);
      name.addEventListener('keydown', event => {
        if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        move(index, event.key === 'ArrowUp' ? -1 : 1);
      });
      row.append(name);
      for (const [text, title, action] of [
        ['Edit', `Edit ${chord(item)}`, () => edit(index)],
        ['×', `Delete ${chord(item)}`, () => remove(index)],
      ]) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = text; button.setAttribute('aria-label', title);
        button.addEventListener('click', action); row.append(button);
      }
      return row;
    }));
  }

  function hasEdits() {
    return editIndex !== null || keySelect.selectedIndex > 0 || modifiers.some(input => input.checked);
  }

  function remove(index) {
    if (hasEdits()) { error('Save or cancel the key you are editing before deleting.'); return; }
    draft.splice(index, 1); renderDraft(); error();
  }

  function move(index, direction) {
    if (hasEdits()) { error('Save or cancel the key you are editing before reordering.'); return; }
    const target = index + direction;
    if (target < 0 || target >= draft.length) return;
    [draft[index], draft[target]] = [draft[target], draft[index]];
    renderDraft(); error();
    list.children[target].querySelector('.keybind-name').focus();
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
    if (commit) {
      const target = [...list.children].filter(row => row !== current.row).indexOf(current.placeholder);
      draft.splice(target, 0, draft.splice(current.index, 1)[0]);
    }
    if (list.hasPointerCapture(current.pointer)) list.releasePointerCapture(current.pointer);
    renderDraft();
  }

  list.addEventListener('pointerdown', event => {
    if (event.button !== 0 || drag || !event.target.closest('.keybind-name')) return;
    if (hasEdits()) { error('Save or cancel the key you are editing before reordering.'); return; }
    event.preventDefault();
    const row = event.target.closest('li');
    const bounds = row.getBoundingClientRect();
    list.setPointerCapture(event.pointerId);
    const placeholder = document.createElement('li');
    placeholder.className = 'keybind-placeholder';
    placeholder.setAttribute('aria-hidden', 'true');
    placeholder.style.height = `${bounds.height}px`;
    row.before(placeholder);
    row.classList.add('dragging');
    row.inert = true;
    row.style.left = `${bounds.left}px`; row.style.width = `${bounds.width}px`; row.style.height = `${bounds.height}px`;
    drag = {row, placeholder, index: Number(row.dataset.index), pointer: event.pointerId, y: event.clientY, offset: event.clientY - bounds.top, tick: null, frame: null};
    error(); positionDrag();
    drag.frame = requestAnimationFrame(scrollDrag);
  });
  list.addEventListener('pointermove', event => {
    if (drag?.pointer !== event.pointerId) return;
    event.preventDefault(); drag.y = event.clientY; positionDrag();
  });
  list.addEventListener('pointerup', event => { if (drag?.pointer === event.pointerId) finishDrag(true); });
  for (const type of ['pointercancel', 'lostpointercapture']) list.addEventListener(type, event => { if (drag?.pointer === event.pointerId) finishDrag(false); });
  list.addEventListener('contextmenu', event => event.preventDefault());
  window.addEventListener('blur', () => finishDrag(false));
  document.addEventListener('visibilitychange', () => { if (document.hidden) finishDrag(false); });

  function edit(index) {
    if (hasEdits()) { error('Save or cancel the key you are editing first.'); return; }
    editIndex = index;
    const item = draft[index];
    keySelect.value = item.key;
    for (const input of modifiers) input.checked = item.modifiers.includes(input.value);
    $('keybind-save').textContent = 'Save key';
    $('keybind-edit-cancel').hidden = false;
    form.scrollIntoView({block: 'nearest'});
    error();
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const item = {key: keySelect.value, modifiers: modifiers.filter(input => input.checked).map(input => input.value)};
    try {
      validate([item]);
      if (item.key === 'delete' && item.modifiers.includes('ctrl') && item.modifiers.includes('alt')) throw new Error('Windows does not allow Ctrl+Alt+Delete through a remote shortcut.');
      if (editIndex === null) {
        if (draft.length === 64) throw new Error('You can save up to 64 keys.');
        draft.push(item);
      } else draft[editIndex] = item;
      resetForm(); renderDraft(); error();
    } catch (issue) { error(issue.message); }
  });
  form.addEventListener('input', () => { $('keybind-edit-cancel').hidden = !hasEdits(); });
  $('keybind-edit-cancel').addEventListener('click', () => { resetForm(); error(); });
  $('edit-keys').addEventListener('click', () => {
    document.dispatchEvent(new Event('inputeditoropen'));
    draft = saved.map(item => ({key: item.key, modifiers: [...item.modifiers]})); resetForm(); renderDraft(); error();
    dialog.showModal(); document.body.classList.add('editing-keys');
  });
  function close() { finishDrag(false); dialog.close(); document.body.classList.remove('editing-keys'); }
  for (const id of ['keys-cancel', 'keys-close']) $(id).addEventListener('click', close);
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  $('keys-done').addEventListener('click', () => {
    finishDrag(false);
    if (hasEdits()) { error('Save or cancel the key you are editing before tapping Done.'); return; }
    try {
      validate(draft);
      localStorage.setItem(storageKey, JSON.stringify(draft));
      saved = draft; renderKeys(); close();
    } catch (issue) { error(issue.message); }
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
