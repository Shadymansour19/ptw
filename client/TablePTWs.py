from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from typing import Iterable
from functools import partial
import qtawesome as qta
import tempfile

from clientRequests import ClientRequests
from PTWData import PTWData

_SELECT_ALL = "(Select All)"


class CheckableComboBox(QComboBox):
    filterChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self._summary_text = "(All)"
        self.view().pressed.connect(self._handleItemPressed)
        self._skip_hide = False
        self._addSelectAllItem()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = self._summary_text
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, opt)
        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, opt, QStyle.SubControl.SC_ComboBoxEditField, self)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._summary_text)

    def _addSelectAllItem(self):
        item = QStandardItem(_SELECT_ALL)
        item.setCheckState(Qt.CheckState.Checked)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._model.appendRow(item)

    def _handleItemPressed(self, index):
        row = index.row()
        item = self._model.item(row)
        new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        if row == 0:
            item.setCheckState(new_state)
            for i in range(1, self._model.rowCount()):
                self._model.item(i).setCheckState(new_state)
        else:
            item.setCheckState(new_state)
            self._syncSelectAll()
        self._skip_hide = True
        self._updateText()
        self.filterChanged.emit()

    def _syncSelectAll(self):
        all_checked = all(
            self._model.item(i).checkState() == Qt.CheckState.Checked
            for i in range(1, self._model.rowCount())
        )
        self._model.item(0).setCheckState(
            Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked
        )

    def hidePopup(self):
        if self._skip_hide:
            self._skip_hide = False
            return
        super().hidePopup()

    def setItems(self, texts, preserve_selection=True):
        prev_unchecked = set()
        if preserve_selection:
            for i in range(1, self._model.rowCount()):  # skip Select All at 0
                item = self._model.item(i)
                if item.checkState() == Qt.CheckState.Unchecked:
                    prev_unchecked.add(item.text())
        self._model.clear()
        self._addSelectAllItem()
        for text in sorted(texts):
            item = QStandardItem(text)
            item.setCheckState(
                Qt.CheckState.Unchecked if (preserve_selection and text in prev_unchecked)
                else Qt.CheckState.Checked
            )
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._model.appendRow(item)
        self._syncSelectAll()
        self._updateText()

    def checkedItems(self):
        result = set()
        for i in range(1, self._model.rowCount()):  # skip Select All at 0
            item = self._model.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                result.add(item.text())
        return result

    def isFiltering(self):
        total = self._model.rowCount() - 1  # exclude Select All
        return len(self.checkedItems()) < total

    def _updateText(self):
        total = self._model.rowCount() - 1  # exclude Select All
        checked = len(self.checkedItems())
        if total == 0 or checked == total:
            self._summary_text = "(All)"
        elif checked == 0:
            self._summary_text = "(None)"
        elif checked == 1:
            self._summary_text = next(iter(self.checkedItems()))
        else:
            self._summary_text = f"({checked}/{total})"
        self.update()


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
            QPushButton:hover { background: rgba(255,255,255,40); }
            QPushButton:pressed { background: rgba(255,255,255,80); }
            QPushButton:checked { background: rgba(25,200,150,45); }
            QPushButton:checked:hover { background: rgba(25,200,150,65); }
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

    def addPTW(self, ptw, toUploadAttachs):
        err, ptwId = ClientRequests.addPTW(self.loggedUser, ptw)

        if err is not None:
            QMessageBox.warning(self, "Fail", err)
            return

        ptw.setId(ptwId)
        if bool(toUploadAttachs):
            err = ClientRequests.addPtwAttachments(self.loggedUser, ptw.id, toUploadAttachs)
            if err:
                QMessageBox.warning(self, "Error", f"Failed to upload attachments: {err}")
                return
            for a in toUploadAttachs:
                a.uploaded = True

        self.addPTWToGUI(ptw)

    def addPTWs(self, ptws: Iterable):
        for ptw in ptws:
            self.addPTW(ptw)

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
