from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QPushButton, QDialog, QMessageBox,
                              QMenu)
from PyQt6.QtGui import QKeySequence, QAction, QShortcut
import qtawesome as qta

from Isolation import IC
from DialogIsolationItem import DialogIsolationItem


class TableIsolationItems(QWidget):
    """Editable isolation-item list embedded inside an IC dialog."""

    def __init__(self, parent, items, readonly):
        super().__init__(parent)
        lyt = QVBoxLayout()
        self.tbl = QTableWidget()
        self.readonly = readonly
        self.items: list[IC.IsolationItem] = items

        self.summeryLabels = ['Tag', 'Description', 'State', 'Lock #', 'Lock Box #']
        self.summeryFields = ['tag', 'description', 'state', 'lock_num', 'lock_box_num']

        self.setLayout(lyt)
        lyt.addWidget(self.tbl)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.setAlternatingRowColors(True)
        if not readonly:
            self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tbl.customContextMenuRequested.connect(self.showContextMenu)
        for item in self.items:
            self.__addItemToGUI(item)

        self.btnNewItem = QPushButton(self)
        self.btnNewItem.setIcon(qta.icon('fa6s.plus', color='white'))
        self.btnNewItem.setFixedSize(60, 60)
        self.btnNewItem.setIconSize(QSize(32, 32))
        self.btnNewItem.setStyleSheet("""
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
        self.btnNewItem.setToolTip("New Isolation Item [Ctrl+N]")
        self.btnNewItem.clicked.connect(self.newItemDialog)
        self.btnNewItem.setVisible(not readonly)
        self.btnFABUpdatePosition()

        if not readonly:
            shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
            shortcut.activated.connect(self.newItemDialog)

    def resizeEvent(self, event):
        self.btnFABUpdatePosition()
        return super().resizeEvent(event)

    def btnFABUpdatePosition(self):
        margin = 40
        x = self.width() - self.btnNewItem.width() - margin
        y = self.height() - self.btnNewItem.height() - margin
        self.btnNewItem.move(x, y)

    def clear(self):
        self.tbl.clearContents()
        self.items.clear()
        self.tbl.setRowCount(0)

    def __addItemToGUI(self, item: 'IC.IsolationItem'):
        self.tbl.insertRow(self.tbl.rowCount())
        data = [str(getattr(item, f)) for f in self.summeryFields]
        for i, d in enumerate(data):
            cell = QTableWidgetItem(d)
            self.tbl.setItem(self.tbl.rowCount()-1, i, cell)

    def addItem(self, item: 'IC.IsolationItem'):
        self.__addItemToGUI(item)
        self.items.append(item)
        self.refreshGUI()

    def newItemDialog(self):
        dialog = DialogIsolationItem(self)
        resp = dialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            item = dialog.getItem()
            if item.tag in [i.tag for i in self.items]:
                QMessageBox.warning(self, "Error", "An isolation item with the same tag already exists.")
                return
            self.addItem(item)

    def refreshGUI(self):
        self.tbl.clearContents()
        self.tbl.setRowCount(0)
        for item in self.items:
            self.__addItemToGUI(item)

    def deleteItem(self, row: int):
        self.items.pop(row)
        self.tbl.removeRow(row)

    def getItems(self):
        return self.items

    def deleteSelectedRows(self):
        selectedRows = sorted(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()), reverse=True)
        for row in selectedRows:
            self.deleteItem(row)

    def showContextMenu(self, pos: QPoint):
        row = self.tbl.indexAt(pos)
        if not row.isValid():
            return
        menu = QMenu(self.tbl)
        actionDelete = QAction('Delete', self.tbl)
        actionDelete.triggered.connect(self.deleteSelectedRows)
        menu.addAction(actionDelete)
        menu.exec(self.tbl.mapToGlobal(pos))
