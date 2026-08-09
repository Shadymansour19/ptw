"""P&ID/Wiring diagram highlight detection and burn-in.

Pure logic module (no UI) used by the P&ID/Wiring tab (`widgets.WidgetPidWiring`) of the
IC dialog. `computeHighlights()` locates each isolation item's tag on a PDF or image
diagram - via the PDF's native text layer where available, falling back to Tesseract OCR
for scanned pages or plain images - and returns the fractional page-relative rectangles
where it was found. `burnInHighlights()` then physically draws those rectangles into a
new copy of the file (PDF or image), so the highlights survive being opened in any
external viewer rather than existing only as an in-app overlay.
"""

import io
import logging
import os
import shutil
import tempfile

from PyQt6.QtCore import Qt, QBuffer, QIODevice, QSize, QEventLoop, QTimer
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtPdf import QPdfDocument, QPdfSearchModel

from models.Isolation import IC
from helper.OcrConfig import tessdataConfig
from network.RequestWorker import async_request

log = logging.getLogger("client")

# pypdf logs a WARNING ("Ignoring wrong pointing object N 0 (offset ...)") whenever a PDF's
# xref table has a stale/incorrect byte offset - common in real-world PDFs from a variety of
# tools, and pypdf recovers from it automatically via its own fallback object scan. It's noise,
# not a sign burn-in failed - only escalate this specific logger on genuine errors.
logging.getLogger("pypdf._reader").setLevel(logging.ERROR)

RENDER_TARGET_LONG_SIDE = 4000  # px; page raster resolution used for OCR and on-screen display -
                                 # the in-app view only scales this fixed pixmap up on zoom (no
                                 # re-render at higher detail), so this is the real ceiling on how
                                 # far you can zoom in before it looks blurry
HIGHLIGHT_ALPHA = 0.4           # 0..1; same opacity for fill and border - one solid-looking translucent color
HIGHLIGHT_PAD_RATIO = 0.15      # fraction of the detected text box's own width/height added as margin on each side
HIGHLIGHT_PAD_MIN = 0.005       # fractional page-size floor, so very small/short tags still get a visible margin


def _waitForReady(doc: QPdfDocument):
    """Block (via a local event loop) until doc finishes loading or fails."""
    if doc.status() in (QPdfDocument.Status.Ready, QPdfDocument.Status.Error):
        return
    loop = QEventLoop()
    doc.statusChanged.connect(loop.quit)
    loop.exec()


def _waitForSearch(model: QPdfSearchModel, timeoutMs: int = 1000):
    """Block (via a local event loop) until model's result count changes or timeoutMs elapses."""
    loop = QEventLoop()
    model.countChanged.connect(loop.quit)
    QTimer.singleShot(timeoutMs, loop.quit)
    loop.exec()


def loadPdfDocument(filePath: str) -> QPdfDocument:
    """Load filePath into a QPdfDocument and wait until it is ready to use."""
    doc = QPdfDocument(None)
    doc.load(filePath)
    _waitForReady(doc)
    return doc


def renderPage(doc: QPdfDocument, pageIndex: int, targetSize: QSize = None) -> QImage:
    """Rasterize one page of doc (at targetSize, or a resolution derived from the page's
    own point size) and flatten it onto an opaque white background."""
    rendered = doc.render(pageIndex, targetSize or _targetSizeForPage(doc.pagePointSize(pageIndex)))
    return _flattenOnWhite(rendered)


def _flattenOnWhite(image: QImage) -> QImage:
    """QPdfDocument.render() hands back a transparent image - the page "background" is
    alpha=0, not opaque white - which reads as black once alpha is ignored (by Tesseract,
    by a viewer that doesn't composite transparency, or once saved to a non-alpha format).
    Composite it onto an opaque white page so it looks/OCRs like an actual printed page."""
    if image.isNull() or not image.hasAlphaChannel():
        return image
    flattened = QImage(image.size(), QImage.Format.Format_RGB32)
    flattened.fill(Qt.GlobalColor.white)
    painter = QPainter(flattened)
    painter.drawImage(0, 0, image)
    painter.end()
    return flattened


def _targetSizeForPage(pageSizePoints) -> QSize:
    """Scale pageSizePoints so its longer side equals RENDER_TARGET_LONG_SIDE, preserving
    aspect ratio, for use as a raster render target."""
    longSide = max(pageSizePoints.width(), pageSizePoints.height())
    if longSide <= 0:
        return QSize(RENDER_TARGET_LONG_SIDE, RENDER_TARGET_LONG_SIDE)
    scale = RENDER_TARGET_LONG_SIDE / longSide
    return QSize(max(1, round(pageSizePoints.width() * scale)), max(1, round(pageSizePoints.height() * scale)))


def computeHighlights(filePath: str, items: list) -> tuple:
    """Returns (highlights: list[IC.Highlight], pageCount: int, ocrUsed: bool).
    Known limitation: a tag whose text is split across two lines by the diagram
    layout won't match via either the native-text or OCR path."""
    items = [i for i in items if i.tag]
    if not items:
        return [], (loadPdfDocument(filePath).pageCount() or 1) if filePath.lower().endswith('.pdf') else 1, False

    if filePath.lower().endswith('.pdf'):
        highlights, pageCount, ocrUsed = _computeForPdf(filePath, items)
    else:
        highlights, pageCount, ocrUsed = _computeForImage(filePath, items)

    for h in highlights:
        h.rect = _padRect(h.rect)
    return highlights, pageCount, ocrUsed


@async_request
def computeHighlightsAsync(filePath: str, items: list):
    """Same work as computeHighlights, wrapped for the async_request calling convention
    (call with callback=(err, result) to run OCR/PDF-search on a background QThread instead
    of the GUI thread) - the GUI thread would otherwise be blocked long enough for
    RefreshOverlay's busy animation to visibly stall on a slow document."""
    try:
        result = computeHighlights(filePath, items)
    except Exception as e:
        return str(e), None
    return None, result


def _padRect(rect: list) -> list:
    """Expands a tight text-detection box by HIGHLIGHT_PAD_RATIO on each side so the
    highlight reads as a callout around the text rather than a shrink-wrapped outline."""
    x, y, w, h = rect
    padX = max(w * HIGHLIGHT_PAD_RATIO, HIGHLIGHT_PAD_MIN)
    padY = max(h * HIGHLIGHT_PAD_RATIO, HIGHLIGHT_PAD_MIN)
    newX = max(0.0, x - padX)
    newY = max(0.0, y - padY)
    return [newX, newY, min(1.0 - newX, w + 2 * padX), min(1.0 - newY, h + 2 * padY)]


def _computeForPdf(filePath: str, items: list) -> tuple:
    """Compute highlights for a PDF: native-text search on every page that has any
    extractable text at all, OCR fallback on the rest (scanned/image-only pages).

    Returns (highlights, pageCount, ocrUsed) where ocrUsed is True if any page needed OCR.
    """
    doc = loadPdfDocument(filePath)
    pageCount = doc.pageCount()

    # A scanned/image-only page has NO extractable text at all, not just "little" text -
    # a page dense with short tag labels and nothing else can legitimately have a short
    # total, so "any text vs none" is the right signal, not a character-count threshold.
    scannedPages = {page for page in range(pageCount) if not doc.getAllText(page).text().strip()}

    highlights = []
    if len(scannedPages) < pageCount:
        highlights.extend(_searchNativeText(doc, items, scannedPages))
    for page in sorted(scannedPages):
        highlights.extend(_ocrMatchTags(renderPage(doc, page), items, page))

    return highlights, max(pageCount, 1), bool(scannedPages)


def _searchNativeText(doc: QPdfDocument, items: list, excludePages: set) -> list:
    """Search doc's real text layer for each item's tag (via QPdfSearchModel), skipping
    excludePages (the scanned pages handled separately by OCR), and return one Highlight
    per matched rectangle, normalized and converted to page-fractional coordinates."""
    highlights = []
    model = QPdfSearchModel(None)
    model.setDocument(doc)
    for item in items:
        model.setSearchString(item.tag)
        _waitForSearch(model)
        for page in range(doc.pageCount()):
            if page in excludePages:
                continue
            pageSize = doc.pagePointSize(page)
            if pageSize.width() <= 0 or pageSize.height() <= 0:
                continue
            for link in model.resultsOnPage(page):
                for rect in link.rectangles():
                    # QPdfSearchModel can hand back a rect with negative width/height
                    # (observed on rotated pages) - normalize before using it, or the
                    # highlight ends up with a nonsensical (even negative) box.
                    rect = rect.normalized()
                    highlights.append(IC.Highlight(
                        tag=item.tag,
                        page=page,
                        rect=[rect.x() / pageSize.width(), rect.y() / pageSize.height(),
                              rect.width() / pageSize.width(), rect.height() / pageSize.height()],
                        state=item.state,
                    ))
    return highlights


def _computeForImage(filePath: str, items: list) -> tuple:
    """Compute highlights for a plain image upload via OCR only (images have no text
    layer to search natively). Returns (highlights, pageCount=1, ocrUsed=True)."""
    image = QImage(filePath)
    if image.isNull():
        return [], 1, False
    return _ocrMatchTags(image, items, 0), 1, True


def _ocrMatchTags(image: QImage, items: list, page: int) -> list:
    """Run Tesseract OCR on image, group the recognized words into lines, and match each
    item's tag against each line's normalized text (whitespace-stripped, case-folded).
    On a match, the highlight rectangle is the union of that line's own word boxes, in
    pixel coordinates normalized to the image size. Returns [] (logging a warning)
    instead of raising if Tesseract is unavailable or fails."""
    try:
        import pytesseract
        from pytesseract import Output
        data = pytesseract.image_to_data(_qImageToPil(image), lang='eng', output_type=Output.DICT, config=tessdataConfig())
    except Exception as e:
        log.warning("OCR unavailable/failed, skipping highlights for page %d: %s", page, e)
        return []

    width, height = image.width(), image.height()
    if width <= 0 or height <= 0:
        return []

    highlights = []
    for lineText, words in _groupWordsIntoLines(data):
        normalizedLine = _normalize(lineText)
        for item in items:
            needle = _normalize(item.tag)
            if not needle or needle not in normalizedLine:
                continue
            x, y, w, h = _unionBox(words)
            highlights.append(IC.Highlight(
                tag=item.tag,
                page=page,
                rect=[x / width, y / height, w / width, h / height],
                state=item.state,
            ))
    return highlights


def _normalize(text: str) -> str:
    """Strip all whitespace and case-fold text, for whitespace/case-insensitive matching."""
    return ''.join(text.split()).casefold()


def _groupWordsIntoLines(data: dict) -> list:
    """Group pytesseract's flat per-word output (data, from image_to_data) into lines by
    (block, paragraph, line) key, preserving first-seen order.

    Returns a list of (lineText, words) tuples, where words is the list of
    (word, left, top, width, height) tuples that make up that line.
    """
    lineKeys = {}
    order = []
    for i in range(len(data.get('text', []))):
        word = data['text'][i].strip()
        if not word:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        if key not in lineKeys:
            lineKeys[key] = []
            order.append(key)
        lineKeys[key].append((word, data['left'][i], data['top'][i], data['width'][i], data['height'][i]))
    return [(' '.join(w[0] for w in lineKeys[key]), lineKeys[key]) for key in order]


def _unionBox(words: list) -> tuple:
    """Return the (x, y, width, height) bounding box enclosing every word's own box in
    words (each a (word, left, top, width, height) tuple)."""
    lefts = [w[1] for w in words]
    tops = [w[2] for w in words]
    rights = [w[1] + w[3] for w in words]
    bottoms = [w[2] + w[4] for w in words]
    x, y = min(lefts), min(tops)
    return x, y, max(rights) - x, max(bottoms) - y


def _qImageToPil(image: QImage):
    """Convert a QImage to a Pillow Image by round-tripping it through an in-memory PNG."""
    from PIL import Image
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, 'PNG')
    pilImage = Image.open(io.BytesIO(bytes(buf.data())))
    pilImage.load()
    buf.close()
    return pilImage


def burnInHighlights(filePath: str, highlights: list) -> str:
    """Produces a new local file with the highlight rectangles physically drawn into
    it and returns its path — the file at filePath is left untouched. This is what
    gets uploaded/stored, so the highlight survives being opened in any external
    PDF/image viewer, not just this app's own viewer."""
    if not highlights:
        return _copyUnchanged(filePath)
    if filePath.lower().endswith('.pdf'):
        return _burnInPdf(filePath, highlights)
    return _burnInImage(filePath, highlights)


@async_request
def burnInHighlightsAsync(filePath: str, highlights: list):
    """Same work as burnInHighlights, wrapped for the async_request calling convention."""
    try:
        result = burnInHighlights(filePath, highlights)
    except Exception as e:
        return str(e), None
    return None, result


def _copyUnchanged(filePath: str) -> str:
    """Copy filePath to a new temp file unmodified and return its path (used by
    burnInHighlights when there are no highlights to draw)."""
    fd, outPath = tempfile.mkstemp(suffix=os.path.splitext(filePath)[1], prefix='pidwiring-')
    os.close(fd)
    shutil.copyfile(filePath, outPath)
    return outPath


def _burnInPdf(filePath: str, highlights: list) -> str:
    """Draw highlights into a new copy of the PDF at filePath and return its path.

    Groups highlights by page, and for each page that needs any: bakes in the page's
    own rotation via transfer_rotation_to_content() first (so pypdf's mediabox agrees
    with the visual dimensions the highlight rects were computed against), builds a
    same-size overlay PDF page (_overlayPdfBytes) with the highlight rectangles drawn on
    it, and merges that overlay onto the page. Every page (highlighted or not) is then
    written out to a new PDF via PdfWriter.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(filePath)
    writer = PdfWriter()

    byPage = {}
    for h in highlights:
        byPage.setdefault(h.page, []).append(h)

    keepAlive = []  # overlay PdfReaders must outlive writer.write() below
    for pageIndex, page in enumerate(reader.pages):
        pageHighlights = byPage.get(pageIndex)
        if pageHighlights:
            # page.mediabox is the raw, un-rotated box - for a page with /Rotate 90/270
            # that's swapped relative to QPdfDocument.pagePointSize()/render(), which the
            # highlight rects were computed against. Baking the rotation into the actual
            # content (and zeroing /Rotate) makes the mediabox agree with Qt's visual
            # dimensions, so the overlay lands right-side-up instead of sideways.
            if page.get('/Rotate', 0):
                page.transfer_rotation_to_content()
            overlayReader = PdfReader(_overlayPdfBytes(float(page.mediabox.width), float(page.mediabox.height), pageHighlights))
            keepAlive.append(overlayReader)
            page.merge_page(overlayReader.pages[0])
        writer.add_page(page)

    fd, outPath = tempfile.mkstemp(suffix='.pdf', prefix='pidwiring-')
    os.close(fd)
    with open(outPath, 'wb') as f:
        writer.write(f)
    return outPath


def _overlayPdfBytes(width: float, height: float, highlights: list) -> io.BytesIO:
    """Build a single-page, width x height reportlab PDF (in memory) with each
    highlight's rectangle drawn filled and stroked in its state color, for merging onto
    the real page in _burnInPdf. Converts each fractional, top-left-origin rect (Qt
    convention) to PDF's bottom-left-origin coordinate space."""
    from reportlab.pdfgen import canvas as reportlab_canvas

    buf = io.BytesIO()
    c = reportlab_canvas.Canvas(buf, pagesize=(width, height))
    for h in highlights:
        x, y, w, hgt = h.rect
        boxWidth, boxHeight = w * width, hgt * height
        left = x * width
        bottom = height - (y * height) - boxHeight  # rect.y is top-left origin (Qt convention); PDF pages are bottom-left origin
        r, g, b = _colorForState(h.state)
        c.setFillColorRGB(r / 255, g / 255, b / 255, alpha=HIGHLIGHT_ALPHA)
        c.setStrokeColorRGB(r / 255, g / 255, b / 255, alpha=HIGHLIGHT_ALPHA)
        c.rect(left, bottom, boxWidth, boxHeight, fill=1, stroke=1)
    c.save()
    buf.seek(0)
    return buf


def _burnInImage(filePath: str, highlights: list) -> str:
    """Draw highlights into a new copy of the image at filePath and return its path.

    Draws all highlight rectangles onto a transparent RGBA overlay the same size as the
    image, alpha-composites that overlay over the (RGBA-converted) original, then
    converts back to the original color mode before saving to a new temp file.
    """
    from PIL import Image, ImageDraw

    image = Image.open(filePath)
    originalMode = image.mode
    rgba = image.convert('RGBA')
    overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = rgba.size
    for h in highlights:
        x, y, w, hgt = h.rect
        box = (x * width, y * height, (x + w) * width, (y + hgt) * height)
        r, g, b = _colorForState(h.state)
        alpha = round(HIGHLIGHT_ALPHA * 255)
        draw.rectangle(box, fill=(r, g, b, alpha), outline=(r, g, b, alpha), width=2)
    composed = Image.alpha_composite(rgba, overlay)
    final = composed if originalMode == 'RGBA' else composed.convert(originalMode)

    fd, outPath = tempfile.mkstemp(suffix=os.path.splitext(filePath)[1] or '.png', prefix='pidwiring-')
    os.close(fd)
    final.save(outPath)
    return outPath


def _colorForState(state: str) -> tuple:
    """Return the (r, g, b) burn-in color for an isolation item's state: red for OPEN,
    green for CLOSE, gray for anything else."""
    if state == IC.IsolationItem.States.OPEN:
        return (255, 0, 0)
    if state == IC.IsolationItem.States.CLOSE:
        return (0, 160, 0)
    return (128, 128, 128)
