from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *

from PTWData import ActiveIsolation


class TableActiveIsolations(QWidget):
    def __init__(self, parent, loggedUser, label: str):
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.isolationsData: list[ActiveIsolation] = []
        self.loggedUser = loggedUser

        self.summaryLabels = ['Type', 'Tag', 'Description', 'Primary PTW', 'Linked PTWs']

        lbl = QLabel(label)
        lbl.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setLayout(lyt)
        self.setAutoFillBackground(False)
        lyt.addWidget(lbl)
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

    def setIsolations(self, isolations: dict):
        self.tbl.setSortingEnabled(False)
        self.tbl.clearContents()
        self.isolationsData.clear()
        self.tbl.setRowCount(0)
        for iso in isolations.values():
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            self.tbl.setItem(row, 0, QTableWidgetItem(str(iso.type)))
            self.tbl.setItem(row, 1, QTableWidgetItem(str(iso.tag)))
            self.tbl.setItem(row, 2, QTableWidgetItem(str(iso.description)))
            self.tbl.setItem(row, 3, QTableWidgetItem(str(iso.primary_ptw)))
            self.tbl.setItem(row, 4, QTableWidgetItem(', '.join(str(p) for p in iso.linked_ptws)))
            self.isolationsData.append(iso)
        self.tbl.setSortingEnabled(True)
        self._sync()

    def clear(self):
        self.tbl.clearContents()
        self.isolationsData.clear()
        self.tbl.setRowCount(0)

    def _sync(self):
        tag_to_iso = {iso.tag: iso for iso in self.isolationsData}
        self.isolationsData = [tag_to_iso[self.tbl.item(r, 1).text()] for r in range(self.tbl.rowCount())]

    def _onDoubleClick(self, row, col):
        iso = self.isolationsData[row]

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Isolation — {iso.tag}")
        dlg.setMinimumWidth(420)

        lyt = QFormLayout(dlg)
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lyt.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        for label, value in [
            ("Type",        str(iso.type)),
            ("Tag",         str(iso.tag)),
            ("Description", str(iso.description)),
            ("Primary PTW", str(iso.primary_ptw)),
            ("Latest PTW",  str(iso.latest_ptw)),
            ("Linked PTWs", ', '.join(str(p) for p in iso.linked_ptws) or '—'),
        ]:
            val_lbl = QLabel(value)
            val_lbl.setWordWrap(True)
            lyt.addRow(f"<b>{label}:</b>", val_lbl)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        lyt.addRow(btns)

        dlg.exec()
