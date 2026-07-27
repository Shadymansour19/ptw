from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QPushButton, QDialogButtonBox)
from PyQt6.QtGui import QFont

from Isolation import IC


class DialogSelectHeldICs(QDialog):
    """
    Dual-mode linked-IC dialog, for the PTW hold flow.

    Selection mode  (review_mode=False, selectable=True):
        PA selects which linked ICs must stay HELD (isolated). Unchecked ICs are no longer
        required by this PTW while held, and become eligible for de-isolation once every
        other PTW linked to them is also closed or held-without-requiring them.
        Returns held IC ids via getHeldICIds().

    Review mode (review_mode=True):
        IA sees what the PA decided to keep held (checked) vs release (unchecked).
        Three buttons: Accept / Reject / Cancel.
        Result is stored in self.action ('accept' | 'reject' | None).
    """

    def __init__(
        self,
        parent,
        ics: list[IC],
        held: list[str] = [],
        selectable: bool = True,
        review_mode: bool = False,
        view_only: bool = False,
        title: str = "Linked ICs",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.action = None

        lyt = QVBoxLayout(self)

        if view_only:
            lbl = QLabel("Held ICs (checked) will remain isolated. Unchecked will be released for de-isolation:")
        elif review_mode:
            lbl = QLabel("Checked ICs will remain isolated. Unchecked will be released for de-isolation:")
        elif selectable:
            lbl = QLabel("Check the linked ICs that must stay HELD (isolated) — unchecked will be released for de-isolation:")
        else:
            lbl = QLabel("The following linked ICs will remain isolated:")
        lbl.setFont(QFont("Helvetica", 12))
        lbl.setWordWrap(True)
        lyt.addWidget(lbl)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(4)
        self.tbl.setHorizontalHeaderLabels(['Hold', 'IC#', 'Type', 'Status'])
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

        for ic in ics:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            chk = QTableWidgetItem()
            flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            if review_mode or view_only:
                flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            elif not selectable:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            chk.setFlags(flags)
            is_held = (str(ic.id) in held) if held else False
            chk.setCheckState(Qt.CheckState.Checked if is_held else Qt.CheckState.Unchecked)
            chk.setSizeHint(QSize(20, 20))
            self.tbl.setItem(row, 0, chk)
            self.tbl.setItem(row, 1, QTableWidgetItem(str(ic.id)))
            self.tbl.setItem(row, 2, QTableWidgetItem(str(ic.type)))
            self.tbl.setItem(row, 3, QTableWidgetItem(str(ic.getStatus())))

        if selectable and not review_mode:
            btnRowLyt = QHBoxLayout()
            btnHoldAll = QPushButton("Hold All")
            btnReleaseAll = QPushButton("Release All")
            btnHoldAll.clicked.connect(self._holdAll)
            btnReleaseAll.clicked.connect(self._releaseAll)
            btnRowLyt.addWidget(btnHoldAll)
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

    def _holdAll(self):
        for row in range(self.tbl.rowCount()):
            self.tbl.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _releaseAll(self):
        for row in range(self.tbl.rowCount()):
            self.tbl.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def getHeldICIds(self) -> list[str]:
        return [
            self.tbl.item(row, 1).text()
            for row in range(self.tbl.rowCount())
            if self.tbl.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
