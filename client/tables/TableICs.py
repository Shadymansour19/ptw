from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QAbstractItemView, QHeaderView, QFrame,
                              QMenu, QMessageBox, QDialog)
from PyQt6.QtGui import QFont, QBrush, QAction
from typing import Iterable
from functools import partial
import qtawesome as qta

from network.clientRequests import ClientRequests
from models.Isolation import IC
from dialogs.DialogIC import DialogIC
from widgets.CheckableComboBox import CheckableComboBox
from GlobalData import globalData


class _LongTermItem(QTableWidgetItem):
    """Long Term column cell: display text is left empty (so no colored/highlighted
    text can ever leak through, selected or not - the icon is drawn by a separate
    cell widget). Sorts by the real Yes/No value stashed in UserRole."""

    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)
        return super().__lt__(other)


class TableICs(QWidget):
    """Reusable per-tab browsing widget for ICs, mirroring TablePTWs."""

    def __init__(self, parent, loggedUser, label: str):
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.icsData: list[IC] = []
        self.loggedUser = loggedUser
        self.options = []

        self.summeryLabels = ['IC#', 'Status', 'Type', 'L.T.',      'Requestor', 'Request Time',        'Requestor Dept.',      'Execution Dept.',      'Location', 'Equipment', 'Reason']
        self.summeryFields = ['id',  'status', 'type', 'long_term', 'requestor', 'requestor_timestamp', 'requestor_department', 'execution_department', 'location', 'equipment', 'reason']
        self._ltCol = self.summeryFields.index('long_term')

        lblLyt = QHBoxLayout()
        lblLyt.setContentsMargins(10, 0, 10, 0)
        self.label = label
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
        for _ in self.summeryLabels:
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

        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.cellDoubleClicked.connect(self.doubleClickHandler)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self.showContextMenu)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setStyleSheet("QTableWidget { background: transparent; }")
        self.tbl.viewport().setAutoFillBackground(False)
        self.tbl.verticalHeader().hide()
        self.tbl.setFrameShape(QFrame.Shape.NoFrame)
        self.tbl.horizontalHeader().sectionResized.connect(self._syncFilterWidths)
        self.tbl.horizontalHeader().sortIndicatorChanged.connect(self._onSorted)

    def _toggleFilters(self, checked):
        self._filterBar.setVisible(checked)
        if checked:
            self._populateFilters()
            self._syncFilterWidths()
            self._applyFilters()
        else:
            self._showAllRows()

    def _cellFilterText(self, col: int, item: QTableWidgetItem) -> str:
        if col == self._ltCol:
            return item.data(Qt.ItemDataRole.UserRole)
        return item.text()

    def _populateFilters(self):
        col_values = [set() for _ in self.summeryLabels]
        for row in range(self.tbl.rowCount()):
            for col in range(len(self.summeryLabels)):
                item = self.tbl.item(row, col)
                if item:
                    col_values[col].add(self._cellFilterText(col, item))
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
                (item := self.tbl.item(row, col)) is not None and self._cellFilterText(col, item) not in allowed
                for col, allowed in active
            )
            self.tbl.setRowHidden(row, hide)

    def _showAllRows(self):
        for row in range(self.tbl.rowCount()):
            self.tbl.setRowHidden(row, False)

    def filterColumn(self, label: str, values: set):
        if label not in self.summeryLabels:
            return
        col = self.summeryLabels.index(label)
        if not self._filterBtn.isChecked():
            self._filterBtn.setChecked(True)   # -> _toggleFilters(True): populates + applies
        else:
            self._populateFilters()
            self._syncFilterWidths()
        self._filterCombos[col].setCheckedOnly(values)

    def _onSorted(self):
        self._syncICsData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def icToRecord(self, ic: IC):
        record = []
        for field in self.summeryFields:
            if field == 'status':
                value = ic.getStatus().value
            elif field == 'long_term':
                value = 'Yes' if ic.long_term else 'No'
            else:
                value = getattr(ic, field)
                if field == 'requestor' and value:
                    user = globalData.allUsers.get(value)
                    if user:
                        value = user.getName()
            record.append(str(value) if value is not None else '')
        return record

    def _makeCell(self, col: int, value: str) -> QTableWidgetItem:
        if col == self._ltCol:
            cell = _LongTermItem("")
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        return QTableWidgetItem(value)

    
    def _longTermIconWidget(self, longTerm: bool) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if longTerm:
            badge = QLabel()
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet("background: rgba(0, 0, 0, 140); border-radius: 14px;")
            badge.setPixmap(qta.icon('ph.infinity-bold', color='cyan').pixmap(20, 20))
            layout.addWidget(badge)
        return container

    def addICToGUI(self, ic: IC):
        self.icsData.append(ic)
        data = self.icToRecord(ic)
        self.tbl.setSortingEnabled(False)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            if i == 0:
                cell.setData(Qt.ItemDataRole.UserRole, ic.id)
            cell.setBackground(QBrush(ic.backgroundColor()))
            cell.setForeground(QBrush(ic.foregroundColor()))
            self.tbl.setItem(row, i, cell)
            if i == self._ltCol:
                self.tbl.setCellWidget(row, i, self._longTermIconWidget(ic.long_term))
        self.tbl.setSortingEnabled(True)
        self._syncICsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def addOption(self, option):
        self.options.append(option)

    def addOptions(self, options: Iterable):
        self.options.extend(options)

    def clear(self):
        self.tbl.clearContents()
        self.icsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def sort(self):
        self.tbl.sortItems(0, Qt.SortOrder.AscendingOrder)
        self._syncICsData()

    def _syncICsData(self):
        id_to_cert = {str(c.id): c for c in self.icsData}
        self.icsData = [
            id_to_cert[str(self.tbl.item(r, 0).data(Qt.ItemDataRole.UserRole))]
            for r in range(self.tbl.rowCount())
        ]

    def doubleClickHandler(self, row, col):
        if len(self.options) > 0:
            self.options[0].fun(row, self.icsData[row])

    def optionDoForAllSelected(self, fun, allAtOnce: bool):
        selectedRows = list(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()))
        if allAtOnce:
            fun(selectedRows, [self.icsData[row] for row in selectedRows])
        else:
            for row in selectedRows[::-1]:
                fun(row, self.icsData[row])

    def showContextMenu(self, pos: QPoint):
        row = self.tbl.indexAt(pos)
        if not row.isValid():
            return
        ic = self.icsData[row.row()]
        menu = QMenu(self.tbl)
        for option in self.options:
            if option.visibleFor is not None and not option.visibleFor(ic):
                continue
            action = QAction(option.icn, option.lbl, self.tbl)
            menu.addAction(action)
            action.triggered.connect(partial(self.optionDoForAllSelected, option.fun, option.allAtOnce))
        menu.exec(self.tbl.mapToGlobal(pos))

    def addNewICDialog(self):
        ic = IC()
        dlg = DialogIC(self, self.loggedUser, ic, True, False, "New IC")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ic = dlg.getIC()

        def on_done(err, icId):
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            ic.id = icId
            globalData.ics[ic.id] = ic
            self.addICToGUI(ic)
            if dlg.pidDocsToBeUploaded:
                def on_pid_upload_done(err, _):
                    if err:
                        QMessageBox.warning(self, "Warning", f"IC saved but failed to upload P&ID/Wiring documents:\n{err}")
                ClientRequests.addIcAttachments(self.loggedUser, ic.id, dlg.pidDocsToBeUploaded, callback=on_pid_upload_done)

        self.window()._refreshOverlay.showBusy()
        ClientRequests.addIC(self.loggedUser, ic, callback=on_done)
