/* Word (.docx) export using the vendored docx.js library. Word performs its
 * own Arabic shaping, so we only need correct Unicode text plus RTL
 * paragraph/run flags - no rasterization needed here.
 *
 * Layout deliberately mirrors the PDF export (exportPdf.js): A4 landscape,
 * same margins, the black document-control strip, the same logo/title box
 * proportions, the diagonal "CONTROLLED COPY" watermark, rows that never
 * split across pages, and the signature block (labels + blank signing space
 * + line) that always stays with at least the last item row. Everything in
 * the repeating page Header (watermark, strip, logo/title box) appears on
 * every page; the table header row repeats via `tableHeader: true`. */

const TWIPS_PER_MM = 1440 / 25.4;
const PX96_PER_MM = 96 / 25.4; // docx.js ImageRun sizes are in 96-dpi pixels
// PDF render scale: 1500px page width = 297mm. Font sizes below are the PDF's
// CSS px sizes converted to Word half-points, so text reads the same size.
const pdfPxToHalfPt = (px) => Math.round(px * (297 / 1500) * (72 / 25.4) * 2);

// A4 landscape (docx.js swaps width/height itself when orientation is
// LANDSCAPE, so the portrait dimensions are passed in).
const WORD_PAGE_SHORT_TWIPS = 11906;
const WORD_PAGE_LONG_TWIPS = 16838;
const WORD_MARGIN_LR_TWIPS = Math.round(17.78 * TWIPS_PER_MM); // 0.7in, same as PDF
const WORD_MARGIN_TOP_TWIPS = Math.round(6 * TWIPS_PER_MM);
const WORD_MARGIN_BOTTOM_TWIPS = Math.round(16 * TWIPS_PER_MM); // same as PDF's MARGIN_BOTTOM_PX
const WORD_HEADER_DIST_TWIPS = Math.round(6 * TWIPS_PER_MM);
const WORD_FOOTER_DIST_TWIPS = Math.round(9 * TWIPS_PER_MM);
const WORD_USABLE_WIDTH_TWIPS = WORD_PAGE_LONG_TWIPS - WORD_MARGIN_LR_TWIPS * 2;

// No | Hazard | Effect | S | L | Risk | Control | S | L | Risk | Evaluation
const WORD_COL_WEIGHTS = [8, 28, 32, 4, 4, 9, 60, 4, 4, 9, 18];
const WORD_COL_WEIGHT_SUM = WORD_COL_WEIGHTS.reduce((a, b) => a + b, 0);
const WORD_COL_WIDTHS_TWIPS = WORD_COL_WEIGHTS.map((w) => Math.round((w / WORD_COL_WEIGHT_SUM) * WORD_USABLE_WIDTH_TWIPS));

// Logo/title box: same mm sizes as the PDF (logo cell 33.6mm, image 24.5mm).
const WORD_LOGO_CELL_TWIPS = Math.round(42 * 0.8 * TWIPS_PER_MM);
const WORD_LOGO_IMG_PX = Math.round(35 * 0.7 * PX96_PER_MM);
const HEADER_BOX_WIDTHS_TWIPS = [
  WORD_LOGO_CELL_TWIPS,
  WORD_USABLE_WIDTH_TWIPS - WORD_LOGO_CELL_TWIPS * 2,
  WORD_LOGO_CELL_TWIPS,
];

const WORD_SIGNATURE_SPACE_TWIPS = Math.round(16 * TWIPS_PER_MM); // same as PDF's SIGNATURE_SPACE_PX

const FS_STRIP = pdfPxToHalfPt(19);
const FS_TITLE = pdfPxToHalfPt(32);
const FS_META = pdfPxToHalfPt(19);
const FS_BODY = pdfPxToHalfPt(18);
const FS_TH = pdfPxToHalfPt(20);
const FS_SIG = pdfPxToHalfPt(20);
const FS_FOOTER = pdfPxToHalfPt(18);

function sanitizeFilename(text) {
  return String(text || '').trim().replace(/[\\/:*?"<>|]/g, '-').replace(/\s+/g, ' ').slice(0, 120);
}

function dataUrlToUint8Array(dataUrl) {
  const base64 = dataUrl.split(',')[1];
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function wordNoBorders() {
  const { BorderStyle } = window.docx;
  const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  return { top: none, bottom: none, left: none, right: none, insideHorizontal: none, insideVertical: none };
}

function wordBilingualParagraphs(field, lang, { keepNext = false } = {}) {
  // Source text often carries real newlines as its own "bullet per line"
  // formatting - Word doesn't render a literal \n inside one run as a line
  // break, so each line becomes its own Paragraph instead.
  const { Paragraph, TextRun, AlignmentType } = window.docx;
  const paras = [];
  const en = field?.en || '';
  const ar = field?.ar || '';
  const lines = (text) => text.split('\n').map((l) => l.trim()).filter(Boolean);

  if (lang === 'en' || lang === 'both') {
    lines(en).forEach((line) => {
      paras.push(new Paragraph({ keepNext, alignment: AlignmentType.JUSTIFIED, children: [new TextRun({ text: line, font: 'Arial', size: FS_BODY })] }));
    });
  }
  if (lang === 'ar' || lang === 'both') {
    lines(ar).forEach((line) => {
      paras.push(new Paragraph({
        keepNext,
        bidirectional: true,
        alignment: AlignmentType.JUSTIFIED,
        children: [new TextRun({ text: line, font: 'Arial', size: FS_BODY, rightToLeft: true })],
      }));
    });
  }
  if (!paras.length) paras.push(new Paragraph({ keepNext, children: [new TextRun({ text: '' })] }));
  return paras;
}

function wordCenteredParagraph(text, { keepNext = false, bold = false, size = FS_BODY } = {}) {
  const { Paragraph, TextRun, AlignmentType } = window.docx;
  return new Paragraph({ keepNext, alignment: AlignmentType.CENTER, children: [new TextRun({ text: String(text), bold, font: 'Arial', size })] });
}

function wordRiskCellParagraphs(severity, likelihood, lang, { keepNext = false } = {}) {
  // Result only (Low/Medium/...), no code - same as the PDF's Evaluation column.
  const { Paragraph, TextRun, AlignmentType } = window.docx;
  const risk = evaluateRisk(severity, likelihood);
  if (!risk) return [new Paragraph({ keepNext, children: [new TextRun({ text: '' })] })];
  const parts = [];
  if (lang === 'en' || lang === 'both') parts.push(risk.en);
  if (lang === 'ar' || lang === 'both') parts.push(risk.ar);
  return [new Paragraph({
    keepNext,
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: parts.join(' / '), font: 'Arial', size: FS_BODY })],
  })];
}

function wordColWidth(weightIndex) {
  return { size: WORD_COL_WIDTHS_TWIPS[weightIndex], type: window.docx.WidthType.DXA };
}

function wordHeaderLabel(key) {
  // Table column headers are always English only - same as the PDF export.
  const H = { no: 'No.', hazard: 'Hazard', effect: 'Effect', free: 'Free Analysis', ctrl: 'Control Measure', controlled: 'Controlled Analysis', eval: 'Evaluation', s: 'S', l: 'L', risk: 'Risk' };
  return H[key];
}

function wordHeaderCell(key, { colSpan, rowSpan, widthIdx } = {}) {
  const { TableCell, ShadingType, VerticalAlign } = window.docx;
  return new TableCell({
    ...(colSpan ? { columnSpan: colSpan } : {}),
    ...(rowSpan ? { rowSpan } : {}),
    ...(widthIdx !== undefined ? { width: wordColWidth(widthIdx) } : {}),
    verticalAlign: VerticalAlign.CENTER,
    shading: { type: ShadingType.CLEAR, fill: 'CCCCCC' },
    children: [wordCenteredParagraph(wordHeaderLabel(key), { bold: true, size: FS_TH })],
  });
}

function wordHeaderRows() {
  const { TableRow } = window.docx;
  const row1 = new TableRow({
    tableHeader: true,
    cantSplit: true,
    children: [
      wordHeaderCell('no', { rowSpan: 2, widthIdx: 0 }),
      wordHeaderCell('hazard', { rowSpan: 2, widthIdx: 1 }),
      wordHeaderCell('effect', { rowSpan: 2, widthIdx: 2 }),
      wordHeaderCell('free', { colSpan: 3 }),
      wordHeaderCell('ctrl', { rowSpan: 2, widthIdx: 6 }),
      wordHeaderCell('controlled', { colSpan: 3 }),
      wordHeaderCell('eval', { rowSpan: 2, widthIdx: 10 }),
    ],
  });
  const row2 = new TableRow({
    tableHeader: true,
    cantSplit: true,
    children: [
      wordHeaderCell('s', { widthIdx: 3 }),
      wordHeaderCell('l', { widthIdx: 4 }),
      wordHeaderCell('risk', { widthIdx: 5 }),
      wordHeaderCell('s', { widthIdx: 7 }),
      wordHeaderCell('l', { widthIdx: 8 }),
      wordHeaderCell('risk', { widthIdx: 9 }),
    ],
  });
  return [row1, row2];
}

function wordItemRow(item, index, lang, { keepNext = false } = {}) {
  // cantSplit: a row never breaks across pages (same as the PDF).
  // keepNext (last row only): keeps that row on the same page as the
  // signature block, so the signatures never land on a page alone.
  const { TableRow, TableCell, VerticalAlign } = window.docx;
  const o = { keepNext };
  const cell = (paras, widthIdx) => new TableCell({ width: wordColWidth(widthIdx), verticalAlign: VerticalAlign.CENTER, children: paras });

  return new TableRow({
    cantSplit: true,
    children: [
      cell([wordCenteredParagraph(index + 1, o)], 0),
      cell(wordBilingualParagraphs(item.hazard, lang, o), 1),
      cell(wordBilingualParagraphs(item.effect, lang, o), 2),
      cell([wordCenteredParagraph(item.severityBefore, o)], 3),
      cell([wordCenteredParagraph(item.likelihoodBefore, o)], 4),
      cell([wordCenteredParagraph(`${item.severityBefore}${item.likelihoodBefore}`, o)], 5),
      cell(wordBilingualParagraphs(item.ctrl, lang, o), 6),
      cell([wordCenteredParagraph(item.severityAfter, o)], 7),
      cell([wordCenteredParagraph(item.likelihoodAfter, o)], 8),
      cell([wordCenteredParagraph(`${item.severityAfter}${item.likelihoodAfter}`, o)], 9),
      cell(wordRiskCellParagraphs(item.severityAfter, item.likelihoodAfter, lang, o), 10),
    ],
  });
}

function wordMetaValueOrBlank(value) {
  // Reserve visible blank width so a printed copy has room to write it in.
  return value || '\u00A0'.repeat(18);
}

function buildWatermarkPng() {
  // Same stamp as the PDF's .rpt-watermark (bold Arial 82px, letter-spacing
  // 10px, gray at 35% opacity, rotated -30deg, centred on the page), drawn
  // on a page-sized canvas so it can sit behind the text on every page.
  try {
    const W = 1500;
    const H = Math.round(W * (210 / 297));
    const canvas = document.createElement('canvas');
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.translate(W / 2, H / 2);
    ctx.rotate((-30 * Math.PI) / 180);
    ctx.font = 'bold 82px Arial, Helvetica, sans-serif';
    if ('letterSpacing' in ctx) ctx.letterSpacing = '10px';
    ctx.fillStyle = 'rgba(120, 120, 120, 0.35)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('CONTROLLED COPY', 0, 0);
    return canvas.toDataURL('image/png');
  } catch (e) {
    return null;
  }
}

function wordWatermarkParagraph() {
  const { Paragraph, ImageRun, HorizontalPositionRelativeFrom, VerticalPositionRelativeFrom } = window.docx;
  const png = buildWatermarkPng();
  if (!png) return null;
  return new Paragraph({
    children: [new ImageRun({
      data: dataUrlToUint8Array(png),
      transformation: { width: Math.round(297 * PX96_PER_MM), height: Math.round(210 * PX96_PER_MM) },
      floating: {
        horizontalPosition: { relative: HorizontalPositionRelativeFrom.PAGE, offset: 0 },
        verticalPosition: { relative: VerticalPositionRelativeFrom.PAGE, offset: 0 },
        behindDocument: true,
        allowOverlap: true,
      },
    })],
  });
}

function wordDocControlStrip() {
  // Full-width black bar: Form Code left, Issue/Rev centred, Rev Date right
  // (DOC_CONTROL_* constants are defined once in exportPdf.js).
  const { Table, TableRow, TableCell, Paragraph, TextRun, WidthType, AlignmentType, ShadingType, VerticalAlign } = window.docx;
  const third = Math.round(WORD_USABLE_WIDTH_TWIPS / 3);
  const cell = (text, alignment) => new TableCell({
    width: { size: third, type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    shading: { type: ShadingType.CLEAR, fill: '000000' },
    margins: { top: 60, bottom: 60, left: 140, right: 140 },
    children: [new Paragraph({ alignment, children: [new TextRun({ text, color: 'FFFFFF', size: FS_STRIP, font: 'Arial' })] })],
  });
  return new Table({
    width: { size: WORD_USABLE_WIDTH_TWIPS, type: WidthType.DXA },
    columnWidths: [third, third, third],
    borders: wordNoBorders(),
    rows: [new TableRow({
      children: [
        cell(`Form Code: ${DOC_CONTROL_FORM_CODE}`, AlignmentType.LEFT),
        cell(`Issue# (${DOC_CONTROL_ISSUE})    Rev. (${DOC_CONTROL_REV})`, AlignmentType.CENTER),
        cell(`Rev Date: ${DOC_CONTROL_REV_DATE}`, AlignmentType.RIGHT),
      ],
    })],
  });
}

function wordPageHeader(project) {
  // Repeating page Header: watermark + doc-control strip + logos/title box.
  // Always English only.
  const {
    Header, Table, TableRow, TableCell, Paragraph, TextRun, ImageRun,
    WidthType, AlignmentType, VerticalAlign, BorderStyle,
  } = window.docx;

  const border = { style: BorderStyle.SINGLE, size: 12, color: '000000' };
  const borders = { top: border, bottom: border, left: border, right: border };
  const noBorder = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const noCellBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

  const logoCell = (dataUrl, widthIdx) => new TableCell({
    width: { size: HEADER_BOX_WIDTHS_TWIPS[widthIdx], type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    borders,
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new ImageRun({ data: dataUrlToUint8Array(dataUrl), transformation: { width: WORD_LOGO_IMG_PX, height: WORD_LOGO_IMG_PX } })],
    })],
  });

  // Location (left) / Date (mid) / PTW# (right) via a borderless 3-cell
  // table (tab stops are unreliable across Word/LibreOffice).
  const metaCell = (text, alignment) => new TableCell({
    borders: noCellBorders,
    children: [new Paragraph({ alignment, children: [new TextRun({ text, size: FS_META, font: 'Arial' })] })],
  });
  const metaTable = new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: wordNoBorders(),
    rows: [new TableRow({
      children: [
        metaCell(`Location: ${wordMetaValueOrBlank(project.location?.en)}`, AlignmentType.LEFT),
        metaCell(`Date: ${formatDDMMYYYY(project.date)}`, AlignmentType.CENTER),
        metaCell(`PTW#: ${wordMetaValueOrBlank(project.ptwNumber)}`, AlignmentType.RIGHT),
      ],
    })],
  });

  const titleLine = (text) => new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ text, bold: true, size: FS_TITLE, font: 'Arial' })],
  });

  const logoTitleTable = new Table({
    width: { size: WORD_USABLE_WIDTH_TWIPS, type: WidthType.DXA },
    columnWidths: HEADER_BOX_WIDTHS_TWIPS,
    rows: [new TableRow({
      children: [
        logoCell(LOGO_RASHPETCO_DATA_URL, 0),
        new TableCell({
          width: { size: HEADER_BOX_WIDTHS_TWIPS[1], type: WidthType.DXA },
          verticalAlign: VerticalAlign.CENTER,
          borders,
          margins: { top: 220, bottom: 220, left: 300, right: 300 },
          children: [
            titleLine('HSE Risk Assessment'),
            titleLine(`Task / Activity: ${project.title?.en || ''}`),
            new Paragraph({ spacing: { before: 120 }, children: [] }),
            metaTable,
          ],
        }),
        logoCell(LOGO_BURULLUS_DATA_URL, 2),
      ],
    })],
  });

  const watermark = wordWatermarkParagraph();
  return new Header({
    children: [
      ...(watermark ? [watermark] : []),
      wordDocControlStrip(),
      logoTitleTable,
      // Gap between the header box and the table (PDF: 18px margin).
      new Paragraph({ spacing: { before: 0, after: 0 }, children: [new TextRun({ text: '', size: 8 })] }),
    ],
  });
}

function wordPageFooter() {
  // Repeating page Footer: "UPDATED <date>" left, dynamic page number right
  // (LAST_UPDATED_DATE is defined once in exportPdf.js). Word controls its
  // own pagination, so the page number must be a native field, not a static
  // value - PageNumber.CURRENT inserts a real PAGE field.
  const {
    Footer, Table, TableRow, TableCell, Paragraph, TextRun,
    WidthType, AlignmentType, BorderStyle, PageNumber,
  } = window.docx;
  const noBorder = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const noCellBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };
  const half = Math.round(WORD_USABLE_WIDTH_TWIPS / 2);

  const cell = (runs, alignment) => new TableCell({
    width: { size: half, type: WidthType.DXA },
    borders: noCellBorders,
    margins: { left: 180, right: 180 },
    children: [new Paragraph({ alignment, children: runs })],
  });

  const footerTable = new Table({
    width: { size: WORD_USABLE_WIDTH_TWIPS, type: WidthType.DXA },
    columnWidths: [half, half],
    borders: wordNoBorders(),
    rows: [new TableRow({
      children: [
        cell([new TextRun({ text: `UPDATED ${LAST_UPDATED_DATE}`, size: FS_FOOTER, font: 'Arial' })], AlignmentType.LEFT),
        cell([new TextRun({ children: [PageNumber.CURRENT, ' | Page'], size: FS_FOOTER, font: 'Arial' })], AlignmentType.RIGHT),
      ],
    })],
  });

  return new Footer({ children: [footerTable] });
}

function wordSignatureRow() {
  // Signature block as the last row of the main table (one borderless cell
  // spanning all columns, holding a 3-column layout): each column has a
  // bold label, ~25mm blank space for the handwritten signature, then a
  // line (80% of the column width) - same as the PDF. Being a row of the
  // same table, it can't split (cantSplit), and the last item row carries
  // keepNext, so if the block doesn't fit, that row moves to the new page
  // with it - the signatures never sit on a page with zero items.
  const { Paragraph, Table, TableRow, TableCell, TextRun, WidthType, AlignmentType, BorderStyle } = window.docx;
  const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const noCellBorders = { top: none, bottom: none, left: none, right: none };
  const third = Math.round(WORD_USABLE_WIDTH_TWIPS / 3);
  const lineIndent = Math.round(third * 0.1);
  const gapTwips = Math.round(40 * (297 / 1500) * TWIPS_PER_MM); // PDF: 40px margin-top

  const block = (label) => new TableCell({
    width: { size: third, type: WidthType.DXA },
    borders: noCellBorders,
    children: [
      new Paragraph({
        keepNext: true,
        keepLines: true,
        spacing: { before: gapTwips },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: label, bold: true, size: FS_SIG, font: 'Arial' })],
      }),
      new Paragraph({
        keepLines: true,
        spacing: { before: WORD_SIGNATURE_SPACE_TWIPS },
        indent: { left: lineIndent, right: lineIndent },
        border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: '000000', space: 1 } },
        children: [new TextRun({ text: '', size: 4 })],
      }),
    ],
  });

  const inner = new Table({
    width: { size: WORD_USABLE_WIDTH_TWIPS, type: WidthType.DXA },
    columnWidths: [third, third, third],
    borders: wordNoBorders(),
    rows: [new TableRow({
      cantSplit: true,
      children: [block('Issuing Authority'), block('Performing Authority'), block('HSE Engineer')],
    })],
  });

  return new TableRow({
    cantSplit: true,
    children: [new TableCell({
      columnSpan: WORD_COL_WEIGHTS.length,
      borders: { left: none, right: none, bottom: none },
      margins: { left: 0, right: 0 },
      children: [inner, new Paragraph({ children: [new TextRun({ text: '', size: 2 })] })],
    })],
  });
}

async function exportProjectToWord(project, lang) {
  const { Document, Packer, Table, WidthType, PageOrientation } = window.docx;
  const lastIdx = project.items.length - 1;

  const table = new Table({
    width: { size: WORD_USABLE_WIDTH_TWIPS, type: WidthType.DXA },
    columnWidths: WORD_COL_WIDTHS_TWIPS,
    rows: [
      ...wordHeaderRows(),
      ...project.items.map((item, i) => wordItemRow(item, i, lang, { keepNext: i === lastIdx })),
      wordSignatureRow(),
    ],
  });

  const doc = new Document({
    sections: [{
      properties: {
        page: {
          size: { width: WORD_PAGE_SHORT_TWIPS, height: WORD_PAGE_LONG_TWIPS, orientation: PageOrientation.LANDSCAPE },
          margin: {
            top: WORD_MARGIN_TOP_TWIPS,
            bottom: WORD_MARGIN_BOTTOM_TWIPS,
            left: WORD_MARGIN_LR_TWIPS,
            right: WORD_MARGIN_LR_TWIPS,
            header: WORD_HEADER_DIST_TWIPS,
            footer: WORD_FOOTER_DIST_TWIPS,
          },
        },
      },
      headers: { default: wordPageHeader(project) },
      footers: { default: wordPageFooter() },
      children: [table],
    }],
  });

  const blob = await Packer.toBlob(doc);
  const fname = `${sanitizeFilename(project.title?.en) || 'risk-assessment'}.docx`;
  saveAs(blob, fname);
}