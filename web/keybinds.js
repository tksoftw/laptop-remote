'use strict';
(() => {
  const storageKey = 'laptop-remote-keys';
  const dialog = $('keybind-dialog');
  const form = $('keybind-form');
  const keySelect = $('keybind-key');
  const labelInput = $('keybind-label');
  const modifiers = [...$('keybind-modifiers').querySelectorAll('input')];
  let keymap;
  let saved;
  let draft;
  let editIndex = null;

  function validate(items, failure = 'Choose a key and a label of 1–24 characters.') {
    if (!Array.isArray(items) || items.length > 64 || items.some(item =>
      !item || typeof item.label !== 'string' || !item.label.trim() || item.label.length > 24 ||
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
      button.textContent = item.label;
      button.title = chord(item);
      button.setAttribute('aria-label', `${item.label}: ${chord(item)}`);
      button.addEventListener('click', () => document.dispatchEvent(new CustomEvent('remotekey', {detail: item})));
      return button;
    }));
    document.dispatchEvent(new Event('keybindschange'));
  }

  function renderDraft() {
    $('keybind-list').replaceChildren(...draft.map((item, index) => {
      const row = document.createElement('li');
      const name = document.createElement('div');
      const label = document.createElement('strong');
      label.textContent = item.label;
      const keys = document.createElement('small');
      keys.textContent = chord(item);
      name.append(label, keys);
      row.append(name);
      for (const [text, title, action, disabled] of [
        ['↑', `Move ${item.label} up`, () => move(index, -1), index === 0],
        ['↓', `Move ${item.label} down`, () => move(index, 1), index === draft.length - 1],
        ['Edit', `Edit ${item.label}`, () => edit(index), false],
        ['×', `Delete ${item.label}`, () => remove(index), false],
      ]) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = text; button.setAttribute('aria-label', title);
        button.disabled = disabled; button.addEventListener('click', action); row.append(button);
      }
      return row;
    }));
  }

  function hasEdits() {
    return editIndex !== null || labelInput.value.trim() || keySelect.selectedIndex > 0 || modifiers.some(input => input.checked);
  }

  function remove(index) {
    if (hasEdits()) { error('Save or cancel the key you are editing before deleting.'); return; }
    draft.splice(index, 1); renderDraft(); error();
  }

  function move(index, direction) {
    if (hasEdits()) { error('Save or cancel the key you are editing before reordering.'); return; }
    const target = index + direction;
    [draft[index], draft[target]] = [draft[target], draft[index]];
    renderDraft(); error();
  }

  function edit(index) {
    if (hasEdits()) { error('Save or cancel the key you are editing first.'); return; }
    editIndex = index;
    const item = draft[index];
    labelInput.value = item.label; keySelect.value = item.key;
    for (const input of modifiers) input.checked = item.modifiers.includes(input.value);
    $('keybind-save').textContent = 'Save key';
    $('keybind-edit-cancel').hidden = false;
    form.scrollIntoView({block: 'nearest'});
    error();
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const item = {label: labelInput.value.trim(), key: keySelect.value, modifiers: modifiers.filter(input => input.checked).map(input => input.value)};
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
    draft = saved.map(item => ({...item, modifiers: [...item.modifiers]})); resetForm(); renderDraft(); error();
    dialog.showModal(); document.body.classList.add('editing-keys');
  });
  function close() { dialog.close(); document.body.classList.remove('editing-keys'); }
  for (const id of ['keys-cancel', 'keys-close']) $(id).addEventListener('click', close);
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  $('keys-done').addEventListener('click', () => {
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
      saved = validate(stored === null ? ['backspace', 'enter', 'tab', 'escape'].map(key => ({label: keymap.get(key).label, key, modifiers: []})) : JSON.parse(stored), 'Saved keys are invalid. They have not been replaced.');
      renderKeys(); $('edit-keys').disabled = false;
    } catch (issue) { message(`Keys could not load: ${issue.message}`); }
  }
  load();
})();
