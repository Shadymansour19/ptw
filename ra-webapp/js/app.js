/* Main UI wiring. Plain DOM, no framework - this is a small, local tool. */

let editingItemId = null;
let pendingExportKind = null; // 'pdf' | 'word' | 'print'

// Monochrome SVG icons for the items-table row actions. Plain inline
// outline shapes (not emoji) so color is fully controllable via CSS
// `currentColor` - neutral by default, colored only on :hover.
const ICON_EDIT = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M13.5 2.5l4 4L7 17l-5 1 1-5L13.5 2.5z"/><path d="M12 4l4 4"/></svg>';
const ICON_DELETE = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h12"/><path d="M8 6V4h4v2"/><path d="M5.5 6l1 10a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1l1-10"/><path d="M8.5 9v5"/><path d="M11.5 9v5"/></svg>';
const ICON_DRAG = '<svg viewBox="0 0 20 20" fill="currentColor"><circle cx="7" cy="4" r="1.3"/><circle cx="13" cy="4" r="1.3"/><circle cx="7" cy="10" r="1.3"/><circle cx="13" cy="10" r="1.3"/><circle cx="7" cy="16" r="1.3"/><circle cx="13" cy="16" r="1.3"/></svg>';

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return Array.from(document.querySelectorAll(sel)); }

function toast(msg, ms = 2600) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, ms);
}

/* ---------------- auto-translate (EN -> AR) ---------------- */

async function runTranslateButton(btn, fieldPairs) {
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Translating…';
  try {
    await Promise.all(fieldPairs.map(async ([enId, arId]) => {
      const enEl = $(enId);
      const enText = enEl.value.trim();
      if (!enText) return;
      const ar = await translateEnToAr(enText);
      $(arId).value = ar;
    }));
    toast('Translated - please review the Arabic text before saving.');
  } catch (err) {
    console.error(err);
    toast('Translation failed - check your internet connection and try again.', 4000);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

/* ---------------- meta panel ---------------- */

function fillMetaPanel() {
  const p = Store.project;
  $('#meta-title-en').value = p.title.en || '';
  $('#meta-location-en').value = p.location.en || '';
  $('#meta-ptw-number').value = p.ptwNumber || '';
  $('#meta-date').value = formatDDMMYYYY(p.date);
  $('#meta-date-picker').value = p.date || '';
}

function wireMetaPanel() {
  const bind = (id, path) => {
    $(id).addEventListener('input', (e) => {
      const [field, lang] = path;
      if (lang) Store.project[field][lang] = e.target.value;
      else Store.project[field] = e.target.value;
      Store.save();
    });
  };
  bind('#meta-title-en', ['title', 'en']);
  bind('#meta-location-en', ['location', 'en']);
  bind('#meta-ptw-number', ['ptwNumber', null]);

  // Date keeps a hidden native <input type="date"> purely for its calendar
  // picker (showPicker()) - the visible field always displays dd/mm/yyyy,
  // since the native picker's own displayed text follows the browser's
  // locale (often mm/dd/yyyy) and can't be forced to a fixed format.
  $('#btn-meta-date-pick').addEventListener('click', () => {
    const picker = $('#meta-date-picker');
    if (picker.showPicker) picker.showPicker();
    else picker.focus();
  });
  $('#meta-date-picker').addEventListener('change', (e) => {
    Store.project.date = e.target.value;
    Store.save();
    $('#meta-date').value = formatDDMMYYYY(Store.project.date);
  });
}

/* ---------------- items table ---------------- */

function renderItemsTable() {
  const tbody = $('#items-tbody');
  const items = Store.project.items;
  tbody.innerHTML = '';
  $('#empty-hint').hidden = items.length > 0;

  items.forEach((item, idx) => {
    const tr = document.createElement('tr');
    tr.dataset.id = item.id;
    const evaluation = evaluateRisk(item.severityAfter, item.likelihoodAfter);

    const biCell = (field) => {
      const en = field?.en ? `<div class="cell-en">${escapeHtml(field.en)}</div>` : '';
      const ar = field?.ar ? `<div class="cell-ar" dir="rtl">${escapeHtml(field.ar)}</div>` : '';
      return en + ar || '&nbsp;';
    };
    const sub = (v) => `<td class="col-sub">${v}</td>`;
    const evalBadge = (risk) => (risk ? `<span class="badge" style="background:${risk.bg};color:${risk.color}">${risk.en}</span>` : '');

    tr.innerHTML = `
      <td class="col-actions">
        <div class="row-actions">
          <span class="row-actions-btn drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag to reorder">${ICON_DRAG}</span>
          <button class="row-actions-btn" data-action="edit" data-id="${item.id}" title="Edit" aria-label="Edit">${ICON_EDIT}</button>
          <button class="row-actions-btn" data-action="delete" data-id="${item.id}" title="Delete" aria-label="Delete">${ICON_DELETE}</button>
        </div>
      </td>
      <td class="col-no">${idx + 1}</td>
      <td>${biCell(item.hazard)}</td>
      <td>${biCell(item.effect)}</td>
      ${sub(item.severityBefore)}
      ${sub(item.likelihoodBefore)}
      ${sub(`${item.severityBefore}${item.likelihoodBefore}`)}
      <td>${biCell(item.ctrl)}</td>
      ${sub(item.severityAfter)}
      ${sub(item.likelihoodAfter)}
      ${sub(`${item.severityAfter}${item.likelihoodAfter}`)}
      <td class="col-eval">${evalBadge(evaluation)}</td>`;
    tbody.appendChild(tr);
  });
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/* ---------------- item dialog (add/edit) ---------------- */

function populateLevelSelects() {
  const sevHtml = SEVERITY_VALUES.map((v) => `<option value="${v}">${v}</option>`).join('');
  const likHtml = LIKELIHOOD_VALUES.map((v) => `<option value="${v}">${v}</option>`).join('');
  ['#f-sev-before', '#f-sev-after'].forEach((id) => { $(id).innerHTML = sevHtml; });
  ['#f-lik-before', '#f-lik-after'].forEach((id) => { $(id).innerHTML = likHtml; });
}

function refreshDialogBadges() {
  $('#f-eval-before').textContent = `${$('#f-sev-before').value}${$('#f-lik-before').value}`;
  $('#f-ctrl-code-after').textContent = `${$('#f-sev-after').value}${$('#f-lik-after').value}`;

  const evaluation = evaluateRisk(Number($('#f-sev-after').value), $('#f-lik-after').value);
  const el = $('#f-eval-after');
  if (!evaluation) { el.textContent = ''; el.style.background = ''; return; }
  el.textContent = evaluation.en;
  el.style.background = evaluation.bg;
  el.style.color = evaluation.color;
}

function openItemDialog(item) {
  editingItemId = item ? item.id : null;
  $('#item-dialog-title').textContent = item ? 'Edit Risk Item' : 'Add Risk Item';

  const src = item || blankItem();
  $('#f-hazard-en').value = src.hazard.en;
  $('#f-hazard-ar').value = src.hazard.ar;
  $('#f-effect-en').value = src.effect.en;
  $('#f-effect-ar').value = src.effect.ar;
  $('#f-ctrl-en').value = src.ctrl.en;
  $('#f-ctrl-ar').value = src.ctrl.ar;
  $('#f-sev-before').value = src.severityBefore;
  $('#f-lik-before').value = src.likelihoodBefore;
  $('#f-sev-after').value = src.severityAfter;
  $('#f-lik-after').value = src.likelihoodAfter;

  refreshDialogBadges();
  // Back to default heights each time the dialog opens (rows attribute).
  ['#f-hazard-en', '#f-hazard-ar', '#f-effect-en', '#f-effect-ar', '#f-ctrl-en', '#f-ctrl-ar']
    .forEach((sel) => { $(sel).style.height = ''; });
  $('#item-dialog').showModal();
}

function readItemForm() {
  return {
    id: editingItemId || blankItem().id,
    hazard: { en: $('#f-hazard-en').value.trim(), ar: $('#f-hazard-ar').value.trim() },
    effect: { en: $('#f-effect-en').value.trim(), ar: $('#f-effect-ar').value.trim() },
    severityBefore: Number($('#f-sev-before').value),
    likelihoodBefore: $('#f-lik-before').value,
    ctrl: { en: $('#f-ctrl-en').value.trim(), ar: $('#f-ctrl-ar').value.trim() },
    severityAfter: Number($('#f-sev-after').value),
    likelihoodAfter: $('#f-lik-after').value,
  };
}

/* Resizing the EN or AR box of a pair resizes its partner to the same height. */
function linkTextareaHeights(selA, selB) {
  const a = $(selA);
  const b = $(selB);
  let syncing = false;
  const sync = (src, dst) => {
    if (syncing) return;
    const h = src.offsetHeight;
    if (!h || Math.abs(dst.offsetHeight - h) < 1) return;
    syncing = true;
    dst.style.height = `${h}px`;
    requestAnimationFrame(() => { syncing = false; });
  };
  const ro = new ResizeObserver((entries) => {
    entries.forEach((e) => (e.target === a ? sync(a, b) : sync(b, a)));
  });
  ro.observe(a);
  ro.observe(b);
}

function wireItemDialog() {
  linkTextareaHeights('#f-hazard-en', '#f-hazard-ar');
  linkTextareaHeights('#f-effect-en', '#f-effect-ar');
  linkTextareaHeights('#f-ctrl-en', '#f-ctrl-ar');
  populateLevelSelects();
  ['#f-sev-before', '#f-lik-before', '#f-sev-after', '#f-lik-after'].forEach((id) => {
    $(id).addEventListener('change', refreshDialogBadges);
  });

  $('#btn-add-manual').addEventListener('click', () => openItemDialog(null));
  $('#btn-item-cancel').addEventListener('click', () => $('#item-dialog').close());

  $('#btn-item-translate').addEventListener('click', (e) => {
    runTranslateButton(e.target, [
      ['#f-hazard-en', '#f-hazard-ar'],
      ['#f-effect-en', '#f-effect-ar'],
      ['#f-ctrl-en', '#f-ctrl-ar'],
    ]);
  });

  $('#btn-item-save').addEventListener('click', () => {
    const hazard = $('#f-hazard-en').value.trim();
    if (!hazard) {
      toast('Hazard (EN) is required.');
      return;
    }
    const data = readItemForm();
    if (editingItemId) {
      Store.updateItem(editingItemId, data);
    } else {
      const added = Store.addItem(data);
      if (!added.length) {
        toast('An identical risk item (same Hazard/Effect/Control) already exists - not added.', 4000);
        return;
      }
    }
    $('#item-dialog').close();
    renderItemsTable();
  });

  $('#items-tbody').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const id = btn.dataset.id;
    if (btn.dataset.action === 'edit') {
      const item = Store.project.items.find((i) => i.id === id);
      if (item) openItemDialog(item);
    } else if (btn.dataset.action === 'delete') {
      if (confirm('Delete this risk item?')) {
        Store.deleteItem(id);
        renderItemsTable();
      }
    }
  });
}

/* Show/hide Arabic text in the on-screen items table only - a preview
   convenience, never affects PDF/Word export or any stored data. */
function wireArabicPreviewToggle() {
  const btn = $('#btn-toggle-arabic');
  btn.addEventListener('click', () => {
    const hidden = $('#items-table').classList.toggle('hide-arabic');
    btn.textContent = hidden ? 'Show Arabic (Preview)' : 'Hide Arabic (Preview)';
    btn.setAttribute('aria-pressed', String(hidden));
  });
}

/* Drag-and-drop row reordering (desktop only - no touch support needed).
   Only the ".drag-handle" icon is draggable, so selecting text or clicking
   Edit/Delete elsewhere in the row never starts a drag. */
function wireItemsReorder() {
  const tbody = $('#items-tbody');
  let draggedRow = null;

  tbody.addEventListener('dragstart', (e) => {
    const handle = e.target.closest('.drag-handle');
    const row = handle && handle.closest('tr');
    if (!row) { e.preventDefault(); return; }
    draggedRow = row;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', row.dataset.id);
    row.classList.add('dragging');
  });

  tbody.addEventListener('dragover', (e) => {
    if (!draggedRow) return;
    e.preventDefault();
    const row = e.target.closest('tr');
    if (!row || row === draggedRow) return;
    const rect = row.getBoundingClientRect();
    const before = (e.clientY - rect.top) < rect.height / 2;
    row.parentNode.insertBefore(draggedRow, before ? row : row.nextSibling);
  });

  tbody.addEventListener('drop', (e) => e.preventDefault());

  tbody.addEventListener('dragend', () => {
    if (!draggedRow) return;
    draggedRow.classList.remove('dragging');
    const orderedIds = Array.from(tbody.querySelectorAll('tr')).map((tr) => tr.dataset.id);
    draggedRow = null;
    Store.reorderItems(orderedIds);
    renderItemsTable();
  });
}

/* ---------------- library dialog ---------------- */

// Checked RAs (by category index) must survive re-rendering the list as the
// user adjusts the search filter - otherwise every re-render creates fresh
// unchecked checkboxes and silently drops the selection.
let selectedLibraryCats = new Set();

function renderLibraryList(filterText = '') {
  // A generic RA is a complete named assessment (e.g. "Use of Hand Tools"),
  // not a pick-list of individual hazards - so this only ever shows RA
  // titles, one row each. Picking one adds every item under it.
  const host = $('#library-list');
  host.innerHTML = '';
  const ft = filterText.trim().toLowerCase();

  const searchContentToo = $('#library-search-content').checked;

  GLOBAL_RA_LIBRARY.forEach((cat, catIdx) => {
    if (ft) {
      const haystackParts = [cat.category.en, cat.category.ar];
      if (searchContentToo) {
        haystackParts.push(...cat.items.flatMap((item) => [item.hazard.en, item.hazard.ar, item.effect.en, item.effect.ar]));
      }
      const haystack = haystackParts.join(' ').toLowerCase();
      if (!haystack.includes(ft)) return;
    }

    const row = document.createElement('label');
    row.className = 'library-item';
    const checked = selectedLibraryCats.has(catIdx) ? 'checked' : '';
    row.innerHTML = `
      <input type="checkbox" data-cat="${catIdx}" ${checked}>
      <span class="item-text">
        <span class="en"><strong>${escapeHtml(cat.category.en)}</strong> (${cat.items.length} item${cat.items.length === 1 ? '' : 's'})</span>
      </span>`;
    host.appendChild(row);
  });

  if (!host.children.length) {
    host.innerHTML = '<p style="padding:14px;color:var(--muted)">No matches.</p>';
  }
}

function wireLibraryDialog() {
  $('#btn-add-library').addEventListener('click', () => {
    selectedLibraryCats = new Set();
    renderLibraryList('');
    $('#library-search').value = '';
    $('#library-dialog').showModal();
  });
  $('#btn-library-close').addEventListener('click', () => $('#library-dialog').close());
  $('#library-search').addEventListener('input', (e) => renderLibraryList(e.target.value));
  $('#library-search-content').addEventListener('change', () => renderLibraryList($('#library-search').value));
  $('#library-list').addEventListener('change', (e) => {
    const cb = e.target.closest('input[type="checkbox"][data-cat]');
    if (!cb) return;
    const catIdx = Number(cb.dataset.cat);
    if (cb.checked) selectedLibraryCats.add(catIdx);
    else selectedLibraryCats.delete(catIdx);
  });

  $('#btn-library-add').addEventListener('click', () => {
    const checked = $all('#library-list input[type="checkbox"]:checked');
    if (!checked.length) { toast('Select at least one RA.'); return; }
    const newItems = checked.flatMap((cb) => {
      const cat = GLOBAL_RA_LIBRARY[Number(cb.dataset.cat)];
      return cat.items.map((source) => ({ ...blankItem(), ...JSON.parse(JSON.stringify(source)) }));
    });
    const added = Store.addItems(newItems);
    renderItemsTable();
    $('#library-dialog').close();
    const skipped = newItems.length - added.length;
    toast(`Added ${added.length} item(s) from the library.${skipped ? ` (${skipped} duplicate(s) skipped.)` : ''}`);
  });
}

/* ---------------- excel import ---------------- */

function wireExcelImport() {
  $('#btn-template-excel').addEventListener('click', () => downloadExcelTemplate());

  $('#btn-import-excel').addEventListener('click', () => $('#file-import-excel').click());
  $('#file-import-excel').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    try {
      const { items, errors } = await parseRiskExcelFile(file);
      let added = [];
      if (items.length) {
        added = Store.addItems(items);
        renderItemsTable();
      }
      const body = $('#import-result-body');
      const duplicateCount = items.length - added.length;
      let html = `<p>${added.length} item(s) imported successfully.${duplicateCount ? ` (${duplicateCount} duplicate(s) skipped.)` : ''}</p>`;
      if (errors.length) {
        html += `<p>${errors.length} row(s) skipped:</p><ul>${errors.map((er) => `<li>${escapeHtml(er)}</li>`).join('')}</ul>`;
      }
      body.innerHTML = html;
      $('#import-result-dialog').showModal();
    } catch (err) {
      alert(`Import failed: ${err.message}`);
    }
  });

  $('#btn-import-result-close').addEventListener('click', () => $('#import-result-dialog').close());
}

/* ---------------- auto-translate all risk items ---------------- */

const TRANSLATE_FIELDS = ['hazard', 'effect', 'ctrl'];

async function translateMultiline(text, cache) {
  // Line by line, so bullet-per-line formatting survives and each request
  // stays well under the service's per-query size limit. Repeated lines
  // (common across items) are translated once via the shared cache.
  const out = [];
  for (const line of String(text || '').split('\n')) {
    const t = line.trim();
    if (!t) { out.push(''); continue; }
    if (!cache.has(t)) cache.set(t, await translateEnToAr(t));
    out.push(cache.get(t));
  }
  return out.join('\n');
}

function wireTranslateAll() {
  const btn = $('#btn-translate-all');
  const dialog = $('#translate-mode-dialog');
  const hasEn = (it, f) => (it[f]?.en || '').trim();
  const hasAr = (it, f) => (it[f]?.ar || '').trim();

  const collectJobs = (mode) => {
    const jobs = [];
    Store.project.items.forEach((it) => TRANSLATE_FIELDS.forEach((f) => {
      if (hasEn(it, f) && (mode === 'all' || !hasAr(it, f))) jobs.push([it.id, f]);
    }));
    return jobs;
  };

  btn.addEventListener('click', () => {
    if (!Store.project.items.length) { toast('No risk items to translate.'); return; }

    const emptyCount = collectJobs('empty').length;
    const totalCount = collectJobs('all').length;
    const filledCount = totalCount - emptyCount;
    if (!totalCount) { toast('Nothing to translate - no English text found.'); return; }

    // Nothing already in Arabic -> nothing to protect, just translate.
    if (!filledCount) { runTranslateJobs(btn, collectJobs('empty')); return; }

    // Some fields already have Arabic (e.g. library items) -> ask first.
    // Default is always "Empty only".
    $('#translate-mode-summary').textContent =
      `${emptyCount} field(s) have no Arabic yet, ${filledCount} field(s) already have Arabic text.`;
    $('input[name="translate-mode"][value="empty"]').checked = true;
    dialog.showModal();
  });

  $('#btn-translate-mode-cancel').addEventListener('click', () => dialog.close());
  $('#btn-translate-mode-go').addEventListener('click', () => {
    const mode = $('input[name="translate-mode"]:checked').value;
    dialog.close();
    if (mode === 'empty' && !collectJobs('empty').length) { toast('All fields already have Arabic - nothing to translate.'); return; }
    if (mode === 'all' && !confirm('Overwrite ALL existing Arabic text (including your edits and the library\'s built-in Arabic)?')) return;
    runTranslateJobs(btn, collectJobs(mode));
  });
}

async function runTranslateJobs(btn, jobs) {
  if (!jobs.length) { toast('Nothing to translate.'); return; }

  const original = btn.textContent;
  btn.disabled = true;
  const cache = new Map();
  let done = 0;
  let failed = 0;
  let next = 0;

  const worker = async () => {
    while (next < jobs.length) {
      const [id, f] = jobs[next];
      next += 1;
      const item = Store.project.items.find((i) => i.id === id);
      if (item) {
        try {
          // eslint-disable-next-line no-await-in-loop
          const ar = await translateMultiline(item[f].en, cache);
          Store.updateItem(id, { [f]: { ...item[f], ar } });
          renderItemsTable();
        } catch (err) {
          console.error(err);
          failed += 1;
        }
      }
      done += 1;
      btn.textContent = `Translating ${done}/${jobs.length}…`;
    }
  };

  try {
    await Promise.all([worker(), worker(), worker()]); // 3 requests at a time
  } finally {
    btn.disabled = false;
    btn.textContent = original;
    renderItemsTable();
  }

  if (failed) {
    toast(`Translated ${jobs.length - failed} of ${jobs.length} fields - ${failed} failed (check internet or the daily free limit).`, 6000);
  } else {
    toast(`Translated ${jobs.length} field(s) - please review the Arabic text.`, 4000);
  }
}

/* ---------------- export RA to general library ---------------- */

const LIB_FILE_PATH = 'js/globalRisks.js';
const LIB_FILE_HEADER = `/*
 * GLOBAL / GENERAL RISK ASSESSMENT LIBRARY
 * =========================================
 * Editable static library of complete generic RAs, one category per RA.
 * Picking a category in "Add from General RA Library" adds all its items.
 * Plain data - nothing else in the app needs to change when you edit it.
 *
 * Item shape (same as a manually-entered risk item):
 *   hazard, effect, ctrl -> { en, ar }   (multiple lines separated by \\n)
 *   severityBefore (1-5), likelihoodBefore (A-E)  - Free Analysis
 *   severityAfter (1-5), likelihoodAfter (A-E)    - Controlled Analysis
 * Evaluation is calculated from the controlled code via matrix.js.
 *
 * Source: Rashpetco Risk Assessment Proformas (controlled copies), 2026-10,
 * plus RAs exported from the app ("Project > Export RA to General Library").
 * Arabic (\`ar\`) is pre-filled (static, no internet needed). Technical / HSE
 * terms that read poorly in Arabic (PPE, PTW, Tool Box Talk, Performing
 * Authority, ATEX, SWL, ESD, ...) are intentionally kept in English.
 */`;

// Re-reads js/globalRisks.js from disk/share (not the copy loaded at page
// start), so RAs other users added since then are kept. Loaded through a
// hidden iframe because a plain fetch() is blocked on file:// pages.
function loadLatestLibrary(timeoutMs = 5000) {
  return new Promise((resolve) => {
    const frame = document.createElement('iframe');
    frame.style.display = 'none';
    document.body.appendChild(frame);
    let finished = false;
    const finish = (lib) => {
      if (finished) return;
      finished = true;
      frame.remove();
      resolve(lib);
    };
    const win = frame.contentWindow;
    win.__libDone = () => {
      let lib = null;
      try { lib = win.eval('typeof GLOBAL_RA_LIBRARY !== "undefined" ? JSON.parse(JSON.stringify(GLOBAL_RA_LIBRARY)) : null'); } catch (e) { lib = null; }
      finish(Array.isArray(lib) ? lib : null);
    };
    const doc = win.document;
    doc.open();
    doc.write(`<base href="${location.href}"><script src="${LIB_FILE_PATH}?t=${Date.now()}" onload="__libDone()" onerror="__libDone()"><\/script>`);
    doc.close();
    setTimeout(() => finish(null), timeoutMs);
  });
}

function libItemFromRiskItem(it) {
  const bi = (v) => ({ en: String(v?.en || '').trim(), ar: String(v?.ar || '').trim() });
  return {
    hazard: bi(it.hazard),
    effect: bi(it.effect),
    severityBefore: Number(it.severityBefore),
    likelihoodBefore: String(it.likelihoodBefore || '').toUpperCase(),
    ctrl: bi(it.ctrl),
    severityAfter: Number(it.severityAfter),
    likelihoodAfter: String(it.likelihoodAfter || '').toUpperCase(),
  };
}

function serializeLibrary(lib) {
  const q = (v) => JSON.stringify(String(v ?? ''));
  const bi = (v) => `{ en: ${q(v?.en)}, ar: ${q(v?.ar)} }`;
  const out = [LIB_FILE_HEADER, '', 'const GLOBAL_RA_LIBRARY = ['];
  lib.forEach((cat) => {
    out.push('  {');
    out.push(`    category: ${bi(cat.category)},`);
    out.push('    items: [');
    (cat.items || []).forEach((it) => {
      out.push('      {');
      out.push(`        hazard: ${bi(it.hazard)},`);
      out.push(`        effect: ${bi(it.effect)},`);
      out.push(`        severityBefore: ${Number(it.severityBefore)}, likelihoodBefore: ${q(it.likelihoodBefore)},`);
      out.push(`        ctrl: ${bi(it.ctrl)},`);
      out.push(`        severityAfter: ${Number(it.severityAfter)}, likelihoodAfter: ${q(it.likelihoodAfter)},`);
      out.push('      },');
    });
    out.push('    ],');
    out.push('  },');
  });
  out.push('];', '');
  return out.join('\r\n');
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    const ta = $('#lib-export-output');
    ta.focus();
    ta.select();
    try { return document.execCommand('copy'); } catch (e2) { return false; }
  }
}

// Absolute path of js/globalRisks.js, from the page's own URL. On Windows
// this is a backslash path (what File Explorer's address bar needs):
//   file://server/share/x/js/globalRisks.js -> \\server\share\x\js\globalRisks.js
//   file:///C:/x/js/globalRisks.js          -> C:\x\js\globalRisks.js
// On any other OS (Linux/Mac - e.g. while developing this app itself) it's
// left as a normal forward-slash path, since backslashes aren't valid there.
function isWindows() {
  return /Windows/i.test(navigator.userAgent);
}

function libraryFilePath() {
  const url = new URL(LIB_FILE_PATH, location.href);
  const path = decodeURIComponent(url.pathname);
  if (url.protocol !== 'file:') return url.href;
  if (!isWindows()) return url.host ? `//${url.host}${path}` : path;
  if (url.host) return `\\\\${url.host}${path.replace(/\//g, '\\')}`;
  return path.replace(/^\//, '').replace(/\//g, '\\');
}

function wireLibraryExport() {
  const dialog = $('#lib-export-dialog');
  const showStep = (n) => {
    $('#lib-export-step1').hidden = n !== 1;
    $('#lib-export-step2').hidden = n !== 2;
  };

  $('#btn-export-lib').addEventListener('click', () => {
    const items = Store.project.items;
    if (!items.length) { toast('Add at least one risk item before exporting to the library.'); return; }
    $('#lib-export-name-en').value = Store.project.title?.en || '';
    $('#lib-export-count').textContent = `${items.length} risk item(s) will be included.`;
    showStep(1);
    dialog.showModal();
    $('#lib-export-name-en').focus();
  });

  $('#btn-lib-export-cancel').addEventListener('click', () => dialog.close());
  $('#btn-lib-export-close').addEventListener('click', () => dialog.close());

  $('#btn-lib-export-go').addEventListener('click', async () => {
    const nameEn = $('#lib-export-name-en').value.trim();
    if (!nameEn) { toast('RA name (English) is required.'); return; }

    const goBtn = $('#btn-lib-export-go');
    goBtn.disabled = true;
    goBtn.textContent = 'Reading library…';
    let lib = await loadLatestLibrary();
    goBtn.disabled = false;
    goBtn.textContent = 'Generate';

    let source = 'latest library file';
    if (!lib) {
      lib = JSON.parse(JSON.stringify(GLOBAL_RA_LIBRARY));
      source = 'library loaded at app start (could not re-read the file)';
    }

    const newCat = {
      category: { en: nameEn, ar: '' },
      items: Store.project.items.map(libItemFromRiskItem),
    };

    const norm = (s) => String(s || '').trim().toLowerCase();
    const existingIdx = lib.findIndex((c) => norm(c.category?.en) === norm(nameEn));
    let action = 'Added';
    if (existingIdx >= 0) {
      if (!confirm(`An RA named "${nameEn}" already exists in the library.\nReplace it with the current items?`)) return;
      lib[existingIdx] = newCat;
      action = 'Replaced';
    } else {
      lib.push(newCat);
    }

    // Update the in-app library too, so it shows in "Add from General RA
    // Library" right away (until the page is reloaded from the old file).
    GLOBAL_RA_LIBRARY.length = 0;
    GLOBAL_RA_LIBRARY.push(...JSON.parse(JSON.stringify(lib)));

    const text = serializeLibrary(lib);
    $('#lib-export-output').value = text;
    $('#lib-export-path').textContent = libraryFilePath();
    $('#lib-export-instructions').textContent = isWindows()
      ? 'Open the library file below in Notepad (File > Open, paste the path), select all its content (Ctrl+A), paste the copied text over it (Ctrl+V) and save (Ctrl+S). Don\'t double-click the .js file in File Explorer - Windows tries to run it.'
      : 'Open the library file below in a text editor (paste the path to locate it), select all its content, paste the copied text over it and save.';
    showStep(2);
    const copied = await copyText(text);
    $('#lib-export-status').textContent =
      `${action} "${nameEn}" (${newCat.items.length} items) - based on the ${source}. ${lib.length} RA(s) in total.`
      + (copied ? ' Copied to clipboard.' : ' Click "Copy to Clipboard" to copy.');
    if (copied) toast('Library file content copied to clipboard.');
  });

  $('#btn-lib-export-copy').addEventListener('click', async () => {
    const ok = await copyText($('#lib-export-output').value);
    toast(ok ? 'Copied to clipboard.' : 'Copy failed - select the text and press Ctrl+C.');
  });

  $('#btn-lib-export-copy-path').addEventListener('click', async () => {
    const path = $('#lib-export-path').textContent;
    let ok = false;
    try { await navigator.clipboard.writeText(path); ok = true; } catch (e) { ok = false; }
    toast(ok ? 'Path copied - paste it in File Explorer\'s address bar.' : 'Copy failed - select the path and press Ctrl+C.');
  });
}

/* ---------------- export ---------------- */

function wireExport() {
  const openLangDialog = (kind) => {
    pendingExportKind = kind;
    if (!Store.project.items.length) {
      toast(kind === 'print' ? 'Add at least one risk item before printing.' : 'Add at least one risk item before exporting.');
      return;
    }
    const titles = { pdf: 'Export as PDF', word: 'Export as Word', print: 'Print' };
    $('#export-lang-title').textContent = titles[kind];
    $('#btn-export-lang-go').textContent = kind === 'print' ? 'Print' : 'Export';
    $('#export-lang-dialog').showModal();
  };

  $all('#export-menu button').forEach((btn) => {
    btn.addEventListener('click', () => {
      $('#export-menu').classList.remove('open');
      openLangDialog(btn.dataset.export);
    });
  });

  $('#btn-print').addEventListener('click', () => openLangDialog('print'));

  $('#btn-export-lang-cancel').addEventListener('click', () => $('#export-lang-dialog').close());

  $('#btn-export-lang-go').addEventListener('click', () => {
    const lang = $('input[name="export-lang"]:checked').value;
    $('#export-lang-dialog').close();
    runExportAction(pendingExportKind, lang);
  });

  // Ctrl+P (Cmd+P on Mac) prints directly with "Both" as the language,
  // skipping the language dialog - default chosen per explicit request,
  // revisit if a different default language is wanted later.
  document.addEventListener('keydown', (e) => {
    const isPrintShortcut = (e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'p';
    if (!isPrintShortcut) return;
    e.preventDefault();
    if (!Store.project.items.length) {
      toast('Add at least one risk item before printing.');
      return;
    }
    runExportAction('print', 'both');
  });
}

async function runExportAction(kind, lang) {
  toast('Generating file…', 6000);
  try {
    if (kind === 'pdf') {
      await exportProjectToPdf(Store.project, lang);
    } else if (kind === 'print') {
      await printProjectPdf(Store.project, lang);
    } else if (kind === 'word') {
      await exportProjectToWord(Store.project, lang);
    } else {
      throw new Error(`Unknown action: ${kind}`);
    }
    toast(kind === 'print' ? 'Sent to print.' : 'Export complete.');
  } catch (err) {
    console.error(err);
    toast(`${kind === 'print' ? 'Print' : 'Export'} failed: ${err.message}`, 5000);
  }
}

/* ---------------- project save/load/clear ---------------- */

function wireProjectMenu() {
  $('#btn-save-json').addEventListener('click', () => {
    const blob = new Blob([Store.exportJson()], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `risk-assessment-${formatDDMMYYYY(Store.project.date).replace(/\//g, '-') || 'project'}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });

  $('#btn-load-json').addEventListener('click', () => $('#file-load-json').click());
  $('#file-load-json').addEventListener('change', (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        Store.importJson(reader.result);
        fillMetaPanel();
        renderItemsTable();
        toast('Project loaded.');
      } catch (err) {
        alert(`Could not load file: ${err.message}`);
      }
    };
    reader.readAsText(file);
  });

  $('#btn-reset').addEventListener('click', () => {
    if (confirm('Reset the whole project (title, meta and all risk items)? This cannot be undone.')) {
      Store.clearAll();
      fillMetaPanel();
      renderItemsTable();
    }
  });
}

/* ---------------- dropdown menus ---------------- */

function wireDropdowns() {
  const dropdowns = [
    { btn: '#btn-export', menu: '#export-menu' },
    { btn: '#btn-project', menu: '#project-menu' },
  ];
  dropdowns.forEach(({ btn, menu }) => {
    $(btn).addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = $(menu).classList.contains('open');
      $all('.dropdown-menu').forEach((m) => m.classList.remove('open'));
      if (!isOpen) $(menu).classList.add('open');
    });
  });
  document.addEventListener('click', () => $all('.dropdown-menu').forEach((m) => m.classList.remove('open')));
}

/* ---------------- init ---------------- */

document.addEventListener('DOMContentLoaded', () => {
  // Each step runs on its own: if one fails (e.g. index.html and app.js are
  // from different versions, so an element is missing), the rest still runs
  // instead of leaving the whole app dead.
  const steps = [
    ['Store.load', () => Store.load()],
    ['header logos', () => {
      $('#header-logo-left').src = LOGO_RASHPETCO_DATA_URL;
      $('#header-logo-right').src = LOGO_BURULLUS_DATA_URL;
    }],
    ['fillMetaPanel', fillMetaPanel],
    ['wireMetaPanel', wireMetaPanel],
    ['wireItemDialog', wireItemDialog],
    ['wireItemsReorder', wireItemsReorder],
    ['wireArabicPreviewToggle', wireArabicPreviewToggle],
    ['wireLibraryDialog', wireLibraryDialog],
    ['wireExcelImport', wireExcelImport],
    ['wireExport', wireExport],
    ['wireTranslateAll', wireTranslateAll],
    ['wireProjectMenu', wireProjectMenu],
    ['wireLibraryExport', wireLibraryExport],
    ['wireDropdowns', wireDropdowns],
    ['renderItemsTable', renderItemsTable],
  ];
  const failed = [];
  steps.forEach(([name, fn]) => {
    try { fn(); } catch (err) { console.error(`[startup] ${name} failed:`, err); failed.push(name); }
  });
  if (failed.length) {
    toast(`Some features failed to load (${failed.join(', ')}). index.html and js/app.js are probably from different versions - replace both. Details: F12 > Console.`, 12000);
  }
});