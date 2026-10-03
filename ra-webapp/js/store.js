/* Application state + localStorage persistence. No server involved. */

const STORAGE_KEY = 'ra_webapp_project_v1';

// Dates are stored internally as ISO "yyyy-mm-dd" (what <input type="date">
// needs), but always DISPLAYED/EXPORTED as dd/mm/yyyy via this formatter.
function formatDDMMYYYY(isoDate) {
  const parts = String(isoDate || '').split('-');
  if (parts.length !== 3) return isoDate || '';
  const [y, m, d] = parts;
  return `${d}/${m}/${y}`;
}

function blankProject() {
  return {
    title: { en: '', ar: '' },
    location: { en: '' }, // Arabic location is not used - removed per explicit instruction
    ptwNumber: '',
    date: new Date().toISOString().slice(0, 10),
    items: [],
  };
}

// A risk item is considered a duplicate of another if its Hazard+Effect+
// Control (English text) match, regardless of severity/likelihood/Arabic.
function riskItemKey(item) {
  const norm = (s) => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase();
  return [norm(item?.hazard?.en), norm(item?.effect?.en), norm(item?.ctrl?.en)].join('|');
}

function blankItem() {
  return {
    id: (crypto.randomUUID ? crypto.randomUUID() : `id_${Date.now()}_${Math.random().toString(16).slice(2)}`),
    hazard: { en: '', ar: '' },
    effect: { en: '', ar: '' },
    severityBefore: 3,
    likelihoodBefore: 'C',
    ctrl: { en: '', ar: '' },
    severityAfter: 2,
    likelihoodAfter: 'B',
  };
}

const Store = {
  project: null,

  load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      this.project = raw ? JSON.parse(raw) : blankProject();
    } catch (e) {
      console.warn('Failed to load saved project, starting fresh.', e);
      this.project = blankProject();
    }
    return this.project;
  },

  save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.project));
    } catch (e) {
      console.warn('Failed to persist project to localStorage.', e);
    }
  },

  // Both return the items actually added (skipping any that duplicate an
  // existing item, or each other, by Hazard+Effect+Control) so callers can
  // report how many were skipped.
  addItem(item) {
    return this.addItems([item]);
  },

  addItems(items) {
    const seenKeys = new Set(this.project.items.map(riskItemKey));
    const added = [];
    items.forEach((item) => {
      const key = riskItemKey(item);
      if (seenKeys.has(key)) return;
      seenKeys.add(key);
      added.push(item);
    });
    this.project.items.push(...added);
    this.save();
    return added;
  },

  updateItem(id, patch) {
    const idx = this.project.items.findIndex((i) => i.id === id);
    if (idx === -1) return;
    this.project.items[idx] = { ...this.project.items[idx], ...patch };
    this.save();
  },

  deleteItem(id) {
    this.project.items = this.project.items.filter((i) => i.id !== id);
    this.save();
  },

  clearAll() {
    this.project = blankProject();
    this.save();
  },

  updateMeta(patch) {
    Object.assign(this.project, patch);
    this.save();
  },

  exportJson() {
    return JSON.stringify(this.project, null, 2);
  },

  importJson(jsonText) {
    const parsed = JSON.parse(jsonText);
    if (!parsed || !Array.isArray(parsed.items)) {
      throw new Error('Invalid project file: missing items array.');
    }
    this.project = parsed;
    this.save();
  },
};
