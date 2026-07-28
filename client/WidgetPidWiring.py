import os
from functools import partial

from PyQt6.QtCore import Qt, QRectF, QPointF, QDir, QFileInfo, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QBrush, QPen, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
                              QLabel, QFileDialog, QGraphicsView, QGraphicsScene,
                              QGraphicsRectItem, QMessageBox, QFrame, QDialog, QFormLayout,
                              QDialogButtonBox)
import qtawesome as qta

from Isolation import IC
from PTWData import Attachment
from clientRequests import ClientRequests
from i18n import t
import PidWiringHighlighter as highlighter


class _EditableHighlightItem(QGraphicsRectItem):
    """A highlight rectangle that can be selected, dragged, and corner-resized. Manual
    editing is always live (not a separate mode) - onReleased fires after every drag or
    resize so the caller can re-burn the highlight into the document immediately."""

    HANDLE_SIZE = 10

    def __init__(self, rect: QRectF, color: QColor, tooltip: str = '', onReleased=None):
        super().__init__(rect)
        self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 90)))
        self.setPen(QPen(color, 2))
        self.setToolTip(tooltip)
        self.setAcceptHoverEvents(True)
        self._resizeHandle = None
        self._onReleased = onReleased

    def _handleRects(self) -> dict:
        r = self.rect()
        s = self.HANDLE_SIZE
        return {
            'tl': QRectF(r.left() - s / 2, r.top() - s / 2, s, s),
            'tr': QRectF(r.right() - s / 2, r.top() - s / 2, s, s),
            'bl': QRectF(r.left() - s / 2, r.bottom() - s / 2, s, s),
            'br': QRectF(r.right() - s / 2, r.bottom() - s / 2, s, s),
        }

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setBrush(QBrush(Qt.GlobalColor.white))
            painter.setPen(QPen(Qt.GlobalColor.black))
            for hr in self._handleRects().values():
                painter.drawRect(hr)

    def _handleAt(self, pos: QPointF):
        for name, hr in self._handleRects().items():
            if hr.contains(pos):
                return name
        return None

    def hoverMoveEvent(self, event):
        handle = self._handleAt(event.pos()) if self.isSelected() else None
        if handle in ('tl', 'br'):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in ('tr', 'bl'):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self._pressRect = self.rect()
        self._resizeHandle = self._handleAt(event.pos()) if self.isSelected() else None
        if self._resizeHandle:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizeHandle:
            r = self.rect()
            p = event.pos()
            if self._resizeHandle == 'tl':
                newRect = QRectF(p, r.bottomRight())
            elif self._resizeHandle == 'tr':
                newRect = QRectF(QPointF(r.left(), p.y()), QPointF(p.x(), r.bottom()))
            elif self._resizeHandle == 'bl':
                newRect = QRectF(QPointF(p.x(), r.top()), QPointF(r.right(), p.y()))
            else:
                newRect = QRectF(r.topLeft(), p)
            newRect = newRect.normalized()
            if newRect.width() > 5 and newRect.height() > 5:
                self.setRect(newRect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resizeHandle = None
        super().mouseReleaseEvent(event)
        if self._onReleased and self.rect() != getattr(self, '_pressRect', self.rect()):
            self._onReleased()


class _AssignHighlightDialog(QDialog):
    """Small popup to attach a freshly hand-drawn rectangle to an isolation item. State
    isn't chosen here - it's always taken from that item's current state in the items
    list, so a manual highlight can never disagree with the table it came from."""

    def __init__(self, parent, items: list):
        super().__init__(parent)
        self.setWindowTitle(t("Assign Highlight"))
        self.setModal(True)
        self._items = items

        lyt = QFormLayout(self)
        self.tagCombo = QComboBox()
        self.tagCombo.addItems([i.tag for i in items])
        lyt.addRow(t("Item:"), self.tagCombo)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

    def selected(self) -> tuple:
        tag = self.tagCombo.currentText()
        item = next((i for i in self._items if i.tag == tag), None)
        return tag, (item.state if item else '')


class _PidGraphicsView(QGraphicsView):
    """Wheel-zoom + drag-pan viewer for a single rendered page image. When armed via
    armAddRect(True), a click-drag on empty canvas draws a new rectangle instead of
    panning, and emits rectDrawn once released. A floating, editable zoom-level combo
    sits pinned to the bottom-left corner, always reflecting the current scale."""

    rectDrawn = pyqtSignal(QRectF)

    ZOOM_PRESETS = ['25%', '50%', '75%', '100%', '125%', '150%', '200%', '300%', '400%']
    ZOOM_MIN_PERCENT = 5
    ZOOM_MAX_PERCENT = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # Scrollbars are redundant here (panning is click-drag via ScrollHandDrag above) and
        # actively wrong with them on: fitInView computes its fit against whatever viewport
        # size is current *at that instant* - if a scrollbar is showing (from the previous
        # page/zoom) it shrinks the viewport fitInView measures, so the resulting scale ends
        # up too zoomed-in relative to the final, scrollbar-free size. Permanently off avoids
        # that feedback loop entirely, rather than fighting it around each fitInView call.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._drawingNew = False
        self._drawStart = None
        self._drawItem = None

        self.zoomCombo = QComboBox(self)
        self.zoomCombo.setEditable(True)
        self.zoomCombo.addItems(self.ZOOM_PRESETS)
        self.zoomCombo.setFixedWidth(80)
        self.zoomCombo.setToolTip(t("Zoom level - pick a preset or type a percentage"))
        self.zoomCombo.setStyleSheet("""
            QComboBox { background: rgba(255, 255, 255, 220); color: black; }
            QComboBox QAbstractItemView { background: white; color: black; }
        """)
        self.zoomCombo.activated.connect(self._onZoomComboChosen)
        self.zoomCombo.lineEdit().returnPressed.connect(self._onZoomComboEntered)
        self._updateZoomDisplay()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 20
        self.zoomCombo.move(self.width() - self.zoomCombo.width() - margin,
                             self.height() - self.zoomCombo.height() - margin)

    def fitInView(self, *args, **kwargs):
        # Qt gotcha: if the previous content left scrollbars visible, fitInView computes
        # its scale against the scrollbar-shrunk viewport, then the scrollbars disappear
        # once the new (smaller) scale no longer needs them - leaving the result zoomed in
        # slightly more than a true fit to the final, full-size viewport. Force scrollbars
        # off for the computation itself to avoid the feedback loop, then restore policy.
        hPolicy, vPolicy = self.horizontalScrollBarPolicy(), self.verticalScrollBarPolicy()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        super().fitInView(*args, **kwargs)
        self.setHorizontalScrollBarPolicy(hPolicy)
        self.setVerticalScrollBarPolicy(vPolicy)
        self._updateZoomDisplay()

    def _currentZoomPercent(self) -> int:
        return round(self.transform().m11() * 100)

    def _updateZoomDisplay(self):
        self.zoomCombo.blockSignals(True)
        self.zoomCombo.setEditText(f"{self._currentZoomPercent()}%")
        self.zoomCombo.blockSignals(False)

    def _parsePercent(self, text: str):
        digits = ''.join(ch for ch in text if ch.isdigit())
        if not digits:
            return None
        return max(self.ZOOM_MIN_PERCENT, min(int(digits), self.ZOOM_MAX_PERCENT))

    def _setZoomPercent(self, percent: int):
        # use the exact transform scale, not the rounded display percentage - compounding
        # the display's own rounding here would make repeated entry (e.g. "100%") drift
        # away from the value actually requested.
        current = self.transform().m11()
        if current <= 0:
            return
        factor = (percent / 100) / current
        self.scale(factor, factor)
        self._updateZoomDisplay()

    def _onZoomComboChosen(self, index: int):
        percent = self._parsePercent(self.zoomCombo.itemText(index))
        if percent:
            self._setZoomPercent(percent)
        else:
            self._updateZoomDisplay()

    def _onZoomComboEntered(self):
        percent = self._parsePercent(self.zoomCombo.currentText())
        if percent:
            self._setZoomPercent(percent)
        else:
            self._updateZoomDisplay()

    def wheelEvent(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
        self.scale(factor, factor)
        self._updateZoomDisplay()

    def armAddRect(self, armed: bool):
        self._drawingNew = armed
        self.setDragMode(QGraphicsView.DragMode.NoDrag if armed else QGraphicsView.DragMode.ScrollHandDrag)

    def mousePressEvent(self, event):
        # the rendered page itself is a full-page QGraphicsPixmapItem, so itemAt() almost
        # never returns None for a click inside the page - only an existing highlight
        # should block starting a new draw (so it can be moved/resized instead).
        if self._drawingNew and not isinstance(self.itemAt(event.pos()), _EditableHighlightItem):
            self._drawStart = self.mapToScene(event.pos())
            self._drawItem = QGraphicsRectItem(QRectF(self._drawStart, self._drawStart))
            self._drawItem.setPen(QPen(Qt.GlobalColor.blue, 2, Qt.PenStyle.DashLine))
            self.scene().addItem(self._drawItem)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drawingNew and self._drawItem is not None:
            self._drawItem.setRect(QRectF(self._drawStart, self.mapToScene(event.pos())).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drawingNew and self._drawItem is not None:
            rect = self._drawItem.rect()
            self.scene().removeItem(self._drawItem)
            self._drawItem = None
            self.armAddRect(False)
            if rect.width() > 5 and rect.height() > 5:
                self.rectDrawn.emit(rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class WidgetPidWiring(QWidget):
    """P&ID/Wiring tab embedded inside an IC dialog.

    Read-only (viewing an existing IC): shows the burned-in file flatly, no editing.
    Editable (creating an IC): shows the pristine original with the current highlights
    overlaid as live, draggable/resizable rectangles - there's no separate "edit mode",
    manual adjustments apply immediately (re-burning the file) as soon as you let go of
    a drag, add one, or delete one."""

    def __init__(self, parent, loggedUser, ic: IC, readonly: bool):
        super().__init__(parent)
        self.loggedUser = loggedUser
        self.ic = ic
        self.readonly = readonly
        self.docsToBeUploaded: list[Attachment] = []

        self._currentDoc = None          # IC.PidWiringDocument currently selected, or None
        self._currentOriginalPath = None  # local path to the pristine original (editable mode only)
        self._currentBurnedPath = None    # local path to the burned-in file (staged locally, or a fetched temp copy)
        self._displayPdfDoc = None        # QPdfDocument backing the current on-screen page, when it's a PDF
        self._displayImage = None         # QImage backing the current on-screen page, when it's a plain image
        self._currentPage = 0
        self._pairs = []                  # list of (IC.Highlight, _EditableHighlightItem) for the displayed page

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(4, 4, 4, 0)  # zero bottom margin - this is the last tab content before
                                             # the dialog's own Ok/Cancel row, no need to double that gap

        topRow = QHBoxLayout()
        self.docCombo = QComboBox()
        self.docCombo.currentIndexChanged.connect(self._onDocComboChanged)
        topRow.addWidget(self.docCombo, stretch=1)

        self.btnOpenExternal = QPushButton(qta.icon('fa6s.up-right-from-square'), t("Open Externally"))
        self.btnOpenExternal.clicked.connect(self._openExternally)
        topRow.addWidget(self.btnOpenExternal)

        self.btnUpload = QPushButton(qta.icon('fa6s.upload'), t("Upload"))
        self.btnUpload.clicked.connect(self._uploadDocument)
        self.btnUpload.setVisible(not readonly)
        topRow.addWidget(self.btnUpload)

        self.btnDeleteDoc = QPushButton(qta.icon('fa6s.trash'), t("Delete"))
        self.btnDeleteDoc.clicked.connect(self._deleteSelectedDoc)
        self.btnDeleteDoc.setVisible(not readonly)
        topRow.addWidget(self.btnDeleteDoc)
        lyt.addLayout(topRow)

        self.view = _PidGraphicsView()
        self.scene = QGraphicsScene(self.view)
        self.view.setScene(self.scene)
        self.view.rectDrawn.connect(self._onNewRectDrawn)
        lyt.addWidget(self.view, stretch=1)

        navRow = QHBoxLayout()
        self.btnPrevPage = QPushButton(qta.icon('fa6s.chevron-left'), '')
        self.btnPrevPage.clicked.connect(partial(self._changePage, -1))
        self.lblPage = QLabel('')
        self.lblPage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btnNextPage = QPushButton(qta.icon('fa6s.chevron-right'), '')
        self.btnNextPage.clicked.connect(partial(self._changePage, 1))
        navRow.addStretch()
        navRow.addWidget(self.btnPrevPage)
        navRow.addWidget(self.lblPage)
        navRow.addWidget(self.btnNextPage)
        navRow.addStretch()
        lyt.addLayout(navRow)

        toolsRow = QHBoxLayout()
        self.btnSync = QPushButton(qta.icon('fa6s.arrows-rotate'), t("Sync"))
        self.btnSync.setToolTip(t("Recompute automatic highlights for all documents from the current items list (keeps manual highlights)."))
        self.btnSync.clicked.connect(self._resyncAll)
        self.btnClear = QPushButton(qta.icon('fa6s.eraser'), t("Clear"))
        self.btnClear.setToolTip(t("Remove all highlights, including manual ones, from this document."))
        self.btnClear.clicked.connect(self._clearSelectedDocHighlights)
        self.btnAddHighlight = QPushButton(qta.icon('fa6s.highlighter'), t("Draw"))
        self.btnAddHighlight.clicked.connect(lambda: self.view.armAddRect(True))
        self.btnDeleteHighlight = QPushButton(qta.icon('fa6s.trash'), t("Delete Selected"))
        self.btnDeleteHighlight.clicked.connect(self._deleteSelectedHighlight)
        toolsRow.addWidget(self.btnSync)
        toolsRow.addWidget(self.btnClear)
        toolsRow.addWidget(self.btnAddHighlight)
        toolsRow.addWidget(self.btnDeleteHighlight)
        toolsRow.addStretch()
        toolsRow.addWidget(self._legendSwatch(IC.colorForItemState(IC.IsolationItem.States.OPEN), t("Open")))
        toolsRow.addWidget(self._legendSwatch(IC.colorForItemState(IC.IsolationItem.States.CLOSE), t("Closed")))
        lyt.addLayout(toolsRow)
        for w in (self.btnSync, self.btnClear, self.btnAddHighlight, self.btnDeleteHighlight):
            w.setVisible(not readonly)

        self._refreshDocCombo()

    def _legendSwatch(self, color, text) -> QWidget:
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        swatch = QFrame()
        swatch.setFixedSize(14, 14)
        swatch.setStyleSheet(f"background-color: {color.name()}; border-radius: 3px;")
        l.addWidget(swatch)
        l.addWidget(QLabel(text))
        return w

    # ------------------------------------------------------------------ document list

    def _refreshDocCombo(self, selectFilename: str = None):
        self.docCombo.blockSignals(True)
        self.docCombo.clear()
        for doc in self.ic.pid_documents:
            label = doc.filename + ("  [OCR]" if doc.ocr_used else "")
            icon = qta.icon('fa6s.file-pdf' if doc.filename.lower().endswith('.pdf') else 'fa6s.file-image')
            self.docCombo.addItem(icon, label)
        self.docCombo.blockSignals(False)

        if not self.ic.pid_documents:
            self._currentDoc = None
            self._showEmptyMessage(t("No P&ID / Wiring documents attached."))
            return

        idx = 0
        if selectFilename:
            idx = next((i for i, d in enumerate(self.ic.pid_documents) if d.filename == selectFilename), 0)
        self.docCombo.blockSignals(True)
        self.docCombo.setCurrentIndex(idx)
        self.docCombo.blockSignals(False)
        self._selectDocument(self.ic.pid_documents[idx])

    def _onDocComboChanged(self, index: int):
        if index < 0 or index >= len(self.ic.pid_documents):
            return
        self._selectDocument(self.ic.pid_documents[index])

    def _localPathFor(self, doc: 'IC.PidWiringDocument'):
        return self._stagedPathFor(doc.filename)

    def _originalLocalPathFor(self, doc: 'IC.PidWiringDocument'):
        return self._stagedPathFor(doc.original_filename)

    def _stagedPathFor(self, remoteName: str):
        for attach in self.docsToBeUploaded:
            if attach.remoteName == remoteName:
                return attach.localPath
        return None

    def _replaceStagedFile(self, remoteName: str, newLocalPath: str):
        for attach in self.docsToBeUploaded:
            if attach.remoteName == remoteName:
                attach.localPath = newLocalPath
                return
        self.docsToBeUploaded.append(Attachment(localPath=newLocalPath, remoteName=remoteName, uploaded=False))

    # ------------------------------------------------------------------ display

    def _selectDocument(self, doc: 'IC.PidWiringDocument'):
        self._currentDoc = doc
        self._currentPage = 0
        self._pairs = []
        self._currentBurnedPath = self._localPathFor(doc)
        self._currentOriginalPath = None if self.readonly else self._originalLocalPathFor(doc)

        if self.readonly:
            if self._currentBurnedPath:
                self._loadDisplayFile(self._currentBurnedPath)
            else:
                self._fetchBurnedThenLoad(doc)
        else:
            sourcePath = self._currentOriginalPath or self._currentBurnedPath
            if sourcePath:
                self._loadDisplayFile(sourcePath)

    def _fetchBurnedThenLoad(self, doc: 'IC.PidWiringDocument'):
        overlay = getattr(self.window(), '_refreshOverlay', None)
        if overlay:
            overlay.showBusy()

        def on_done(err, filepath):
            if overlay:
                overlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to fetch document:") + f" {err}")
                return
            self._currentBurnedPath = filepath
            self._loadDisplayFile(filepath)
        ClientRequests.getIcAttachment(self.loggedUser, self.ic.id, doc.filename, callback=on_done)

    def _loadDisplayFile(self, filePath: str):
        self._displayPdfDoc = None
        self._displayImage = None
        try:
            if filePath.lower().endswith('.pdf'):
                self._displayPdfDoc = highlighter.loadPdfDocument(filePath)
            else:
                self._displayImage = QImage(filePath)
        except Exception as e:
            QMessageBox.warning(self, t("Error"), t("Failed to open document:") + f" {e}")
            return
        self._showPage(0)

    def _pageCount(self) -> int:
        if self._displayPdfDoc is not None:
            return max(self._displayPdfDoc.pageCount(), 1)
        return 1

    def _showPage(self, pageIndex: int):
        pageCount = self._pageCount()
        self._currentPage = max(0, min(pageIndex, pageCount - 1))

        if self._displayPdfDoc is not None:
            image = highlighter.renderPage(self._displayPdfDoc, self._currentPage)
        else:
            image = self._displayImage

        self.scene.clear()
        self._pairs = []
        if image is not None and not image.isNull():
            self.scene.addPixmap(QPixmap.fromImage(image))
            self.scene.setSceneRect(QRectF(image.rect()))
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

            if not self.readonly and self._currentDoc is not None:
                width, height = image.width(), image.height()
                for h in self._currentDoc.highlights:
                    if h.page != self._currentPage:
                        continue
                    rect = self._fractionalToScene(h.rect, width, height)
                    item = _EditableHighlightItem(rect, IC.colorForItemState(h.state), tooltip=h.tag,
                                                   onReleased=self._onHighlightGeometryChanged)
                    self.scene.addItem(item)
                    self._pairs.append((h, item))

        multi = pageCount > 1
        self.btnPrevPage.setVisible(multi)
        self.btnNextPage.setVisible(multi)
        self.lblPage.setVisible(multi)
        self.lblPage.setText(f"{t('Page')} {self._currentPage + 1} / {pageCount}")
        self.btnPrevPage.setEnabled(self._currentPage > 0)
        self.btnNextPage.setEnabled(self._currentPage < pageCount - 1)

    def _changePage(self, delta: int):
        self._showPage(self._currentPage + delta)

    def _showEmptyMessage(self, text: str):
        self.scene.clear()
        self._pairs = []
        self.scene.addText(text)
        self.btnPrevPage.setVisible(False)
        self.btnNextPage.setVisible(False)
        self.lblPage.setVisible(False)

    def _openExternally(self):
        if not self._currentBurnedPath:
            QMessageBox.information(self, t("No Document"), t("Select a document first."))
            return
        from ReportGenerator import ReportGenerator
        ReportGenerator.openPDF(self._currentBurnedPath)

    # ------------------------------------------------------------------ upload / delete document

    def _existingFilenames(self) -> set:
        names = set()
        for doc in self.ic.pid_documents:
            names.add(doc.filename)
            names.add(doc.original_filename)
        return names

    def _uniqueOriginalName(self, filename: str) -> str:
        base, ext = os.path.splitext(filename)
        return f"{base}__original{ext}"

    def _uploadDocument(self):
        fileDialog = QFileDialog(self, t("Select P&ID / Wiring file to upload"), QDir.homePath(),
                                  "PDF/Image (*.pdf *.jpg *.jpeg *.png);;All Files (*)")
        fileDialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if not fileDialog.exec():
            return
        selected = fileDialog.selectedFiles()
        if not selected:
            return
        filePath = selected[0]
        filename = QFileInfo(filePath).fileName()
        if filename in self._existingFilenames():
            QMessageBox.warning(self, t("Error"), t("A P&ID/Wiring document with the same filename already exists."))
            return

        overlay = getattr(self.window(), '_refreshOverlay', None)
        if overlay:
            overlay.showBusy()

        def on_compute_done(err, result):
            if err:
                if overlay:
                    overlay.hideBusy()
                QMessageBox.warning(self, t("Error"), t("Failed to process document:") + f" {err}")
                return
            highlights, pageCount, ocrUsed = result

            def on_burn_done(err2, burnedInPath):
                if overlay:
                    overlay.hideBusy()
                if err2:
                    QMessageBox.warning(self, t("Error"), t("Failed to process document:") + f" {err2}")
                    return
                originalName = self._uniqueOriginalName(filename)
                doc = IC.PidWiringDocument(filename=filename, original_filename=originalName,
                                            page_count=pageCount, ocr_used=ocrUsed, highlights=highlights)
                self.ic.pid_documents.append(doc)
                self.docsToBeUploaded.append(Attachment(localPath=burnedInPath, remoteName=filename, uploaded=False))
                self.docsToBeUploaded.append(Attachment(localPath=filePath, remoteName=originalName, uploaded=False))
                self._refreshDocCombo(selectFilename=filename)

            highlighter.burnInHighlightsAsync(filePath, highlights, callback=on_burn_done)

        highlighter.computeHighlightsAsync(filePath, self.ic.items, callback=on_compute_done)

    def _deleteSelectedDoc(self):
        doc = self._currentDoc
        if doc is None:
            return
        reply = QMessageBox.question(
            self, t("Delete Document"), t("Remove '{0}' from this IC?").format(doc.filename),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.ic.pid_documents.remove(doc)
        self.docsToBeUploaded[:] = [a for a in self.docsToBeUploaded if a.remoteName not in (doc.filename, doc.original_filename)]
        self._refreshDocCombo()

    # ------------------------------------------------------------------ sync / clear

    def onItemsChanged(self):
        """Connected to TableIsolationItems.itemsChanged - offers to resync whenever
        the isolation items list changes, but only asks if there's actually something
        to resync."""
        if self.readonly or not self.ic.pid_documents:
            return
        reply = QMessageBox.question(
            self, t("Isolation Items Changed"),
            t("The isolation items list has changed. Resync P&ID/Wiring highlights now?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._resyncAll()

    def _resyncAll(self):
        if not self.ic.pid_documents:
            return
        currentFilename = self._currentDoc.filename if self._currentDoc else None
        overlay = getattr(self.window(), '_refreshOverlay', None)
        if overlay:
            overlay.showBusy()

        queue = list(self.ic.pid_documents)
        errors = []

        def process_next():
            if not queue:
                if overlay:
                    overlay.hideBusy()
                if errors:
                    QMessageBox.warning(self, t("Error"), t("Failed to resync highlights:") + "\n" + "\n".join(errors))
                self._refreshDocCombo(selectFilename=currentFilename)
                return

            doc = queue.pop(0)
            originalPath = self._originalLocalPathFor(doc)
            if not originalPath:
                process_next()
                return
            manualHighlights = [h for h in doc.highlights if h.manual]

            def on_compute_done(err, result, doc=doc, manualHighlights=manualHighlights, originalPath=originalPath):
                if err:
                    errors.append(err)
                    process_next()
                    return
                autoHighlights, pageCount, ocrUsed = result
                combined = manualHighlights + autoHighlights

                def on_burn_done(err2, newBurnedPath, doc=doc, combined=combined, pageCount=pageCount, ocrUsed=ocrUsed):
                    if err2:
                        errors.append(err2)
                        process_next()
                        return
                    doc.highlights = combined
                    doc.page_count = pageCount
                    doc.ocr_used = ocrUsed
                    self._replaceStagedFile(doc.filename, newBurnedPath)
                    process_next()

                highlighter.burnInHighlightsAsync(originalPath, combined, callback=on_burn_done)

            highlighter.computeHighlightsAsync(originalPath, self.ic.items, callback=on_compute_done)

        process_next()

    def _clearSelectedDocHighlights(self):
        doc = self._currentDoc
        if doc is None or self.readonly:
            return
        reply = QMessageBox.question(
            self, t("Clear Highlights"),
            t("Remove all highlights, including manual ones, from '{0}'?").format(doc.filename),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        originalPath = self._originalLocalPathFor(doc)
        if not originalPath:
            return

        overlay = getattr(self.window(), '_refreshOverlay', None)
        if overlay:
            overlay.showBusy()

        def on_done(err, newPath):
            if overlay:
                overlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to clear highlights:") + f" {err}")
                return
            doc.highlights = []
            doc.ocr_used = False
            self._replaceStagedFile(doc.filename, newPath)
            self._refreshDocCombo(selectFilename=doc.filename)

        highlighter.burnInHighlightsAsync(originalPath, [], callback=on_done)

    # ------------------------------------------------------------ manual highlight editing (always live)

    def _applyCurrentPageHighlights(self):
        doc = self._currentDoc
        if doc is None or self.readonly or not self._currentOriginalPath:
            return
        width, height = self.scene.sceneRect().width(), self.scene.sceneRect().height()
        otherPageHighlights = [h for h in doc.highlights if h.page != self._currentPage]
        thisPageHighlights = []
        for h, item in self._pairs:
            # only the highlight(s) that actually moved/resized get marked manual - an
            # untouched sibling on the same page must keep its existing manual/auto status
            # so a later Sync can still refresh it if it was never a manual override. A
            # tolerance (not exact equality) is required: a fractional->pixel->fractional
            # round-trip through an untouched item's own unchanged rect isn't always
            # bit-exact, and a spurious mismatch would wrongly flip it to manual.
            newRect = self._sceneToFractional(item.rect(), width, height)
            if not self._rectsClose(newRect, h.rect):
                h.rect = newRect
                h.manual = True
            thisPageHighlights.append(h)
        doc.highlights = otherPageHighlights + thisPageHighlights

        overlay = getattr(self.window(), '_refreshOverlay', None)
        if overlay:
            overlay.showBusy()

        def on_done(err, newBurnedPath):
            if overlay:
                overlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to apply highlight changes:") + f" {err}")
                return
            self._replaceStagedFile(doc.filename, newBurnedPath)
            self._currentBurnedPath = newBurnedPath

        highlighter.burnInHighlightsAsync(self._currentOriginalPath, doc.highlights, callback=on_done)

    def _onHighlightGeometryChanged(self):
        self._applyCurrentPageHighlights()

    def _onNewRectDrawn(self, rect: QRectF):
        if self._currentDoc is None or self.readonly:
            return
        if not self.ic.items:
            QMessageBox.information(self, t("No Items"), t("Add an isolation item first."))
            return
        dlg = _AssignHighlightDialog(self, self.ic.items)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        tag, state = dlg.selected()
        h = IC.Highlight(tag=tag, page=self._currentPage, rect=[0.0, 0.0, 0.0, 0.0], state=state, manual=True)
        item = _EditableHighlightItem(rect, IC.colorForItemState(state), tooltip=tag,
                                       onReleased=self._onHighlightGeometryChanged)
        self.scene.addItem(item)
        self._pairs.append((h, item))
        self._applyCurrentPageHighlights()

    def _deleteSelectedHighlight(self):
        if self._currentDoc is None or self.readonly:
            return
        selected = set(self.scene.selectedItems())
        if not selected:
            return
        for item in selected:
            self.scene.removeItem(item)
        self._pairs = [(h, gi) for h, gi in self._pairs if gi not in selected]
        self._applyCurrentPageHighlights()

    @staticmethod
    def _fractionalToScene(rect: list, width: float, height: float) -> QRectF:
        x, y, w, h = rect
        return QRectF(x * width, y * height, w * width, h * height)

    @staticmethod
    def _sceneToFractional(rect: QRectF, width: float, height: float) -> list:
        if width <= 0 or height <= 0:
            return [0.0, 0.0, 0.0, 0.0]
        return [rect.x() / width, rect.y() / height, rect.width() / width, rect.height() / height]

    @staticmethod
    def _rectsClose(a: list, b: list, tol: float = 1e-6) -> bool:
        return all(abs(x - y) < tol for x, y in zip(a, b))
