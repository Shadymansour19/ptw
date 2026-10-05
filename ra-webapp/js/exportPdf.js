/* PDF export: renders the report as real HTML (so Arabic shaping/RTL is
 * handled by the browser itself), rasterizes it page-by-page with
 * html2canvas, and assembles the pages into a PDF with jsPDF. Row content is
 * never cut mid-row across a page break.
 *
 * Visual style (page size/margins, logos, fonts, column widths, borders,
 * diagonal watermark) deliberately mirrors the PTW Qt app's own
 * `riskAssessmentReport` (ReportLab) output, so printed assessments from
 * both tools look the same. */

const MM_TO_PX = 1500 / 297; // render width (1500px) represents A4 landscape's 297mm
const PT_TO_PX = 1500 / 841.89; // A4 landscape width is 841.89pt
const PDF_PAGE_W_PX = 1500;
const PDF_PAGE_H_PX = Math.round(PDF_PAGE_W_PX * (210 / 297)); // A4 landscape ratio
const PDF_SCALE = 2;
const MARGIN_LR_PX = Math.round(17.78 * MM_TO_PX); // 0.7in
const MARGIN_BOTTOM_PX = Math.round(16 * MM_TO_PX); // enlarged to keep the (bigger, higher) page footer clear of the table
const CONTENT_TOP_PADDING_PX = 28; // .rpt-content-layer's own top padding (style.css)
const LOGO_IMG_PX = Math.round(35 * 0.7 * MM_TO_PX); // 24.5mm - logo image scaled 0.7x
const LOGO_CELL_PX = Math.round(42 * 0.8 * MM_TO_PX); // 33.6mm - logo column scaled 0.8x

// PDF-only column weights (Word has its own, independent WORD_COL_WEIGHTS in
// exportWord.js - the two exports are tuned separately, not shared):
// No | Hazard | Effect | S | L | Risk | Control | S | L | Risk | Evaluation
const PDF_COL_WEIGHTS = [7, 26, 30, 5, 5, 8, 66, 5, 5, 8, 16];
const PDF_COL_WEIGHT_SUM = PDF_COL_WEIGHTS.reduce((a, b) => a + b, 0);

// Document-control strip shown above the logos/title box on every export.
// Fixed, project-independent boilerplate (not per-RA data).
const DOC_CONTROL_FORM_CODE = 'FO-HSE-RM-01';
const DOC_CONTROL_ISSUE = '3';
const DOC_CONTROL_REV = '0';
const DOC_CONTROL_REV_DATE = '29 June 2025';

// Footer shown on every page. Update this whenever the app/library/matrix
// content changes - it's the only thing to edit, the rest is automatic.
const LAST_UPDATED_DATE = 'FEB 2026';

function sanitizeFilename(text) {
  return String(text || '').trim().replace(/[\\/:*?"<>|]/g, '-').replace(/\s+/g, ' ').slice(0, 120);
}

function metaValueOrBlank(value) {
  return value ? escapeHtml(value) : '<span class="rpt-meta-blank"></span>';
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function bilingualCellHtml(field, lang) {
  const en = escapeHtml(field?.en);
  const ar = escapeHtml(field?.ar);
  if (lang === 'en') return `<div class="rpt-en">${en}</div>`;
  if (lang === 'ar') return `<div class="rpt-ar" dir="rtl">${ar}</div>`;
  const parts = [];
  if (en) parts.push(`<div class="rpt-en">${en}</div>`);
  if (ar) parts.push(`<div class="rpt-ar" dir="rtl">${ar}</div>`);
  return parts.join('');
}

function plainCodeHtml(v) {
  return escapeHtml(String(v));
}

function riskEvaluationHtml(severity, likelihood, lang) {
  // Plain text, no color, result only (Low/Medium/...) - matches the Qt
  // report's own plain Evaluation column. The code itself is already shown
  // in the Controlled Analysis "Risk" sub-column, so it isn't repeated here.
  const risk = evaluateRisk(severity, likelihood);
  if (!risk) return '';
  const labelParts = [];
  if (lang === 'en' || lang === 'both') labelParts.push(escapeHtml(risk.en));
  if (lang === 'ar' || lang === 'both') labelParts.push(escapeHtml(risk.ar));
  return labelParts.join(' / ');
}

function headerLabels() {
  // Table column headers are always English only - user instruction, no
  // need to translate "Hazard"/"Effect"/etc.
  const H = { no: 'No.', hazard: 'Hazard', effect: 'Effect', free: 'Risk Analysis (No controls)', ctrl: 'Control Measure', controlled: 'Risk Analysis with control', eval: 'Evaluation', s: 'S', l: 'L', risk: 'Risk' };
  return (key) => H[key];
}

function buildColgroupHtml() {
  return `<colgroup>${PDF_COL_WEIGHTS.map((w) => `<col style="width:${((w / PDF_COL_WEIGHT_SUM) * 100).toFixed(4)}%">`).join('')}</colgroup>`;
}

function buildTableHeadHtml() {
  const L = headerLabels();
  return `<thead>
    <tr>
      <th class="col-no" rowspan="2">${L('no')}</th>
      <th rowspan="2">${L('hazard')}</th>
      <th rowspan="2">${L('effect')}</th>
      <th colspan="3">${L('free')}</th>
      <th rowspan="2">${L('ctrl')}</th>
      <th colspan="3">${L('controlled')}</th>
      <th rowspan="2">${L('eval')}</th>
    </tr>
    <tr>
      <th class="col-sub">${L('s')}</th>
      <th class="col-sub">${L('l')}</th>
      <th class="col-sub">${L('risk')}</th>
      <th class="col-sub">${L('s')}</th>
      <th class="col-sub">${L('l')}</th>
      <th class="col-sub">${L('risk')}</th>
    </tr>
  </thead>`;
}

function renderRowHtml(item, index, lang) {
  const freeCode = `${item.severityBefore}${item.likelihoodBefore}`;
  const controlledCode = `${item.severityAfter}${item.likelihoodAfter}`;
  return `<tr>
    <td class="col-no">${index + 1}</td>
    <td>${bilingualCellHtml(item.hazard, lang)}</td>
    <td>${bilingualCellHtml(item.effect, lang)}</td>
    <td class="col-sub">${plainCodeHtml(item.severityBefore)}</td>
    <td class="col-sub">${plainCodeHtml(item.likelihoodBefore)}</td>
    <td class="col-sub">${plainCodeHtml(freeCode)}</td>
    <td>${bilingualCellHtml(item.ctrl, lang)}</td>
    <td class="col-sub">${plainCodeHtml(item.severityAfter)}</td>
    <td class="col-sub">${plainCodeHtml(item.likelihoodAfter)}</td>
    <td class="col-sub">${plainCodeHtml(controlledCode)}</td>
    <td class="col-eval">${riskEvaluationHtml(item.severityAfter, item.likelihoodAfter, lang)}</td>
  </tr>`;
}


function buildDocControlStripHtml() {
  // Full-width black bar: Form Code left, Issue/Rev centered, Rev Date right.
  return `<div class="rpt-doc-control">
    <span class="rpt-dc-left">Form Code: ${escapeHtml(DOC_CONTROL_FORM_CODE)}</span>
    <span class="rpt-dc-mid">Issue# (${escapeHtml(DOC_CONTROL_ISSUE)})&nbsp;&nbsp;&nbsp;&nbsp;Rev. (${escapeHtml(DOC_CONTROL_REV)})</span>
    <span class="rpt-dc-right">Rev Date: ${escapeHtml(DOC_CONTROL_REV_DATE)}</span>
  </div>`;
}

function buildHeaderBoxHtml(project) {
  // Header is always English only, regardless of export language, and never
  // carries a watermark - matches explicit instruction, a deliberate
  // deviation from the Qt report's own header (which has no PTW#/Location
  // line at all, only a title).
  return `
    <div class="rpt-header-group">
      ${buildDocControlStripHtml()}
      <table class="rpt-header-box">
        <tr>
          <td class="rpt-logo-cell" style="width:${LOGO_CELL_PX}px">
            <img src="${LOGO_RASHPETCO_DATA_URL}" alt="" style="width:${LOGO_IMG_PX}px;height:${LOGO_IMG_PX}px">
          </td>
          <td class="rpt-title-cell">
            <div class="rpt-ra-title">HSE Risk Assessment</div>
            <div class="rpt-ra-title">Task / Activity: ${escapeHtml(project.title?.en) || '&nbsp;'}</div>
            <div class="rpt-ra-meta">
              <span class="rpt-meta-left">Location: ${metaValueOrBlank(project.location?.en)}</span>
              <span class="rpt-meta-mid">Date: ${escapeHtml(formatDDMMYYYY(project.date))}</span>
              <span class="rpt-meta-right">PTW#: ${metaValueOrBlank(project.ptwNumber)}</span>
            </div>
          </td>
          <td class="rpt-logo-cell" style="width:${LOGO_CELL_PX}px">
            <img src="${LOGO_BURULLUS_DATA_URL}" alt="" style="width:${LOGO_IMG_PX}px;height:${LOGO_IMG_PX}px">
          </td>
        </tr>
      </table>
    </div>`;
}

const SIGNATURE_SPACE_PX = Math.round(16 * MM_TO_PX); // ~16mm blank space for handwritten signatures

function buildSignatureFooterHtml() {
  const block = (label) => `
    <div class="rpt-sig-block">
      <div class="rpt-sig-label">${label}</div>
      <div class="rpt-sig-space" style="height:${SIGNATURE_SPACE_PX}px"></div>
      <div class="rpt-sig-line"></div>
    </div>`;
  return `
    <div class="rpt-signatures">
      ${block('Issuing Authority')}
      ${block('Performing Authority')}
      ${block('HSE Engineer')}
    </div>`;
}

async function waitForFontsReady() {
  try { if (document.fonts && document.fonts.ready) await document.fonts.ready; } catch (e) { /* ignore */ }
}

async function waitForImages(root) {
  const imgs = Array.from(root.querySelectorAll('img'));
  await Promise.all(imgs.map((img) => (img.complete ? Promise.resolve() : new Promise((res) => {
    img.onload = res;
    img.onerror = res;
  }))));
}

function makeOffscreenHost() {
  const host = document.createElement('div');
  host.style.position = 'fixed';
  host.style.top = '0';
  host.style.left = '-20000px';
  host.style.zIndex = '-1';
  document.body.appendChild(host);
  return host;
}

function buildPageFooterHtml(pageNumber) {
  return `
    <div class="rpt-page-footer">
      <span>UPDATED ${escapeHtml(LAST_UPDATED_DATE)}</span>
      <span>${pageNumber} | Page</span>
    </div>`;
}

function pageContentHtml(project, lang, rowsHtml, includeSignatures, pageNumber) {
  return `
    <div class="rpt-watermark">CONTROLLED COPY</div>
    <div class="rpt-content-layer">
      ${buildHeaderBoxHtml(project)}
      <div class="rpt-table-wrapper">
        <table class="rpt-table" dir="${lang === 'ar' ? 'rtl' : 'ltr'}">
          ${buildColgroupHtml()}
          ${buildTableHeadHtml()}
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
      ${includeSignatures ? buildSignatureFooterHtml() : ''}
    </div>
    ${buildPageFooterHtml(pageNumber)}`;
}

async function renderProjectPageImages(project, lang) {
  // Renders every report page (same layout/pagination as the PDF) to a JPEG
  // data URL. Shared by the PDF export and by Print.
  await waitForFontsReady();
  const host = makeOffscreenHost();

  try {
    // --- measurement pass: render everything once (unpaginated) to measure row/header heights ---
    const measureDiv = document.createElement('div');
    measureDiv.className = 'rpt-page';
    measureDiv.style.width = `${PDF_PAGE_W_PX}px`;
    measureDiv.style.height = 'auto';
    measureDiv.innerHTML = pageContentHtml(project, lang, project.items.map((it, i) => renderRowHtml(it, i, lang)).join(''), true, 1);
    host.appendChild(measureDiv);
    await waitForImages(measureDiv);

    const headerBoxEl = measureDiv.querySelector('.rpt-header-group');
    const theadEl = measureDiv.querySelector('thead');
    const rowEls = Array.from(measureDiv.querySelectorAll('.rpt-table tbody tr'));
    const signaturesEl = measureDiv.querySelector('.rpt-signatures');

    const headerBoxH = headerBoxEl.getBoundingClientRect().height + 18; // .rpt-header-box's own margin-bottom
    const theadH = theadEl.getBoundingClientRect().height;
    const rowHeights = rowEls.map((r) => r.getBoundingClientRect().height);
    const signaturesH = signaturesEl.getBoundingClientRect().height + 40; // + its own margin-top (not included in getBoundingClientRect)
    host.removeChild(measureDiv);

    // --- paginate by accumulating row heights against the page budget ---
    // The logo/title header box AND the table header repeat on every page.
    const usablePageH = PDF_PAGE_H_PX - MARGIN_BOTTOM_PX - headerBoxH - theadH - CONTENT_TOP_PADDING_PX;
    const pages = [];
    let i = 0;
    while (i < rowHeights.length || pages.length === 0) {
      let used = 0;
      const startIdx = i;
      if (i >= rowHeights.length) { pages.push({ startIdx, endIdx: startIdx }); break; }
      while (i < rowHeights.length) {
        const next = used + rowHeights[i];
        if (next > usablePageH && i > startIdx) break;
        used = next;
        i += 1;
      }
      if (i === startIdx) i += 1; // guard: a single row taller than a page still advances
      pages.push({ startIdx, endIdx: i });
    }

    // The signature footer (labels + blank signing space) goes after the
    // table, only on the last page. If it doesn't fit under the last page's
    // rows, move the last row to a fresh page with it, so the signatures
    // never sit on a page with zero items.
    const lastPage = pages[pages.length - 1];
    const lastPageRowsH = rowHeights.slice(lastPage.startIdx, lastPage.endIdx).reduce((a, b) => a + b, 0);
    if (lastPageRowsH + signaturesH > usablePageH) {
      if (lastPage.endIdx - lastPage.startIdx > 1) {
        lastPage.endIdx -= 1;
        pages.push({ startIdx: lastPage.endIdx, endIdx: lastPage.endIdx + 1 });
      }
      // Single row on the last page: moving it wouldn't gain anything (the
      // same row + signatures would land on the new page), so keep them
      // together rather than leave signatures alone on an empty page.
    }

    // --- render + capture each page ---
    const images = [];

    for (let p = 0; p < pages.length; p += 1) {
      const { startIdx, endIdx } = pages[p];
      const pageDiv = document.createElement('div');
      pageDiv.className = 'rpt-page';
      pageDiv.style.width = `${PDF_PAGE_W_PX}px`;
      pageDiv.style.height = `${PDF_PAGE_H_PX}px`;
      const rowsHtml = project.items.slice(startIdx, endIdx).map((it, i2) => renderRowHtml(it, startIdx + i2, lang)).join('');
      const includeSignatures = p === pages.length - 1;
      pageDiv.innerHTML = pageContentHtml(project, lang, rowsHtml, includeSignatures, p + 1);
      host.appendChild(pageDiv);

      // eslint-disable-next-line no-await-in-loop
      await waitForImages(pageDiv);
      // eslint-disable-next-line no-await-in-loop
      const canvas = await html2canvas(pageDiv, { scale: PDF_SCALE, backgroundColor: '#ffffff', useCORS: true });
      host.removeChild(pageDiv);

      images.push(canvas.toDataURL('image/jpeg', 0.95));
    }

    return images;
  } finally {
    document.body.removeChild(host);
  }
}

async function buildProjectPdf(project, lang) {
  const images = await renderProjectPageImages(project, lang);
  const pdf = new window.jspdf.jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  images.forEach((img, p) => {
    if (p > 0) pdf.addPage('a4', 'landscape');
    pdf.addImage(img, 'JPEG', 0, 0, 297, 210);
  });
  return pdf;
}

async function exportProjectToPdf(project, lang) {
  const pdf = await buildProjectPdf(project, lang);
  pdf.save(`${sanitizeFilename(project.title?.en) || 'risk-assessment'}.pdf`);
}

async function printProjectPdf(project, lang) {
  // Prints the exact PDF pages (same rendered images the PDF export uses),
  // but through a hidden HTML iframe instead of a PDF file - so nothing is
  // downloaded and no PDF viewer is involved; the browser's print dialog
  // opens directly. Each image fills one A4-landscape sheet, zero margins.
  const images = await renderProjectPageImages(project, lang);

  const old = document.getElementById('pdf-print-frame');
  if (old) old.remove();
  const frame = document.createElement('iframe');
  frame.id = 'pdf-print-frame';
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden;';
  document.body.appendChild(frame);

  const title = escapeHtml(project.title?.en || 'Risk Assessment');
  const doc = frame.contentDocument;
  doc.open();
  doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>
<style>
  @page { size: A4 landscape; margin: 0; }
  html, body { margin: 0; padding: 0; background: #fff; }
  .sheet { width: 297mm; height: 210mm; overflow: hidden; page-break-after: always; break-after: page; }
  .sheet:last-child { page-break-after: auto; break-after: auto; }
  .sheet img { display: block; width: 297mm; height: 210mm; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
</style></head><body>
${images.map((src) => `<div class="sheet"><img src="${src}" alt=""></div>`).join('')}
</body></html>`);
  doc.close();

  await waitForImages(doc);
  await new Promise((res) => setTimeout(res, 100));

  const win = frame.contentWindow;
  win.addEventListener('afterprint', () => setTimeout(() => frame.remove(), 500));
  win.focus();
  win.print();
}