/* Excel import/template using the vendored SheetJS (XLSX) library. */

const EXCEL_COLUMNS = [
  { key: 'hazard_en', header: 'Hazard (EN)', required: true },
  { key: 'hazard_ar', header: 'Hazard (AR)', required: false },
  { key: 'effect_en', header: 'Effect (EN)', required: true },
  { key: 'effect_ar', header: 'Effect (AR)', required: false },
  { key: 'severity_before', header: 'Severity Before (1-5)', required: true },
  { key: 'likelihood_before', header: 'Likelihood Before (A-E)', required: true },
  { key: 'ctrl_en', header: 'Control (EN)', required: false },
  { key: 'ctrl_ar', header: 'Control (AR)', required: false },
  { key: 'severity_after', header: 'Severity After (1-5)', required: true },
  { key: 'likelihood_after', header: 'Likelihood After (A-E)', required: true },
];

function normalizeHeader(h) {
  return String(h || '').trim().toLowerCase().replace(/\s+/g, ' ');
}

function downloadExcelTemplate() {
  const headers = EXCEL_COLUMNS.map((c) => c.header);
  const example = [
    'Fire from sparks', 'حريق من الشرر',
    'Burns, asset damage', 'حروق، أضرار بالممتلكات',
    4, 'C',
    'Hot work permit, fire watch, gas testing, remove combustibles', 'تصريح عمل ساخن، مراقب حريق، اختبار الغازات، إزالة المواد القابلة للاشتعال',
    4, 'A',
  ];
  const ws = XLSX.utils.aoa_to_sheet([headers, example]);
  ws['!cols'] = headers.map(() => ({ wch: 24 }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Risk Items');
  XLSX.writeFile(wb, 'risk_assessment_import_template.xlsx');
}

function buildHeaderIndex(headerRow) {
  const normalizedToKey = {};
  EXCEL_COLUMNS.forEach((c) => { normalizedToKey[normalizeHeader(c.header)] = c.key; });
  const index = {};
  headerRow.forEach((cell, i) => {
    const key = normalizedToKey[normalizeHeader(cell)];
    if (key) index[key] = i;
  });
  return index;
}

function parseRiskExcelFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read the file.'));
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const wb = XLSX.read(data, { type: 'array' });
        const sheet = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '', raw: true });
        if (!rows.length) throw new Error('The sheet appears to be empty.');

        const headerIndex = buildHeaderIndex(rows[0]);
        const missing = EXCEL_COLUMNS.filter((c) => c.required && !(c.key in headerIndex));
        if (missing.length) {
          throw new Error(`Missing required column(s): ${missing.map((c) => c.header).join(', ')}`);
        }

        const items = [];
        const errors = [];

        for (let r = 1; r < rows.length; r += 1) {
          const row = rows[r];
          if (!row || row.every((c) => String(c).trim() === '')) continue;

          const get = (key) => {
            const i = headerIndex[key];
            return i === undefined ? '' : String(row[i] ?? '').trim();
          };

          const severityBefore = Number(get('severity_before'));
          const severityAfter = Number(get('severity_after'));
          const likelihoodBefore = get('likelihood_before').toUpperCase();
          const likelihoodAfter = get('likelihood_after').toUpperCase();

          const rowErrors = [];
          if (!get('hazard_en')) rowErrors.push('Hazard (EN) is required');
          if (!get('effect_en')) rowErrors.push('Effect (EN) is required');
          if (!(severityBefore >= 1 && severityBefore <= 5)) rowErrors.push('Severity Before must be 1-5');
          if (!(severityAfter >= 1 && severityAfter <= 5)) rowErrors.push('Severity After must be 1-5');
          if (!/^[A-E]$/.test(likelihoodBefore)) rowErrors.push('Likelihood Before must be A-E');
          if (!/^[A-E]$/.test(likelihoodAfter)) rowErrors.push('Likelihood After must be A-E');

          if (rowErrors.length) {
            errors.push(`Row ${r + 1}: ${rowErrors.join('; ')}`);
            continue;
          }

          items.push({
            id: (crypto.randomUUID ? crypto.randomUUID() : `id_${Date.now()}_${r}`),
            hazard: { en: get('hazard_en'), ar: get('hazard_ar') },
            effect: { en: get('effect_en'), ar: get('effect_ar') },
            severityBefore,
            likelihoodBefore,
            ctrl: { en: get('ctrl_en'), ar: get('ctrl_ar') },
            severityAfter,
            likelihoodAfter,
          });
        }

        resolve({ items, errors });
      } catch (err) {
        reject(err);
      }
    };
    reader.readAsArrayBuffer(file);
  });
}
