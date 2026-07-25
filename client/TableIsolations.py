from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QPushButton, QDialog, QMessageBox,
                              QMenu, QLabel, QFormLayout, QDialogButtonBox)
from PyQt6.QtGui import QFont, QKeySequence, QAction, QShortcut
import qtawesome as qta

from Isolation import Isolation
from DialogIsolation import DialogIsolation
from CheckableComboBox import CheckableComboBox


class TablePTWIsolations(QWidget):
    """Editable isolation list embedded inside a PTW form."""

    def __init__(self, parent, isolations, readonly):
        super().__init__(parent)
        lyt = QVBoxLayout()
        self.tbl = QTableWidget()
        self.readonly = readonly
        self.isolations: list[Isolation] = isolations

        self.summeryLabels = ['Type', 'Tag', 'Description']
        self.summeryFields = ['type', 'tag', 'description']

        self.setLayout(lyt)
        lyt.addWidget(self.tbl)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setAlternatingRowColors(True)
        if not readonly:
            self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tbl.customContextMenuRequested.connect(self.showContextMenu)
        for isolation in self.isolations:
            self.__addIsolationToGUI(isolation)

        self.btnNewIsolation = QPushButton(self)
        self.btnNewIsolation.setIcon(qta.icon('fa6s.plus', color='white'))
        self.btnNewIsolation.setFixedSize(60, 60)
        self.btnNewIsolation.setIconSize(QSize(32, 32))
        self.btnNewIsolation.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border-radius: 30px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.btnNewIsolation.setToolTip("New Isolation [Ctrl+N]")
        self.btnNewIsolation.clicked.connect(self.newIsolationDialog)
        self.btnNewIsolation.setVisible(not readonly)
        self.btnFABUpdatePosition()

        if not readonly:
            shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
            shortcut.activated.connect(self.newIsolationDialog)

    def resizeEvent(self, event):
        self.btnFABUpdatePosition()
        return super().resizeEvent(event)

    def btnFABUpdatePosition(self):
        margin = 40
        x = self.width() - self.btnNewIsolation.width() - margin
        y = self.height() - self.btnNewIsolation.height() - margin
        self.btnNewIsolation.move(x, y)

    def clear(self):
        self.tbl.clearContents()
        self.isolations.clear()
        self.tbl.setRowCount(0)

    def __addIsolationToGUI(self, isolation: Isolation):
        self.tbl.insertRow(self.tbl.rowCount())
        data = [str(getattr(isolation, f)) for f in self.summeryFields]
        for i, d in enumerate(data):
            cell = QTableWidgetItem(d)
            self.tbl.setItem(self.tbl.rowCount()-1, i, cell)

    def addIsolation(self, isolation: Isolation):
        self.__addIsolationToGUI(isolation)
        self.isolations.append(isolation)
        self.refreshGUI()

    def newIsolationDialog(self):
        dialog = DialogIsolation(self)
        resp = dialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            isolation = dialog.getIsolation()
            if isolation.tag in [i.tag for i in self.isolations]:
                QMessageBox.warning(self, "Error", "An isolation with the same tag already exists.")
                return
            self.addIsolation(isolation)

    def refreshGUI(self):
        self.tbl.clearContents()
        self.tbl.setRowCount(0)
        for isolation in self.isolations:
            self.__addIsolationToGUI(isolation)

    def deleteIsolation(self, row: int):
        self.isolations.pop(row)
        self.tbl.removeRow(row)

    def getIsolations(self):
        return self.isolations

    def deleteSelectedRows(self):
        selectedRows = sorted(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()), reverse=True)
        for row in selectedRows:
            self.deleteIsolation(row)

    def showContextMenu(self, pos: QPoint):
        row = self.tbl.indexAt(pos)
        if not row.isValid():
            return
        row = row.row()
        menu = QMenu(self.tbl)
        actionDelete = QAction('Delete', self.tbl)
        actionDelete.triggered.connect(self.deleteSelectedRows)
        menu.addAction(actionDelete)
        menu.exec(self.tbl.mapToGlobal(pos))


class TableIsolationsBrowser(QWidget):
    """Read-only isolation browser shown on the main isolations screen."""

    def __init__(self, parent, loggedUser, label: str):
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.isolationsData: list[Isolation] = []
        self.loggedUser = loggedUser

        self.summaryLabels = ['Type', 'Tag', 'Description', 'Held By', 'Linked PTWs']
        self.summeryFields = ['type', 'tag', 'description', 'held_by', 'linked_ptws']

        lblLyt = QHBoxLayout()
        lblLyt.setContentsMargins(10, 0, 10, 0)
        lbl = QLabel(label)
        lbl.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lblLyt.addStretch()
        lblLyt.addWidget(lbl)

        self._filterBtn = QPushButton(qta.icon('fa6s.filter'), "")
        self._filterBtn.setToolTip("Filter")
        self._filterBtn.setIconSize(QSize(32, 32))
        self._filterBtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filterBtn.setStyleSheet("""
            QPushButton { background: transparent; border: none; padding: 6px; border-radius: 6px; }
            QPushButton:hover { background: rgba(128, 128, 128, 0.15); }
            QPushButton:pressed { background: rgba(128, 128, 128, 0.30); }
            QPushButton:checked { background: palette(highlight); }
            QPushButton:checked:hover { background: palette(link); }
        """)
        self._filterBtn.setCheckable(True)
        self._filterBtn.toggled.connect(self._toggleFilters)
        lblLyt.addStretch()
        lblLyt.addWidget(self._filterBtn)

        self._filterBar = QWidget()
        filterBarLayout = QHBoxLayout(self._filterBar)
        filterBarLayout.setContentsMargins(0, 0, 0, 0)
        filterBarLayout.setSpacing(0)
        self._filterCombos = []
        for _ in self.summaryLabels:
            combo = CheckableComboBox()
            combo.filterChanged.connect(self._applyFilters)
            filterBarLayout.addWidget(combo)
            self._filterCombos.append(combo)
        self._filterBar.setVisible(False)

        self.setLayout(lyt)
        self.setAutoFillBackground(False)
        lyt.addLayout(lblLyt)
        lyt.addWidget(self._filterBar)
        lyt.addWidget(self.tbl)

        self.tbl.setColumnCount(len(self.summaryLabels))
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.cellDoubleClicked.connect(self._onDoubleClick)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summaryLabels)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setStyleSheet("QTableWidget { background: transparent; }")
        self.tbl.viewport().setAutoFillBackground(False)
        self.tbl.verticalHeader().hide()
        self.tbl.horizontalHeader().sectionResized.connect(self._syncFilterWidths)
        self.tbl.horizontalHeader().sortIndicatorChanged.connect(self._onSorted)

    def isolationToRecord(self, isolation):
        record = []
        for field in self.summeryFields:
            val = getattr(isolation, field)
            if isinstance(val, bool):
                val = "Yes" if val else "No"
            elif isinstance(val, list):
                val = ', '.join(str(v) for v in val) if val else '—'
            record.append(val)
        return record

    def setIsolations(self, isolations: dict):
        self.tbl.setSortingEnabled(False)
        self.tbl.clearContents()
        self.isolationsData.clear()
        self.tbl.setRowCount(0)
        for iso in isolations.values():
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            data = self.isolationToRecord(iso)
            for i, d in enumerate(data):
                cell = QTableWidgetItem(d)
                self.tbl.setItem(row, i, cell)
            self.isolationsData.append(iso)
        self.tbl.setSortingEnabled(True)
        self._sync()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def clear(self):
        self.tbl.clearContents()
        self.isolationsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def _sync(self):
        tag_to_iso = {iso.tag: iso for iso in self.isolationsData}
        self.isolationsData = [tag_to_iso[self.tbl.item(r, 1).text()] for r in range(self.tbl.rowCount())]

    def _toggleFilters(self, checked):
        self._filterBar.setVisible(checked)
        if checked:
            self._populateFilters()
            self._syncFilterWidths()
            self._applyFilters()
        else:
            self._showAllRows()

    def _populateFilters(self):
        col_values = [set() for _ in self.summaryLabels]
        for row in range(self.tbl.rowCount()):
            for col in range(len(self.summaryLabels)):
                item = self.tbl.item(row, col)
                if item:
                    col_values[col].add(item.text())
        for col, combo in enumerate(self._filterCombos):
            combo.setItems(col_values[col], preserve_selection=True)

    def _syncFilterWidths(self):
        if not self._filterBar.isVisible():
            return
        header = self.tbl.horizontalHeader()
        for i, combo in enumerate(self._filterCombos[:-1]):
            combo.setFixedWidth(header.sectionSize(i))
        self._filterCombos[-1].setMinimumWidth(header.sectionSize(len(self._filterCombos) - 1))

    def _applyFilters(self):
        active = [
            (col, combo.checkedItems())
            for col, combo in enumerate(self._filterCombos)
            if combo.isFiltering()
        ]
        for row in range(self.tbl.rowCount()):
            hide = any(
                (item := self.tbl.item(row, col)) is not None and item.text() not in allowed
                for col, allowed in active
            )
            self.tbl.setRowHidden(row, hide)

    def _showAllRows(self):
        for row in range(self.tbl.rowCount()):
            self.tbl.setRowHidden(row, False)

    def _onSorted(self):
        self._sync()
        if self._filterBar.isVisible():
            self._applyFilters()

    def _onDoubleClick(self, row, col):
        iso = self.isolationsData[row]

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Isolation — {iso.tag}")
        dlg.setMinimumWidth(420)

        lyt = QFormLayout(dlg)
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lyt.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        for label, value in [
            ("Type",                str(iso.type)),
            ("Tag",                 str(iso.tag)),
            ("Description",         str(iso.description)),
            ("Linked PTWs",         ', '.join(str(p) for p in iso.linked_ptws) or '—'),
            ("Held By",             ', '.join(str(p) for p in iso.held_by) or '—'),
        ]:
            val_lbl = QLabel(value)
            val_lbl.setWordWrap(True)
            lyt.addRow(f"<b>{label}:</b>", val_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        lyt.addRow(btns)

        dlg.exec()
