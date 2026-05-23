from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from typing import Iterable
from functools import partial

from clientRequests import ClientRequests
from PTWData import PTWData

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

        self.label = label
        lbl = QLabel(label)
        lbl.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setLayout(lyt)
        self.setAutoFillBackground(False)
        lyt.addWidget(lbl)
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
        # self.tbl.insertActions

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
    

    def clear(self):
        self.tbl.clearContents()
        self.ptwsData.clear()
        self.tbl.setRowCount(0)

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
    