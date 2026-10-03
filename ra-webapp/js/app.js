/* Main UI wiring. Plain DOM, no framework - this is a small, local tool. */

let editingItemId = null;
let pendingExportKind = null; // 'pdf' | 'word' | 'print'

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
  $('#meta-title-ar').value = p.title.ar || '';
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
  bind('#meta-title-ar', ['title', 'ar']);
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

  $('#btn-meta-translate').addEventListener('click', (e) => {
    runTranslateButton(e.target, [
      ['#meta-title-en', '#meta-title-ar'],
    ]);
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
    const evaluation = evaluateRisk(item.severityAfter, item.likelihoodAfter);

    const biCell = (field) => {
      const en = field?.en ? `<div class="cell-en">${escapeHtml(field.en)}</div>` : '';
      const ar = field?.ar ? `<div class="cell-ar" dir="rtl">${escapeHtml(field.ar)}</div>` : '';
      return en + ar || '&nbsp;';
    };
    const sub = (v) => `<td class="col-sub">${v}</td>`;
    const evalBadge = (risk) => (risk ? `<span class="badge" style="background:${risk.bg};color:${risk.color}">${risk.en}</span>` : '');

    tr.innerHTML = `
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
      <td class="col-eval">${evalBadge(evaluation)}</td>
      <td class="col-actions">
        <button class="row-actions-btn" data-action="edit" data-id="${item.id}">Edit</button>
        <button class="row-actions-btn danger" data-action="delete" data-id="${item.id}">Delete</button>
      </td>`;
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

/* ---------------- library dialog ---------------- */

function renderLibraryList(filterText = '') {
  // A generic RA is a complete named assessment (e.g. "Use of Hand Tools"),
  // not a pick-list of individual hazards - so this only ever shows RA
  // titles, one row each. Picking one adds every item under it.
  const host = $('#library-list');
  host.innerHTML = '';
  const ft = filterText.trim().toLowerCase();

  GLOBAL_RA_LIBRARY.forEach((cat, catIdx) => {
    if (ft) {
      const haystack = [
        cat.category.en, cat.category.ar,
        ...cat.items.flatMap((item) => [item.hazard.en, item.hazard.ar, item.effect.en, item.effect.ar]),
      ].join(' ').toLowerCase();
      if (!haystack.includes(ft)) return;
    }

    const row = document.createElement('label');
    row.className = 'library-item';
    row.innerHTML = `
      <input type="checkbox" data-cat="${catIdx}">
      <span class="item-text">
        <span class="en"><strong>${escapeHtml(cat.category.en)}</strong> (${cat.items.length} item${cat.items.length === 1 ? '' : 's'})</span>
        <span class="ar" dir="rtl">${escapeHtml(cat.category.ar)}</span>
      </span>`;
    host.appendChild(row);
  });

  if (!host.children.length) {
    host.innerHTML = '<p style="padding:14px;color:var(--muted)">No matches.</p>';
  }
}

function wireLibraryDialog() {
  $('#btn-add-library').addEventListener('click', () => {
    renderLibraryList('');
    $('#library-search').value = '';
    $('#library-dialog').showModal();
  });
  $('#btn-library-close').addEventListener('click', () => $('#library-dialog').close());
  $('#library-search').addEventListener('input', (e) => renderLibraryList(e.target.value));

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
  btn.addEventListener('click', async () => {
    const items = Store.project.items;
    if (!items.length) { toast('No risk items to translate.'); return; }

    const hasEn = (it, f) => (it[f]?.en || '').trim();
    const hasAr = (it, f) => (it[f]?.ar || '').trim();

    // Default: only fill fields whose Arabic is empty. If everything is
    // already translated, offer to re-translate (overwrite) all of it.
    let jobs = [];
    items.forEach((it) => TRANSLATE_FIELDS.forEach((f) => {
      if (hasEn(it, f) && !hasAr(it, f)) jobs.push([it.id, f]);
    }));
    if (!jobs.length) {
      if (!confirm('All risk items already have Arabic text.\nRe-translate everything and overwrite the existing Arabic?')) return;
      items.forEach((it) => TRANSLATE_FIELDS.forEach((f) => {
        if (hasEn(it, f)) jobs.push([it.id, f]);
      }));
    }
    if (!jobs.length) { toast('Nothing to translate - no English text found.'); return; }

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

  $('#btn-export-lang-go').addEventListener('click', async () => {
    const lang = $('input[name="export-lang"]:checked').value;
    $('#export-lang-dialog').close();
    toast('Generating file…', 6000);
    try {
      if (pendingExportKind === 'pdf') {
        await exportProjectToPdf(Store.project, lang);
      } else if (pendingExportKind === 'print') {
        await printProjectPdf(Store.project, lang);
      } else if (pendingExportKind === 'word') {
        await exportProjectToWord(Store.project, lang);
      } else {
        throw new Error(`Unknown action: ${pendingExportKind}`);
      }
      toast(pendingExportKind === 'print' ? 'Sent to print.' : 'Export complete.');
    } catch (err) {
      console.error(err);
      toast(`${pendingExportKind === 'print' ? 'Print' : 'Export'} failed: ${err.message}`, 5000);
    }
  });
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
  Store.load();
  fillMetaPanel();
  wireMetaPanel();
  wireItemDialog();
  wireLibraryDialog();
  wireExcelImport();
  wireExport();
  wireTranslateAll();
  wireProjectMenu();
  wireDropdowns();
  renderItemsTable();
});