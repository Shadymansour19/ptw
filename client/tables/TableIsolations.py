from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QPushButton, QDialog, QMessageBox,
                              QMenu)
from PyQt6.QtGui import QKeySequence, QAction, QShortcut
import qtawesome as qta

from models.Isolation import Isolation
from dialogs.DialogIsolation import DialogIsolation


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
