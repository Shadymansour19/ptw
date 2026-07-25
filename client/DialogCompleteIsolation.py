from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QDialogButtonBox)

from Isolation import IsolationCertificate
from i18n import t


class DialogCompleteIsolation(QDialog):
    """Shown to the isolator when completing physical isolation - lets them optionally
    record Lock #/Lock Box # per item. Tag/Description/State stay read-only here;
    only the lock fields are editable."""

    def __init__(self, parent, items: list['IsolationCertificate.IsolationItem']):
        super().__init__(parent)
        self.setWindowTitle(t("Complete Isolation"))
        self.setModal(True)
        self._items = [
            IsolationCertificate.IsolationItem(tag=i.tag, description=i.description, state=i.state)
                .setLockNum(i.lock_num).setLockBoxNum(i.lock_box_num)
            for i in items
        ]

        self.summeryLabels = ['Tag', 'Description', 'State', 'Lock #', 'Lock Box #']
        self.summeryFields = ['tag', 'description', 'state', 'lock_num', 'lock_box_num']
        self._editableCols = {3, 4}

        lyt = QVBoxLayout(self)
        lyt.addWidget(QLabel(t("Optionally record the Lock # / Lock Box # used for each item:")))

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.setRowCount(len(self._items))
        self.tbl.verticalHeader().hide()
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        for row, item in enumerate(self._items):
            for col, field in enumerate(self.summeryFields):
                cell = QTableWidgetItem(str(getattr(item, field)))
                if col not in self._editableCols:
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tbl.setItem(row, col, cell)

        lyt.addWidget(self.tbl, stretch=1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

        self.setMinimumSize(600, 300)

    def getItems(self) -> list['IsolationCertificate.IsolationItem']:
        for row in range(self.tbl.rowCount()):
            self._items[row].lock_num = self.tbl.item(row, 3).text()
            self._items[row].lock_box_num = self.tbl.item(row, 4).text()
        return self._items
