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

        self.summeryLabels = ['PTW#', 'Type', 'Date', 'Department', 'Requestor', 'Location', 'Equipment', 'Description']
        self.summeryFields = ['id',   'type', 'date', 'department', 'requestor', 'location', 'equipment', 'description']

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
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def ptwToRecord(self, ptw):
        record = []
        for field in self.summeryFields:
            record.append(str(getattr(ptw, field)))
        return record

    def addPTWToGUI(self, ptw):
        self.ptwsData.append(ptw)
        data = self.ptwToRecord(ptw)
        self.tbl.setSortingEnabled(False)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for i, d in enumerate(data):
            cell = QTableWidgetItem(d)
            cell.setBackground(QBrush(ptw.backgroundColor()))
            cell.setForeground(QBrush(ptw.foregroundColor()))
            self.tbl.setItem(row, i, cell)
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
            cell = QTableWidgetItem(d)
            cell.setBackground(QBrush(ptw.backgroundColor()))
            cell.setForeground(QBrush(ptw.foregroundColor()))
            self.tbl.setItem(row, i, cell)
        self.tbl.setSortingEnabled(True)
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def updatePTW(self, row: int, ptw):
        err = ClientRequests.updatePTW(self.loggedUser, ptw)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return
        self.updatePTWInGUI(row, ptw)

    def deletePTW(self, row: int):
        ptw = self.ptwsData[row]
        reply = QMessageBox.question(self, 'Delete PTW', f"Are you sure you want to delete PTW# '{ptw.id}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        err = ClientRequests.deletePTW(self.loggedUser, ptw.id)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return

        self.ptwsData.pop(row)
        self.tbl.removeRow(row)
        if self._filterBar.isVisible():
            self._populateFilters()

    def clear(self):
        self.tbl.clearContents()
        self.ptwsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def sort(self):
        self.tbl.sortItems(0, Qt.SortOrder.DescendingOrder)
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
