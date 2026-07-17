from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QAbstractItemView, QHeaderView, QFrame,
                              QMenu, QMessageBox)
from PyQt6.QtGui import QFont, QBrush, QAction
from typing import Iterable
from functools import partial
import qtawesome as qta

from clientRequests import ClientRequests
from PTWData import PTWData
from CheckableComboBox import CheckableComboBox
from GlobalData import globalData


class _FastTrackItem(QTableWidgetItem):
    """F.T. column cell: display text is left empty (so no colored/highlighted
    text can ever leak through, selected or not - the bolt icon is drawn by a
    separate cell widget). Sorts by the real Yes/No value stashed in UserRole."""

    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)
        return super().__lt__(other)


class TablePTWs(QWidget):
    class MenuOption:
        def __init__(self, lbl, fun, icn, allAtOnce : bool = False):
            self.lbl = lbl
            self.fun = fun
            self.icn = icn
            self.allAtOnce = allAtOnce

    def __init__(self, parent, loggedUser, label: str):
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.ptwsData = []
        self.loggedUser = loggedUser
        self.options = []

        self.summeryLabels = ['PTW#', 'F.T.',       'Type', 'Request Time', 'Department', 'Requestor', 'Location', 'Equipment', 'Description']
        self.summeryFields = ['id',   'fast_track', 'type', 'request_date', 'department', 'requestor', 'location', 'equipment', 'description']
        self._ftCol = self.summeryFields.index('fast_track')

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
        self._filterBtn.setObjectName("filterBtn")

        self._filterBtn.setCheckable(True)
        self._filterBtn.toggled.connect(self._toggleFilters)
        lblLyt.addStretch()
        lblLyt.addWidget(self._filterBtn)

        self._filterBar = QWidget()
        filterBarLayout = QHBoxLayout(self._filterBar)
        filterBarLayout.setContentsMargins(0, 0, 0, 0)
        filterBarLayout.setSpacing(0)
        self._filterCombos = []
        for i, _ in enumerate(self.summeryLabels):
            combo = CheckableComboBox()
            combo.filterChanged.connect(self._applyFilters)
            # if i < len(self.summeryLabels) - 1:
            #     combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            # else:
            #     combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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

    def _populateFilters(self):
        col_values = [set() for _ in self.summeryLabels]
        for row in range(self.tbl.rowCount()):
            for col in range(len(self.summeryLabels)):
                item = self.tbl.item(row, col)
                if item:
                    col_values[col].add(self._cellFilterText(item))
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
                (item := self.tbl.item(row, col)) is not None and self._cellFilterText(item) not in allowed
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
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def ptwToRecord(self, ptw):
        record = []
        for field in self.summeryFields:
            value = getattr(ptw, field)
            if field == 'fast_track':
                value = 'Yes' if value else 'No'
            elif field == 'requestor' and value:
                user = globalData.allUsers.get(value)
                if user:
                    value = user.getName()
            record.append(str(value))
        return record

    def _makeCell(self, col: int, value: str) -> QTableWidgetItem:
        if col == self._ftCol:
            cell = _FastTrackItem("")
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        return QTableWidgetItem(value)

    @staticmethod
    def _cellFilterText(item: QTableWidgetItem) -> str:
        userData = item.data(Qt.ItemDataRole.UserRole)
        return userData if userData is not None else item.text()

    def _applyFastTrackStyle(self, cell: QTableWidgetItem, fastTrack: bool):
        if fastTrack:
            font = cell.font()
            font.setBold(True)
            if font.pointSize() > 0:
                font.setPointSize(font.pointSize() + 3)
            else:
                font.setPixelSize(font.pixelSize() + 4)
            cell.setFont(font)

    def _fastTrackIconWidget(self, fastTrack: bool) -> QLabel:
        # setTextAlignment() only centers the item's text block, not its icon -
        # a QLabel cell widget is used so the icon itself is genuinely centered
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent;")
        if fastTrack:
            lbl.setPixmap(qta.icon('fa6s.bolt', color='orange').pixmap(24, 24))
        return lbl

    def addPTWToGUI(self, ptw):
        self.ptwsData.append(ptw)
        data = self.ptwToRecord(ptw)
        self.tbl.setSortingEnabled(False)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            cell.setBackground(QBrush(ptw.backgroundColor()))
            cell.setForeground(QBrush(ptw.foregroundColor()))
            self._applyFastTrackStyle(cell, ptw.fast_track)
            self.tbl.setItem(row, i, cell)
            if i == self._ftCol:
                self.tbl.setCellWidget(row, i, self._fastTrackIconWidget(ptw.fast_track))
        self.tbl.setSortingEnabled(True)
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def addOption(self, options: MenuOption):
        self.options.append(options)

    def addOptions(self, options: Iterable[MenuOption]):
        self.options.extend(options)

    def updatePTWInGUI(self, row: int, ptw):
        self.ptwsData[row] = ptw
        data = self.ptwToRecord(ptw)
        self.tbl.setSortingEnabled(False)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            cell.setBackground(QBrush(ptw.backgroundColor()))
            cell.setForeground(QBrush(ptw.foregroundColor()))
            self._applyFastTrackStyle(cell, ptw.fast_track)
            self.tbl.setItem(row, i, cell)
            if i == self._ftCol:
                self.tbl.setCellWidget(row, i, self._fastTrackIconWidget(ptw.fast_track))
        self.tbl.setSortingEnabled(True)
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def updatePTW(self, row: int, ptw):
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.updatePTWInGUI(row, ptw)
        ClientRequests.updatePTW(self.loggedUser, ptw, callback=on_done)

    def deletePTW(self, row: int):
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.ptwsData.pop(row)
            self.tbl.removeRow(row)
            if self._filterBar.isVisible():
                self._populateFilters()
        
        ptw = self.ptwsData[row]
        reply = QMessageBox.question(self, 'Delete PTW', f"Are you sure you want to delete PTW# '{ptw.id}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            ClientRequests.deletePTW(self.loggedUser, ptw.id, callback=on_done)

    def clear(self):
        self.tbl.clearContents()
        self.ptwsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def sort(self):
        self.tbl.sortItems(0, Qt.SortOrder.AscendingOrder)
        self._syncPtwsData()

    def _syncPtwsData(self):
        id_to_ptw = {str(p.id): p for p in self.ptwsData}
        self.ptwsData = [id_to_ptw[self.tbl.item(r, 0).text()] for r in range(self.tbl.rowCount())]

    def doubleClickHandler(self, row, col):
        if len(self.options) > 0:
            self.options[0].fun(row, self.ptwsData[row])

    def optionDoForAllSelected(self, fun, allAtOnce: bool):
        selectedRows = list(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()))
        if allAtOnce:
            fun(selectedRows, [self.ptwsData[row] for row in selectedRows])
        else:
            for row in selectedRows[::-1]:          # reverse to avoid messing up row numbers when deleting
                fun(row, self.ptwsData[row])

    def showContextMenu(self, pos: QPoint):
        row = self.tbl.indexAt(pos)

        if not row.isValid():
            return

        row = row.row()
        menu = QMenu(self.tbl)

        for option in self.options:
            action = QAction(option.icn, option.lbl, self.tbl)
            menu.addAction(action)
            action.triggered.connect(partial(self.optionDoForAllSelected, option.fun, option.allAtOnce))

        menu.exec(self.tbl.mapToGlobal(pos))
