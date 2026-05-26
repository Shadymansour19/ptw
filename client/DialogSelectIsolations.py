from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QPushButton, QDialogButtonBox)
from PyQt6.QtGui import QFont

from PTWData import Isolation


class DialogSelectIsolations(QDialog):
    """
    Dual-mode isolation dialog.

    Selection mode  (review_mode=False, selectable=True):
        PA selects which isolations to KEEP.  Unchecked rows will be de-isolated.
        Returns kept tags via getKeptTags().

    Review mode (review_mode=True):
        IA sees what the PA decided to keep (checked) vs release (unchecked).
        Three buttons: Accept / Reject / Cancel.
        Result is stored in self.action ('accept' | 'reject' | None).
    """

    def __init__(
        self,
        parent,
        isolations: list[Isolation],
        kept: list[str] = [],
        selectable: bool = True,
        review_mode: bool = False,
        view_only: bool = False,
        title: str = "Isolations",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.action = None

        lyt = QVBoxLayout(self)

        if view_only:
            lbl = QLabel("Kept isolations (checked) will remain active. Unchecked will be de-isolated:")
        elif review_mode:
            lbl = QLabel("Checked isolations will remain active. Unchecked will be de-isolated:")
        elif selectable:
            lbl = QLabel("Check the isolations to KEEP active (unchecked will be de-isolated):")
        else:
            lbl = QLabel("The following isolations will remain active:")
        lbl.setFont(QFont("Helvetica", 12))
        lbl.setWordWrap(True)
        lyt.addWidget(lbl)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(4)
        self.tbl.setHorizontalHeaderLabels(['Keep', 'Type', 'Tag', 'Description'])
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tbl.setColumnWidth(0, 40)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        if not selectable or review_mode or view_only:
            self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSortingEnabled(True)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl.setStyleSheet("""
            QTableWidget::indicator {
                width: 20px;
                height: 20px;
            }
        """)  
        lyt.addWidget(self.tbl)

        for iso in isolations:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            chk = QTableWidgetItem()
            flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            if review_mode or view_only:
                flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            elif not selectable:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            chk.setFlags(flags)
            is_kept = (iso.tag in kept) if kept else False
            chk.setCheckState(Qt.CheckState.Checked if is_kept else Qt.CheckState.Unchecked)
            chk.setSizeHint(QSize(20, 20))
            self.tbl.setItem(row, 0, chk)
            self.tbl.setItem(row, 1, QTableWidgetItem(str(iso.type)))
            self.tbl.setItem(row, 2, QTableWidgetItem(iso.tag))
            self.tbl.setItem(row, 3, QTableWidgetItem(iso.description))

        if selectable and not review_mode:
            btnRowLyt = QHBoxLayout()
            btnKeepAll = QPushButton("Keep All")
            btnReleaseAll = QPushButton("Release All")
            btnKeepAll.clicked.connect(self._keepAll)
            btnReleaseAll.clicked.connect(self._releaseAll)
            btnRowLyt.addWidget(btnKeepAll)
            btnRowLyt.addWidget(btnReleaseAll)
            btnRowLyt.addStretch()
            lyt.addLayout(btnRowLyt)

        if view_only:
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            btns.rejected.connect(self.reject)
            lyt.addWidget(btns)
        elif review_mode:
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes |
                QDialogButtonBox.StandardButton.No |
                QDialogButtonBox.StandardButton.Cancel
            )
            btns.button(QDialogButtonBox.StandardButton.Yes).setText("Accept")
            btns.button(QDialogButtonBox.StandardButton.No).setText("Reject")
            btns.button(QDialogButtonBox.StandardButton.Yes).clicked.connect(lambda: self._setAction('accept'))
            btns.button(QDialogButtonBox.StandardButton.No).clicked.connect(lambda: self._setAction('reject'))
            btns.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(self.reject)
            lyt.addWidget(btns)
        else:
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            btns.accepted.connect(self.accept)
            btns.rejected.connect(self.reject)
            lyt.addWidget(btns)

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.7))

    def _setAction(self, action: str):
        self.action = action
        self.accept()

    def _keepAll(self):
        for row in range(self.tbl.rowCount()):
            self.tbl.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _releaseAll(self):
        for row in range(self.tbl.rowCount()):
            self.tbl.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def getKeptTags(self) -> list[str]:
        return [
            self.tbl.item(row, 2).text()
            for row in range(self.tbl.rowCount())
            if self.tbl.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
